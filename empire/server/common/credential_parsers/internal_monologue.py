import logging
import re
from typing import TYPE_CHECKING

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import NETNTLMV1

if TYPE_CHECKING:
    from empire.server.core.db import models

log = logging.getLogger(__name__)

TOOL_TAG = "internal_monologue"
MACHINE_ACCOUNT_TAG = "machine_account"

# Hashcat mode 5500 format emitted by Invoke-InternalMonologue:
#   username::domain:lmresp:ntresp:challenge
# The username may end in `$` (machine account). Domain may be empty.
# Responses and challenge are hex.
_NETNTLMV1_RE = re.compile(
    r"^(?P<user>[^:\s]+)::(?P<domain>[^:]*):"
    r"(?P<lmresp>[0-9a-fA-F]+):(?P<ntresp>[0-9a-fA-F]+):(?P<challenge>[0-9a-fA-F]+)\s*$"
)


class InternalMonologueParser:
    """Parses NetNTLMv1 responses from Invoke-InternalMonologue. Each output
    line that matches the hashcat-5500 shape becomes a credential keyed by
    (username, hash-line) with the full response as the password body.
    Machine accounts (username ending in `$`) are retained and tagged in
    `notes` so operators can filter/skip them in the UI.
    """

    def parse(
        self, data: bytes | str, agent: "models.Agent | None"
    ) -> list[CredentialPostRequest]:
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str]] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = _NETNTLMV1_RE.match(line)
            if not match:
                continue

            username = match.group("user")
            domain = match.group("domain")

            is_machine = username.endswith("$")
            notes = f"{TOOL_TAG} {MACHINE_ACCOUNT_TAG}" if is_machine else TOOL_TAG

            key = (username.lower(), line)
            if key in seen:
                continue
            seen.add(key)

            results.append(
                CredentialPostRequest(
                    credtype=NETNTLMV1,
                    domain=domain,
                    username=username,
                    password=line,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=notes,
                )
            )

        return results
