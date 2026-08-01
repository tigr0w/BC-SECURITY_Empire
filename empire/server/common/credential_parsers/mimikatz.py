import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_bytes
from empire.server.common.credential_parsers.credtypes import HASH, PLAINTEXT

log = logging.getLogger(__name__)

TOOL_TAG = "mimikatz"

# Regions of `sekurlsa::logonpasswords` output that carry credentials.
_SEKURLSA_REGEXES = [
    "(?s)(?<=msv :).*?(?=tspkg :)",
    "(?s)(?<=tspkg :).*?(?=wdigest :)",
    "(?s)(?<=wdigest :).*?(?=kerberos :)",
    "(?s)(?<=kerberos :).*?(?=ssp :)",
    "(?s)(?<=ssp :).*?(?=credman :)",
    "(?s)(?<=credman :).*?(?=Authentication Id :)",
    "(?s)(?<=credman :).*?(?=mimikatz)",
]

_NTLM_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _is_ntlm_hash(value: str) -> bool:
    return bool(_NTLM_RE.match(value))


class MimikatzParser:
    """Handles `Invoke-Mimikatz`, `sekurlsa::logonpasswords`, `lsadump::sam`,
    and `lsadump::dcsync` output. Output starts with a `Hostname:` line.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:  # noqa: PLR0912 PLR0915
        data = coerce_bytes(data)
        lines = data.split(b"\n")

        host_domain = ""
        domain_sid = ""
        host_name = ""
        for line in lines[0:2]:
            if line.startswith(b"Hostname:"):
                try:
                    domain = line.split(b":")[1].strip()
                    temp = domain.split(b"/")[0].strip()
                    domain_sid = domain.split(b"/")[1].strip().decode("UTF-8")

                    host_name = temp.split(b".")[0].decode("UTF-8")
                    host_domain = (
                        b".".join(temp.split(b".")[1:]).decode("UTF-8").lower()
                    )
                except (IndexError, UnicodeDecodeError):
                    log.debug(
                        "mimikatz: could not parse Hostname header", exc_info=True
                    )

        creds: list[tuple[str, str, str, str, str, str]] = []

        text = data.decode("UTF-8", errors="replace")
        for regex in _SEKURLSA_REGEXES:
            for match in re.compile(regex).findall(text):
                username, domain, password = "", "", ""
                for line in match.split("\n"):
                    try:
                        if "Username" in line:
                            username = line.split(":", 1)[1].strip()
                        elif "Domain" in line:
                            domain = line.split(":", 1)[1].strip()
                        elif "NTLM" in line or "Password" in line:
                            password = line.split(":", 1)[1].strip()
                    except IndexError:
                        # Field line without a value — skip silently.
                        pass

                if password in ("", "(null)"):
                    continue

                sid = ""
                if host_domain.startswith(domain.lower()):
                    domain = host_domain
                    sid = domain_sid

                cred_type = HASH if _is_ntlm_hash(password) else PLAINTEXT
                if cred_type == PLAINTEXT and username.endswith("$"):
                    # Machine account plaintext — drop.
                    continue

                creds.append((cred_type, domain, username, password, host_name, sid))

        # lsadump-style domain controller hashdump fallback: look for krbtgt.
        if not creds and len(lines) >= 13:  # noqa: PLR2004
            for x in range(8, 13):
                if lines[x].startswith(b"Domain :"):
                    try:
                        domain_parts = lines[x].split(b":")[1]
                        domain_b = domain_parts.split(b"/")[0].strip()
                        sid_b = domain_parts.split(b"/")[1].strip()
                        domain_s = domain_b.decode("UTF-8")
                        sid_s = sid_b.decode("UTF-8")

                        if host_domain.startswith(domain_s.lower()):
                            domain_s = host_domain
                            sid_s = domain_sid

                        krbtgt_hash = b""
                        for y in range(len(lines)):
                            if lines[y].startswith(b"User : krbtgt"):
                                krbtgt_hash = lines[y + 2].split(b":")[1].strip()
                                break

                        if krbtgt_hash:
                            creds.append(
                                (
                                    HASH,
                                    domain_s,
                                    "krbtgt",
                                    krbtgt_hash.decode("UTF-8"),
                                    host_name,
                                    sid_s,
                                )
                            )
                    except (IndexError, UnicodeDecodeError):
                        log.debug(
                            "mimikatz: lsadump krbtgt parse skipped", exc_info=True
                        )

        # lsadump::dcsync output — SAM account block. The marker line is
        # indented in real dcsync output, so check membership per-line.
        if not creds and any(b"** SAM ACCOUNT **" in ln for ln in lines):
            domain_s, user, user_hash, dc_name, sid_s = "", "", "", "", ""
            for line in lines:
                if line.strip().endswith(b"will be the domain"):
                    domain_s = line.split(b"'")[1].decode("UTF-8")
                elif line.strip().endswith(b"will be the DC server"):
                    dc_name = line.split(b"'")[1].split(b".")[0].decode("UTF-8")
                elif line.strip().startswith(b"SAM Username"):
                    user = line.split(b":")[1].strip().decode("UTF-8")
                elif line.strip().startswith(b"Object Security ID"):
                    parts = line.split(b":")[1].strip().split(b"-")
                    sid_s = b"-".join(parts[0:-1]).decode("UTF-8")
                elif line.strip().startswith(b"Hash NTLM:"):
                    user_hash = line.split(b":")[1].strip().decode("UTF-8")

            if domain_s and user_hash:
                creds.append((HASH, domain_s, user, user_hash, dc_name, sid_s))

        # De-dup preserving order. Unlike the legacy helpers.uniquify_tuples
        # (which keyed on credtype/domain/user/password only), we key on the
        # full 6-tuple so identical creds observed on different hosts survive.
        seen: set[tuple] = set()
        unique_creds: list[tuple] = []
        for cred in creds:
            if cred not in seen:
                seen.add(cred)
                unique_creds.append(cred)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)
        return [
            CredentialPostRequest(
                credtype=cred[0],
                domain=cred[1],
                username=cred[2],
                password=cred[3],
                host=cred[4] or agent_host,
                os=agent_os,
                sid=cred[5],
                notes=TOOL_TAG,
            )
            for cred in unique_creds
        ]
