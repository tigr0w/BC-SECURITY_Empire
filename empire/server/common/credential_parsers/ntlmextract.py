import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import HASH

log = logging.getLogger(__name__)

TOOL_TAG = "ntlmextract"
MACHINE_ACCOUNT_TAG = "machine_account"

# Invoke-NTLMExtract emits PowerShell PSCustomObject output piped through
# Out-String, which renders each object as `@{Key=Value; Key=Value}`.
# Fields are Username, NTLM, RID (order not guaranteed).
_BLOCK_RE = re.compile(r"@\{([^}]*)\}")
_NT_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _parse_block(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in body.split(";"):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        fields[key.strip()] = value.strip()
    return fields


class NtlmExtractParser:
    """Parses Invoke-NTLMExtract output: one `@{Username=...; NTLM=...; RID=...}`
    block per local account, as rendered by PowerShell's default Out-String
    formatter. Preserves machine-account rows and tags them in `notes`.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str]] = set()

        for match in _BLOCK_RE.finditer(text):
            fields = _parse_block(match.group(1))
            username = fields.get("Username", "").strip()
            nt_hash = fields.get("NTLM", "").strip().lower()

            if not username or not _NT_HEX_RE.match(nt_hash):
                continue

            key = (username.lower(), nt_hash)
            if key in seen:
                continue
            seen.add(key)

            is_machine = username.endswith("$")
            notes = f"{TOOL_TAG} {MACHINE_ACCOUNT_TAG}" if is_machine else TOOL_TAG

            results.append(
                CredentialPostRequest(
                    credtype=HASH,
                    domain="",
                    username=username,
                    password=nt_hash,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=notes,
                )
            )

        return results
