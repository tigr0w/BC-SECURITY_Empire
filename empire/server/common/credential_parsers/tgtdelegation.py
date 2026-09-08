import json
import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import KRB_TICKET

log = logging.getLogger(__name__)

TOOL_TAG = "tgtdelegation"

_DOMAIN_RE = re.compile(
    r"\[\+\]\s*Found a DC for the domain\s+([^\s!]+)", re.IGNORECASE
)
_DC_RE = re.compile(r"\[\+\]\s*DC:\s*\\?\\?([^\s]+)", re.IGNORECASE)
_SPN_RE = re.compile(r"\[\+\]\s*Target SPN:\s*(\S+)", re.IGNORECASE)
_APREQ_RE = re.compile(
    r"\[\+\]\s*AP-REQ output:\s*\n(?P<body>.*?)(?:\n\s*\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_SESSION_KEY_RE = re.compile(
    r"\[\+\]\s*Kerberos session key:\s*\n(?P<body>.*?)(?:\n\s*\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_ENCRYPTION_RE = re.compile(r"\[\+\]\s*Encryption:\s*\n?\s*(\S+)", re.IGNORECASE)
_BASE64_CHUNK_RE = re.compile(r"[A-Za-z0-9+/=]+")


def _collapse_base64(body: str) -> str:
    return "".join(_BASE64_CHUNK_RE.findall(body))


class TgtDelegationParser:
    """Parses the output of the `bof/credentials/tgtdelegation` BOF, which
    uses the GSS-API Kerberos delegation trick to produce an AP-REQ ticket
    for the current user plus the session key needed to reconstruct a
    usable TGT offline. Stores both halves plus SPN + encryption metadata
    as a JSON envelope in the `password` column so operators can extract
    whichever piece they need for the downstream tool.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data).replace("\r", "")

        apreq_match = _APREQ_RE.search(text)
        session_match = _SESSION_KEY_RE.search(text)
        if not apreq_match or not session_match:
            return []

        apreq = _collapse_base64(apreq_match.group("body"))
        session_key = _collapse_base64(session_match.group("body"))
        if not apreq or not session_key:
            return []

        encryption_match = _ENCRYPTION_RE.search(text)
        spn_match = _SPN_RE.search(text)
        domain_match = _DOMAIN_RE.search(text)
        dc_match = _DC_RE.search(text)

        spn = spn_match.group(1) if spn_match else ""
        encryption = encryption_match.group(1) if encryption_match else ""
        domain = domain_match.group(1) if domain_match else ""
        # If we have an FQDN from the SPN (e.g. CIFS/host.example.local),
        # prefer that over the short domain name for the `domain` column.
        fqdn = ""
        if spn and "/" in spn:
            target_host = spn.split("/", 1)[1]
            if "." in target_host:
                fqdn = target_host.split(".", 1)[1]
        if fqdn:
            domain = fqdn

        payload = {
            "apreq": apreq,
            "session_key": session_key,
            "encryption": encryption,
            "spn": spn,
        }
        if dc_match:
            payload["dc"] = dc_match.group(1)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        return [
            CredentialPostRequest(
                credtype=KRB_TICKET,
                domain=domain,
                username="(current_user)",
                password=json.dumps(payload),
                host=agent_host,
                os=agent_os,
                sid="",
                notes=TOOL_TAG,
            )
        ]
