import json
import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import (
    DPAPI_MASTERKEY,
    DPAPI_VAULT_CRED,
)

log = logging.getLogger(__name__)

TOOL_TAG = "sharp_dpapi"

# SharpDPAPI's masterkey triage emits pairs like:
#   [*] guidMasterKey    : {00000000-0000-0000-0000-000000000000}
#   [*] SHA1 MasterKey   : <40 hex chars>
_GUID_RE = re.compile(r"guidMasterKey\s*:\s*\{?([0-9a-fA-F-]{36})\}?", re.IGNORECASE)
_SHA1_KEY_RE = re.compile(r"SHA1\s+MasterKey\s*:\s*([0-9a-fA-F]{40})", re.IGNORECASE)

# Key-value pairs inside vault/chrome/credential blocks. Field names vary
# between subcommands (credentials/vault/chrome) — accept any of them.
_URL_RE = re.compile(
    r"^\s*(?:Target|URL|Resource)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)
_USER_RE = re.compile(
    r"^\s*(?:UserName|Username|User)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)
_PASS_RE = re.compile(
    r"^\s*(?:Password|Credential)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)


def _split_blocks(text: str) -> list[str]:
    """Split SharpDPAPI output into semantic blocks — separated by blank
    lines or by `---` separators it prints between Chrome entries.
    """
    normalized = re.sub(r"\n-{3,}.*?\n", "\n\n", text)
    return [b.strip() for b in normalized.split("\n\n") if b.strip()]


class SharpDpapiParser:
    """Handles SharpDPAPI's `masterkeys`, `credentials`, `vaults`, `chrome`,
    and related subcommands. Emits MASTERKEY rows only when the SHA1 body
    is present (partial decryption is skipped silently) and VAULT_CRED rows
    whenever a URL/user/password trio can be extracted from a block.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data).replace("\r", "")

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []

        results.extend(self._parse_masterkeys(text, agent_host, agent_os))
        results.extend(self._parse_vault_creds(text, agent_host, agent_os))

        return results

    def _parse_masterkeys(
        self, text: str, agent_host: str, agent_os
    ) -> list[CredentialPostRequest]:
        out: list[CredentialPostRequest] = []
        seen: set[tuple[str, str]] = set()

        # Walk line-by-line so that a GUID pairs with the SHA1 that follows
        # it in the same block.
        current_guid: str | None = None
        for line in text.splitlines():
            guid_match = _GUID_RE.search(line)
            if guid_match:
                current_guid = guid_match.group(1).lower()
                continue

            key_match = _SHA1_KEY_RE.search(line)
            if key_match and current_guid:
                sha1_key = key_match.group(1).lower()
                pair = (current_guid, sha1_key)
                if pair in seen:
                    current_guid = None
                    continue
                seen.add(pair)
                out.append(
                    CredentialPostRequest(
                        credtype=DPAPI_MASTERKEY,
                        domain="",
                        username=current_guid,
                        password=f"{current_guid}:{sha1_key}",
                        host=agent_host,
                        os=agent_os,
                        sid="",
                        notes=TOOL_TAG,
                    )
                )
                current_guid = None

        return out

    def _parse_vault_creds(
        self, text: str, agent_host: str, agent_os
    ) -> list[CredentialPostRequest]:
        out: list[CredentialPostRequest] = []
        seen: set[str] = set()

        for block in _split_blocks(text):
            url_match = _URL_RE.search(block)
            user_match = _USER_RE.search(block)

            # Vault blocks list "Credential : {GUID}" metadata AND a second
            # "Credential : <secret>" field. We want the last Password or
            # Credential field in the block that isn't a GUID.
            pass_match = None
            for m in _PASS_RE.finditer(block):
                value = m.group(1).strip()
                if _looks_like_guid(value):
                    continue
                pass_match = m

            if not (url_match and user_match and pass_match):
                continue

            payload = json.dumps(
                {
                    "url": url_match.group(1).strip(),
                    "username": user_match.group(1).strip(),
                    "password": pass_match.group(1).strip(),
                }
            )
            if payload in seen:
                continue
            seen.add(payload)

            out.append(
                CredentialPostRequest(
                    credtype=DPAPI_VAULT_CRED,
                    domain="",
                    username=user_match.group(1).strip(),
                    password=payload,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=TOOL_TAG,
                )
            )

        return out


_GUID_SHAPE_RE = re.compile(r"^\{?[0-9a-fA-F-]{36}\}?$")


def _looks_like_guid(value: str) -> bool:
    return bool(_GUID_SHAPE_RE.match(value.strip()))
