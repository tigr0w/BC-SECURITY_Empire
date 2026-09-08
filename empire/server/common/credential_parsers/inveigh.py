import logging
import re
from typing import TYPE_CHECKING

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import NETNTLMV1, NETNTLMV2

if TYPE_CHECKING:
    from empire.server.core.db import models

log = logging.getLogger(__name__)

TOOL_TAG = "inveigh"
MACHINE_ACCOUNT_TAG = "machine_account"

# Invoke-Inveigh writes each capture to the console stream as a header line
# followed by the hashcat-format response on the next line, e.g.:
#   2026-08-21T12:00:00 - SMB NTLMv2 challenge/response captured from 10.0.0.5(HOST):
#   user::DOMAIN:1122334455667788:<32-hex ntproof>:<blob hex>
# We key off the response shape rather than the header, so HTTP/HTTPS/Proxy/SMB
# captures are all handled uniformly.
#
# NetNTLMv1 (hashcat 5500): user::domain:lmresp(48):ntresp(48):challenge(16)
# NetNTLMv2 (hashcat 5600): user::domain:challenge(16):ntproof(32):blob
# The exact hex-segment lengths make the two shapes mutually exclusive, so a
# v1 line never matches the v2 pattern and vice versa. Username may end in `$`
# (machine account); domain may be empty.
_NETNTLMV1_RE = re.compile(
    r"^(?P<user>[^:\s]+)::(?P<domain>[^:]*):"
    r"(?P<lmresp>[0-9a-fA-F]{48}):(?P<ntresp>[0-9a-fA-F]{48}):"
    r"(?P<challenge>[0-9a-fA-F]{16})\s*$"
)
_NETNTLMV2_RE = re.compile(
    r"^(?P<user>[^:\s]+)::(?P<domain>[^:]*):"
    r"(?P<challenge>[0-9a-fA-F]{16}):(?P<ntproof>[0-9a-fA-F]{32}):"
    r"(?P<blob>[0-9a-fA-F]+)\s*$"
)


class InveighParser:
    """Turns each captured response line into a credential whose password body
    is the full hashcat line. Byte-identical lines collapse *within a single
    batch*; because ingestion runs per task-result batch, repeats spanning
    batches are caught downstream by the credential store's duplicate check. A
    re-authentication carries a fresh challenge, so it is a distinct line and
    is kept. Machine accounts are retained and tagged in `notes` — Empire runs
    Inveigh with `-MachineAccounts Y`, so they appear in the output.
    """

    def parse(
        self, data: bytes | str, agent: "models.Agent | None"
    ) -> list[CredentialPostRequest]:
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[str] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = _NETNTLMV2_RE.match(line)
            credtype = NETNTLMV2
            if not match:
                match = _NETNTLMV1_RE.match(line)
                credtype = NETNTLMV1
            if not match:
                continue

            username = match.group("user")
            domain = match.group("domain")

            if line in seen:
                continue
            seen.add(line)

            is_machine = username.endswith("$")
            notes = f"{TOOL_TAG} {MACHINE_ACCOUNT_TAG}" if is_machine else TOOL_TAG

            results.append(
                CredentialPostRequest(
                    credtype=credtype,
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
