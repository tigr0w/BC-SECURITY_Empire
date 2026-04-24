import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import (
    HASH,
    KRB_TICKET,
    KRBASREP,
    KRBTGS,
)
from empire.server.common.credential_parsers.kerberoast import (
    KRB5TGS_HEADER_RE,
    reconstruct_tgs,
)

log = logging.getLogger(__name__)

TOOL_TAG = "rubeus"

# $krb5asrep$23$user@domain:hex$hex — Rubeus `asreproast` output.
_ASREP_HEADER_RE = re.compile(
    r"\$krb5asrep\$(?P<etype>\d+)\$(?P<user>[^@\s]+)@(?P<realm>[^:\s]+)[:\$]"
)
_HEX_BODY_RE = re.compile(r"[0-9A-Fa-f]+")

# `[*] base64(ticket.kirbi):` anchor precedes a block of indented base64 lines
# for asktgt/asktgs/dump/s4u/renew/describe subcommands.
_TICKET_ANCHOR_RE = re.compile(r"base64\(ticket\.kirbi\)\s*:\s*", re.IGNORECASE)
_BASE64_CHUNK_RE = re.compile(r"[A-Za-z0-9+/=]+")
_NTLM_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _reconstruct_asrep(text: str, header_start: int) -> str | None:
    header_match = _ASREP_HEADER_RE.match(text, header_start)
    if not header_match:
        return None
    tail = text[header_start:]
    stop = len(tail)
    for marker in ("\n\n", "\n$krb5asrep$", "\n$krb5tgs$"):
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


def _parse_metadata_block(lines: list[str], start: int) -> tuple[dict[str, str], int]:
    """Read the `Key : Value` block Rubeus prints after a ticket. Returns the
    parsed dict and the index of the first line after the block.
    """
    fields: dict[str, str] = {}
    i = start
    blank_streak = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            blank_streak += 1
            if blank_streak >= 2 or (blank_streak == 1 and fields):  # noqa: PLR2004
                break
            i += 1
            continue
        blank_streak = 0
        # Field lines have the shape: `  Key : Value`. Bail out once we stop
        # seeing that shape (next section / new ticket).
        if ":" not in stripped or stripped.startswith("["):
            if fields:
                break
            i += 1
            continue
        key, _, value = stripped.partition(":")
        fields[key.strip()] = value.strip()
        i += 1
    return fields, i


def _consume_base64(lines: list[str], start: int) -> tuple[str, int]:
    """Consume indented base64 continuation lines after the
    `base64(ticket.kirbi):` anchor. Stops at the first non-base64 line.
    """
    i = start
    while i < len(lines) and not lines[i].strip():
        i += 1
    pieces: list[str] = []
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            if pieces:
                break
            i += 1
            continue
        chunks = _BASE64_CHUNK_RE.findall(stripped)
        # The line must be pure base64 (modulo surrounding whitespace) for
        # us to treat it as continuation. Once we see the metadata block
        # ("Key : Value"), stop.
        if (
            ":" in stripped
            or not chunks
            or "".join(chunks) != stripped.replace(" ", "")
        ):
            break
        pieces.extend(chunks)
        i += 1
    return "".join(pieces), i


def _strip_principal_annotation(name: str) -> str:
    # Rubeus prints `m.torres (NT_PRINCIPAL)` — drop the trailing parens.
    return re.sub(r"\s*\([A-Z_]+\)\s*$", "", name).strip()


class RubeusParser:
    """Handles Rubeus subcommands whose output carries a `$krb5tgs$` /
    `$krb5asrep$` hashcat blob (`kerberoast`, `asreproast`) or a
    `base64(ticket.kirbi):` block (`asktgt`, `asktgs`, and the ticket-
    emitting paths of `s4u`, `dump`, `renew`, `describe`). Also extracts
    the NTLM hash Rubeus prints as `ASREP (key)` for the authenticating
    principal. `triage` is not supported — its summary table has no
    kirbi payload and no hashcat blobs.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data).replace("\r", "")

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []

        results.extend(self._parse_krbtgs(text, agent_host, agent_os))
        results.extend(self._parse_asrep_hashes(text, agent_host, agent_os))
        results.extend(self._parse_ticket_blocks(text, agent_host, agent_os))

        return results

    def _parse_krbtgs(self, text, agent_host, agent_os):
        out = []
        seen: set[str] = set()
        for match in KRB5TGS_HEADER_RE.finditer(text):
            blob = reconstruct_tgs(text, match.start())
            if not blob or blob in seen:
                continue
            seen.add(blob)
            header = KRB5TGS_HEADER_RE.match(blob)
            if not header:
                continue
            out.append(
                CredentialPostRequest(
                    credtype=KRBTGS,
                    domain=header.group("realm").strip(),
                    username=header.group("user").strip(),
                    password=blob,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=f"{TOOL_TAG}:kerberoast",
                )
            )
        return out

    def _parse_asrep_hashes(self, text, agent_host, agent_os):
        out = []
        seen: set[str] = set()
        for match in _ASREP_HEADER_RE.finditer(text):
            blob = _reconstruct_asrep(text, match.start())
            if not blob or blob in seen:
                continue
            seen.add(blob)
            header = _ASREP_HEADER_RE.match(blob)
            if not header:
                continue
            out.append(
                CredentialPostRequest(
                    credtype=KRBASREP,
                    domain=header.group("realm").strip(),
                    username=header.group("user").strip(),
                    password=blob,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=f"{TOOL_TAG}:asreproast",
                )
            )
        return out

    def _parse_ticket_blocks(self, text, agent_host, agent_os):
        out = []
        lines = text.split("\n")
        seen_kirbi: set[str] = set()
        seen_hash: set[tuple[str, str, str]] = set()

        i = 0
        while i < len(lines):
            if not _TICKET_ANCHOR_RE.search(lines[i]):
                i += 1
                continue
            kirbi, next_i = _consume_base64(lines, i + 1)
            fields, next_i = _parse_metadata_block(lines, next_i)
            i = next_i

            if not kirbi and not fields:
                continue

            # UserName/UserRealm for asktgt/asktgs/dump; fall back to
            # ClientName/ClientRealm for s4u describe output.
            username = _strip_principal_annotation(
                fields.get("UserName") or fields.get("ClientName") or ""
            )
            realm = (fields.get("UserRealm") or fields.get("ClientRealm") or "").strip()
            subcommand = _infer_subcommand(fields)

            if kirbi and kirbi not in seen_kirbi:
                seen_kirbi.add(kirbi)
                out.append(
                    CredentialPostRequest(
                        credtype=KRB_TICKET,
                        domain=realm,
                        username=username,
                        password=kirbi,
                        host=agent_host,
                        os=agent_os,
                        sid="",
                        notes=f"{TOOL_TAG}:{subcommand}" if subcommand else TOOL_TAG,
                    )
                )

            asrep_key = fields.get("ASREP (key)")
            if asrep_key and _NTLM_HEX_RE.match(asrep_key.strip()):
                hash_value = asrep_key.strip().lower()
                hash_key = (username.lower(), realm.lower(), hash_value)
                if hash_key not in seen_hash:
                    seen_hash.add(hash_key)
                    out.append(
                        CredentialPostRequest(
                            credtype=HASH,
                            domain=realm,
                            username=username,
                            password=hash_value,
                            host=agent_host,
                            os=agent_os,
                            sid="",
                            notes=f"{TOOL_TAG}:{subcommand}"
                            if subcommand
                            else TOOL_TAG,
                        )
                    )

        return out


def _infer_subcommand(fields: dict[str, str]) -> str:
    flags = fields.get("Flags", "").lower()
    if "initial" in flags:
        return "asktgt"
    if fields.get("ServiceName") and not fields.get("ServiceName", "").startswith(
        "krbtgt"
    ):
        return "asktgs"
    return "ticket"
