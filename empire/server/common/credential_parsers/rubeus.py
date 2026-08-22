import logging
import re

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import (
    HASH,
    KRB_SESSION_KEY,
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

# The two markers that introduce a block of indented base64 lines:
# `[*] base64(ticket.kirbi):` (asktgt/asktgs/s4u/renew/describe) and
# `Base64EncodedTicket   :` (dump). See `RubeusParser` for how the two
# layouts differ.
_TICKET_ANCHOR_RE = re.compile(
    r"(?P<kirbi>base64\(ticket\.kirbi\))\s*:|(?P<dump>Base64EncodedTicket)\s*:",
    re.IGNORECASE,
)

# `  UserSID : S-1-5-21-...` in a `dump` logon-session header. Every ticket
# printed below it belongs to that session's owner.
_USER_SID_RE = re.compile(r"^\s*UserSID\s*:\s*(S-1-[0-9-]+?)\s*$")
_BASE64_CHUNK_RE = re.compile(r"[A-Za-z0-9+/=]+")
_NTLM_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")
# `Base64(key)` value: the ticket's session key. Rubeus prints `(null)` (or an
# empty value) when it could not read the key; the base64 charset alone
# rejects both. The length floor is the shortest key Kerberos uses — 8 bytes
# (`des_cbc_md5` / `des_cbc_crc`) encodes to 11 characters plus padding.
_SESSION_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{11,}={0,2}$")
# A keytype is only useful as a prefix if it looks like one — guard against a
# truncated/wrapped `KeyType` line poisoning the stored value.
_KEYTYPE_RE = re.compile(r"^[a-z0-9_]+$")


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


# An indented `Key : Value` line with a non-empty value. The non-empty value
# is load-bearing: it excludes the bare `Base64EncodedTicket   :` anchor, so
# the base64 body below it is never glued on as a wrapped continuation.
_FIELD_LINE_RE = re.compile(r"^\s+[^:\s][^:]*:\s*\S")


def _unwrap_field_lines(lines: list[str]) -> list[str]:
    """Rejoin metadata fields the agent transport hard-wrapped mid-value.

    Real `dump` output comes back column-wrapped, which splits long fields
    across lines (`UserName : HOST$ (NT_PRINC` / `IPAL)`). Left alone, the
    orphan tail reads as a block boundary and truncates the metadata. A
    non-blank, colon-less line whose predecessor is a complete field line is
    such a tail; base64 body lines never qualify, since their predecessor is
    either blank or another colon-less line.
    """
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            out
            and stripped
            and ":" not in stripped
            and not stripped.startswith("[")
            and _FIELD_LINE_RE.match(out[-1])
        ):
            # Assumes a hard column cut, so the tail resumes mid-token. A
            # wrap landing on a space would merge the two words instead; no
            # field emitted today has a load-bearing internal space.
            out[-1] = out[-1].rstrip() + stripped
            continue
        out.append(line)
    return out


def _parse_metadata_block_backward(lines: list[str], anchor_idx: int) -> dict[str, str]:
    """Read the `Key : Value` block `dump` prints *above* the
    `Base64EncodedTicket :` anchor, walking upward from `anchor_idx - 1`.

    Stops at the first blank line or non-field line, normally the previous
    ticket's base64 body. That boundary is not always there: the first ticket
    under a logon-session header abuts it, so the walk carries on into the
    header's own `UserName`/`Domain`. Keeping only the first occurrence of a
    key — nearest wins, since we read upward — is what stops the session
    owner from shadowing that ticket's principal.
    """
    fields: dict[str, str] = {}
    i = anchor_idx - 1
    while i >= 0:
        stripped = lines[i].strip()
        if not stripped or ":" not in stripped or stripped.startswith("["):
            break
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key and key not in fields:
            fields[key] = value.strip()
        i -= 1
    return fields


def _session_sids(lines: list[str]) -> list[str]:
    """Map each line index to the `UserSID` of the enclosing `dump` logon-
    session header, or "" when none has been seen. Only `dump` prints one.
    """
    out: list[str] = []
    current = ""
    for line in lines:
        match = _USER_SID_RE.match(line)
        if match:
            current = match.group(1)
        out.append(current)
    return out


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


def _session_key(fields: dict[str, str]) -> str | None:
    """Build the `<keytype>:<base64key>` value for a ticket's session key.

    Returns None when Rubeus printed no usable key. The keytype prefix is
    dropped rather than faked if `KeyType` is missing or malformed — a key
    with an unknown etype is still worth storing, a key with a *wrong* etype
    is worse than none.
    """
    raw_key = (fields.get("Base64(key)") or "").strip()
    if not _SESSION_KEY_RE.match(raw_key):
        return None
    keytype = (fields.get("KeyType") or "").strip().lower()
    if not _KEYTYPE_RE.match(keytype):
        return raw_key
    return f"{keytype}:{raw_key}"


class RubeusParser:
    """Handles Rubeus subcommands whose output carries a `$krb5tgs$` /
    `$krb5asrep$` hashcat blob (`kerberoast`, `asreproast`), a
    `base64(ticket.kirbi):` block (`asktgt`, `asktgs`, and the ticket-
    emitting paths of `s4u`, `renew`, `describe`), or the
    `Base64EncodedTicket :` blocks `dump` prints. Also extracts the NTLM
    hash Rubeus prints as `ASREP (key)` for the authenticating principal.

    The two ticket layouts differ: kirbi-style output puts the
    `Key : Value` metadata *after* the base64 body, `dump` puts it
    *before*, so the metadata is read in whichever direction the matched
    anchor implies. `dump` additionally groups tickets under logon-session
    headers, whose `UserSID` is carried onto every credential beneath it.

    `triage` is not supported — its summary table has no ticket payload
    and no hashcat blobs.
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
        lines = _unwrap_field_lines(text.split("\n"))
        seen_kirbi: set[str] = set()
        seen_hash: set[tuple[str, str, str]] = set()
        seen_keys: set[str] = set()

        sids = _session_sids(lines)

        i = 0
        while i < len(lines):
            anchor = _TICKET_ANCHOR_RE.search(lines[i])
            if not anchor:
                i += 1
                continue
            anchor_idx = i
            is_dump = anchor.group("dump") is not None
            kirbi, after_b64 = _consume_base64(lines, i + 1)

            if is_dump:
                # Metadata sits above the anchor. Deliberately no forward
                # fallback: parsing forward here would attribute the *next*
                # ticket's fields to this one.
                fields = _parse_metadata_block_backward(lines, anchor_idx)
                i = after_b64
            else:
                fields, i = _parse_metadata_block(lines, after_b64)

            if not kirbi and not fields:
                continue

            sid = sids[anchor_idx]

            # UserName/UserRealm for asktgt/asktgs/dump; fall back to
            # ClientName/ClientRealm for s4u describe output.
            username = _strip_principal_annotation(
                fields.get("UserName") or fields.get("ClientName") or ""
            )
            realm = (fields.get("UserRealm") or fields.get("ClientRealm") or "").strip()
            # `dump` is known from the anchor; only the kirbi-style
            # subcommands need the Flags/ServiceName heuristic.
            subcommand = "dump" if is_dump else _infer_subcommand(fields)
            note = f"{TOOL_TAG}:{subcommand}" if subcommand else TOOL_TAG
            # A session key is only usable once you know which ticket it
            # belongs to, and one logon session can hold many. The service
            # name is what pairs the two rows back up.
            service = (fields.get("ServiceName") or "").strip()
            if service:
                note = f"{note} {service}"

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
                        sid=sid,
                        notes=note,
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
                            sid=sid,
                            notes=note,
                        )
                    )

            session_key = _session_key(fields)
            if session_key and session_key not in seen_keys:
                seen_keys.add(session_key)
                out.append(
                    CredentialPostRequest(
                        credtype=KRB_SESSION_KEY,
                        domain=realm,
                        username=username,
                        password=session_key,
                        host=agent_host,
                        os=agent_os,
                        sid=sid,
                        notes=note,
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
