import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import HASH

log = logging.getLogger(__name__)

TOOL_TAG = "pwdump_hashes"
MACHINE_ACCOUNT_TAG = "machine_account"

# pwdump format: username:rid:lmhash:nthash:::
# Allow optional trailing metadata (like SharpSecDump's ":::" or ":user comment").
_PWDUMP_RE = re.compile(
    r"^(?P<username>[^:]+):(?P<rid>\d+):(?P<lm>[0-9a-fA-F]{32}|[Nn][Oo][\s_-]?[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\*+|aad3b435b51404eeaad3b435b51404ee):(?P<nt>[0-9a-fA-F]{32}):"
)

_EMPTY_LM = "aad3b435b51404eeaad3b435b51404ee"


class PwdumpHashesParser:
    """Handles pwdump-style output from Invoke-PowerDump, Invoke-SharpSecDump,
    and Invoke-NTLMExtract. Preserves machine-account hash rows (valuable for
    silver-ticket forging) and tags them in `notes` so operators can filter.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str]] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = _PWDUMP_RE.match(line)
            if not match:
                continue

            username = match.group("username").strip()
            nt_hash = match.group("nt").lower()
            lm_hash = match.group("lm").lower()

            # Construct the NTLM hash pair in the conventional format:
            # LM:NT if both present, else just NT.
            if lm_hash and lm_hash != _EMPTY_LM and len(lm_hash) == 32:  # noqa: PLR2004
                password = f"{lm_hash}:{nt_hash}"
            else:
                password = nt_hash

            is_machine = username.endswith("$")
            notes = f"{TOOL_TAG} {MACHINE_ACCOUNT_TAG}" if is_machine else TOOL_TAG

            key = (username.lower(), password)
            if key in seen:
                continue
            seen.add(key)

            results.append(
                CredentialPostRequest(
                    credtype=HASH,
                    domain="",
                    username=username,
                    password=password,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=notes,
                )
            )

        return results
