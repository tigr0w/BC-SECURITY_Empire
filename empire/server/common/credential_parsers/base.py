from typing import TYPE_CHECKING, Protocol

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest

if TYPE_CHECKING:
    from empire.server.core.db import models


class CredentialParser(Protocol):
    """Turns agent task output into credential DTOs ready for CredentialService.

    Parsers fill `host`/`os` from the agent when the output itself doesn't
    carry those fields. `agent` may be `None` when the source isn't tied to
    an Empire agent (e.g. a plugin tailing a third-party tool's logs); in
    that case the parser leaves `host` as `""` and `os` as `None` unless the
    input itself carries them. Return an empty list when no credentials are
    found.

    Caller contract: pass the originating `Agent` whenever the data came
    from agent tasking. `None` is reserved for non-agent ingestion paths
    (plugins, file uploads) — don't default to `None` for convenience,
    since that strips host attribution from credentials that have it.

    `data` may be `bytes` or `str`; the helpers `coerce_bytes` / `coerce_str`
    normalise to whichever form the parser body wants.
    """

    def parse(
        self, data: bytes | str, agent: "models.Agent | None"
    ) -> list[CredentialPostRequest]: ...


def coerce_bytes(data: bytes | str) -> bytes:
    if isinstance(data, str):
        return data.encode("UTF-8")
    return data


def coerce_str(data: bytes | str) -> str:
    if isinstance(data, bytes):
        return data.decode("UTF-8", errors="replace")
    return data
