import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import KRBTGS

log = logging.getLogger(__name__)

TOOL_TAG = "kerberoast"

# $krb5tgs$ETYPE$*USER$REALM$SPN*$HEX... — header fields we need to populate
# domain/username. The hex body may be wrapped by PowerShell/Rubeus default
# formatting, so we reconstruct it from continuation lines.
KRB5TGS_HEADER_RE = re.compile(
    r"\$krb5tgs\$(?P<etype>\d+)\$\*(?P<user>[^$]+)\$(?P<realm>[^$]+)\$(?P<spn>[^*]+)\*\$"
)
_HEX_BODY_RE = re.compile(r"[0-9A-Fa-f]+")


def reconstruct_tgs(text: str, header_start: int) -> str | None:
    """Pull a single `$krb5tgs$...` blob starting at `header_start`, stitching
    continuation lines that default Rubeus/PowerShell output wraps onto.
    Returns the normalized single-line hash, or None if malformed.
    """
    header_match = KRB5TGS_HEADER_RE.match(text, header_start)
    if not header_match:
        return None

    # Everything from $krb5tgs$ up to the next blank line or the next $krb5tgs$.
    tail = text[header_start:]
    stop = len(tail)
    for marker in ("\n\n", "\n$krb5tgs$"):
        idx = tail.find(marker, 1)
        if idx != -1 and idx < stop:
            stop = idx
    chunk = tail[:stop]

    header_part = chunk[: header_match.end() - header_start]
    body_part = chunk[header_match.end() - header_start :]

    hex_pieces = _HEX_BODY_RE.findall(body_part)
    if not hex_pieces:
        return None

    return header_part + "".join(hex_pieces)


class KerberoastParser:
    """Handles Hashcat/John-format TGS hashes emitted by Invoke-Kerberoast,
    Rubeus (`kerberoast`), and SharpSploit (`Kerberoast`). Output may be
    preceded by per-SPN metadata lines; we key off the `$krb5tgs$` marker
    rather than the surrounding format.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data).replace("\r", "")

        results: list[CredentialPostRequest] = []
        seen: set[str] = set()

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        for match in KRB5TGS_HEADER_RE.finditer(text):
            blob = reconstruct_tgs(text, match.start())
            if not blob or blob in seen:
                continue
            seen.add(blob)

            header = KRB5TGS_HEADER_RE.match(blob)
            if not header:
                continue

            user = header.group("user").strip()
            realm = header.group("realm").strip()

            results.append(
                CredentialPostRequest(
                    credtype=KRBTGS,
                    domain=realm,
                    username=user,
                    password=blob,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=TOOL_TAG,
                )
            )

        return results
