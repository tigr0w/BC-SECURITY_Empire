"""Registry of credential parsers.

Each parser turns raw agent task output into `CredentialPostRequest` DTOs.
Modules declare which parser handles their output via the `credential_parser`
field in their YAML. When no module is known (ad-hoc shell invocations),
`detect_by_prefix` inspects the first line of output as a heuristic fallback
— the historical behaviour for `Invoke-Mimikatz` and prompt-driven captures.
"""

from empire.server.common.credential_parsers.base import (
    CredentialParser,
    coerce_bytes,
)
from empire.server.common.credential_parsers.internal_monologue import (
    InternalMonologueParser,
)
from empire.server.common.credential_parsers.kerberoast import KerberoastParser
from empire.server.common.credential_parsers.mimikatz import MimikatzParser
from empire.server.common.credential_parsers.ntlmextract import NtlmExtractParser
from empire.server.common.credential_parsers.prompt import PromptParser
from empire.server.common.credential_parsers.pwdump_hashes import PwdumpHashesParser
from empire.server.common.credential_parsers.rubeus import RubeusParser
from empire.server.common.credential_parsers.session_gopher import SessionGopherParser
from empire.server.common.credential_parsers.sharp_dpapi import SharpDpapiParser
from empire.server.common.credential_parsers.sharpsecdump import SharpSecDumpParser
from empire.server.common.credential_parsers.tgtdelegation import TgtDelegationParser

_REGISTRY: dict[str, CredentialParser] = {
    "mimikatz": MimikatzParser(),
    "prompt": PromptParser(),
    "kerberoast": KerberoastParser(),
    "rubeus": RubeusParser(),
    "pwdump_hashes": PwdumpHashesParser(),
    "sharp_dpapi": SharpDpapiParser(),
    "session_gopher": SessionGopherParser(),
    "internal_monologue": InternalMonologueParser(),
    "sharpsecdump": SharpSecDumpParser(),
    "ntlmextract": NtlmExtractParser(),
    "tgtdelegation": TgtDelegationParser(),
}


def get_parser(name: str | None) -> CredentialParser | None:
    """Look up a registered parser by the name used in a module YAML."""
    if not name:
        return None
    return _REGISTRY.get(name)


def registered_parser_names() -> list[str]:
    """Return the sorted list of parser names a module YAML may declare."""
    return sorted(_REGISTRY)


def detect_by_prefix(data: bytes | str) -> CredentialParser | None:
    """Heuristic fallback for output that did not come from a module tasking
    (ad-hoc shell commands). Mirrors the historical prefix checks in
    `helpers.parse_credentials`.
    """
    data = coerce_bytes(data)
    first_line = data.split(b"\n", 1)[0]

    if first_line.startswith(b"Hostname:"):
        return _REGISTRY["mimikatz"]
    if first_line.startswith(b"[+] Prompted credentials:"):
        return _REGISTRY["prompt"]
    if b"text returned:" in first_line:
        return _REGISTRY["prompt"]
    return None


__all__ = [
    "CredentialParser",
    "detect_by_prefix",
    "get_parser",
    "registered_parser_names",
]
