import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import (
    DCC2,
    DPAPI_SYSTEM_KEY,
    HASH,
    PLAINTEXT,
)

log = logging.getLogger(__name__)

TOOL_TAG = "sharpsecdump"
MACHINE_ACCOUNT_TAG = "machine_account"
EMPTY_LM = "aad3b435b51404eeaad3b435b51404ee"

# Section headers. SharpSecDump intentionally mangles the case
# (`C4ched`, `LsA SEcrEts`) so we match case-insensitively.
_SECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\[\*\]\s*SAM\s+hashes", re.IGNORECASE), "sam"),
    (
        re.compile(r"\[\*\]\s*C[4a]ched\s+d[o0]main\s+l[o0]gon", re.IGNORECASE),
        "dcc2",
    ),
    (re.compile(r"\[\*\]\s*Ls[aA]\s+SE?cr[Ee]ts?", re.IGNORECASE), "lsa_banner"),
    (re.compile(r"\[\*\]\s*\$MACHINE\.ACC", re.IGNORECASE), "machine_acc"),
    (re.compile(r"\[\*\]\s*DefaultPassword", re.IGNORECASE), "default_pw"),
    (re.compile(r"\[\*\]\s*DPAPI_SYSTEM", re.IGNORECASE), "dpapi_system"),
]

_SAM_RE = re.compile(
    r"^(?P<user>[^:\s]+):(?P<rid>\d+):"
    r"(?P<lm>[0-9a-fA-F]{32}):(?P<nt>[0-9a-fA-F]{32})\s*:?\s*$"
)

_DCC2_RE = re.compile(
    r"^(?P<domain>[^/\\]+)[/\\](?P<user>[^:]+):"
    r"(?P<hash>\$DCC2\$\d+#[^#]+#[0-9a-fA-F]+)\s*$"
)

_MACHINE_ACC_RE = re.compile(
    r"^(?P<domain>[^\\/:]+)[\\/](?P<user>[^:]+\$):"
    r"(?P<lm>[0-9a-fA-F]{32}):(?P<nt>[0-9a-fA-F]{32})\s*$"
)

_DPAPI_SYSTEM_RE = re.compile(
    r"^(?P<name>dpapi_(?:machine|user)key)\s*:\s*(?P<hex>[0-9a-fA-F]+)\s*$"
)


class SharpSecDumpParser:
    """Parses SharpSecDump's multi-section report output. Handles SAM hashes,
    cached domain logons (DCC2 / hashcat-2100), the `$MACHINE.ACC` machine
    account NTLM, the `DefaultPassword` autologon plaintext, and the
    `DPAPI_SYSTEM` machine/user DPAPI keys.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:  # noqa: PLR0912
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str, str]] = set()

        def add(
            credtype: str,
            username: str,
            password: str,
            domain: str = "",
            extra_note: str | None = None,
        ) -> None:
            key = (credtype, username.lower(), password.lower() if password else "")
            if key in seen:
                return
            seen.add(key)
            notes = f"{TOOL_TAG} {extra_note}" if extra_note else TOOL_TAG
            results.append(
                CredentialPostRequest(
                    credtype=credtype,
                    domain=domain,
                    username=username,
                    password=password,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=notes,
                )
            )

        section = None
        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()

            new_section = _match_section(stripped)
            if new_section is not None:
                section = new_section
                continue

            if not stripped:
                continue

            if section == "sam":
                match = _SAM_RE.match(stripped)
                if match:
                    user = match.group("user")
                    lm = match.group("lm").lower()
                    nt = match.group("nt").lower()
                    pw = f"{lm}:{nt}" if lm != EMPTY_LM else nt
                    add(
                        HASH,
                        user,
                        pw,
                        extra_note=MACHINE_ACCOUNT_TAG if user.endswith("$") else None,
                    )

            elif section == "dcc2":
                match = _DCC2_RE.match(stripped)
                if match:
                    add(
                        DCC2,
                        match.group("user"),
                        match.group("hash"),
                        domain=match.group("domain"),
                    )

            elif section == "machine_acc":
                match = _MACHINE_ACC_RE.match(stripped)
                if match:
                    lm = match.group("lm").lower()
                    nt = match.group("nt").lower()
                    pw = f"{lm}:{nt}" if lm != EMPTY_LM else nt
                    add(
                        HASH,
                        match.group("user"),
                        pw,
                        domain=match.group("domain"),
                        extra_note=MACHINE_ACCOUNT_TAG,
                    )

            elif section == "default_pw":
                # SharpSecDump prints a `[!] secret type not supported yet`
                # warning before the raw unicode value. Skip status lines
                # and take the first real content line as the password.
                if stripped.startswith(("[*]", "[!]", "[X]", "[+]", "[-]")):
                    continue
                add(
                    PLAINTEXT,
                    "(autologon)",
                    stripped,
                    extra_note="default_password",
                )
                section = None  # one value only

            elif section == "dpapi_system":
                match = _DPAPI_SYSTEM_RE.match(stripped)
                if match:
                    add(DPAPI_SYSTEM_KEY, match.group("name"), match.group("hex"))

        return results


def _match_section(line: str) -> str | None:
    for pattern, name in _SECTION_PATTERNS:
        if pattern.search(line):
            return name
    return None
