from typing import TYPE_CHECKING, Protocol

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest

if TYPE_CHECKING:
    from empire.server.core.db import models


class CredentialParser(Protocol):
    """Turns agent task output into credential DTOs ready for CredentialService.

    Parsers fill `host`/`os` from the agent when the output itself doesn't
    carry those fields. Return an empty list when no credentials are found.
    """

    def parse(
        self, data: bytes, agent: "models.Agent"
    ) -> list[CredentialPostRequest]: ...


def coerce_bytes(data: bytes | str) -> bytes:
    if isinstance(data, str):
        return data.encode("UTF-8")
    return data


def coerce_str(data: bytes | str) -> str:
    if isinstance(data, bytes):
        return data.decode("UTF-8", errors="replace")
    return data
