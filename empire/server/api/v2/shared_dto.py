import typing
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
)

from empire.server.core.option_types import ValueType

if typing.TYPE_CHECKING:
    from empire.server.core.db import models


class BadRequestResponse(BaseModel):
    detail: str


class NotFoundResponse(BaseModel):
    detail: str


# Ensure the functionality of pydantic v1 coercing values to strings
# https://github.com/pydantic/pydantic/issues/5606
def coerce_to_string(v: Any):
    if isinstance(v, list):
        return [str(value) for value in v]
    return str(v)


class DependentOption(BaseModel):
    name: str
    values: list[str] | None


class CustomOptionSchema(BaseModel):
    description: str
    required: bool
    value: Annotated[str, BeforeValidator(coerce_to_string)]
    suggested_values: Annotated[list[str], BeforeValidator(coerce_to_string)]
    strict: bool
    editable: bool = True
    value_type: ValueType
    internal: bool
    depends_on: list[DependentOption] = []
    bypass_language_map: dict[str, str] | None = None


class OrderDirection(StrEnum):
    asc = "asc"
    desc = "desc"


class DownloadDescription(BaseModel):
    id: int
    filename: str
    link: str
    model_config = ConfigDict(from_attributes=True)


class Author(BaseModel):
    name: str | None = None
    handle: str | None = None
    link: str | None = None


def domain_to_dto_download_description(download: "models.Download"):
    filename = download.filename or download.location.split("/")[-1]

    return DownloadDescription(
        id=download.id,
        filename=filename,
        link=f"/api/v2/downloads/{download.id}/download",
    )


def to_string(value):
    return str(value)


# This is sort of an undocumented behavior for the Empire API. The openapi spec says
#   the values should be strings, but it has allowed other types.
# The behavior in pydantic v1 was to just coerce values to strings, but in v2
#   this behavior was changed to raise a validation error. Using this custom
#   type with a BeforeValidator allows us to coerce the value to a string before
#   validation.
# Every option-bearing POST body (modules, stagers, listeners, plugins) uses this
# contract: the OpenAPI schema stays a clean `dict[str, str]` (so typed-language
# clients get a plain string map), while native JSON `bool`/`int`/`float` are
# still accepted and normalized to strings. Each option's real type is advertised
# on the GET side via `value_type` and re-applied server-side by `safe_cast`.
coerced_dict = dict[str, Annotated[str, BeforeValidator(to_string)]]
