import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from empire.server.common.malleable.profile import Profile as MalleableProfile

log = logging.getLogger(__name__)


class Profile(BaseModel):
    id: int
    name: str
    file_path: str | None = None
    category: str
    data: str
    # Derived from the parsed profile body (set host_stage / set sample_name).
    # Populated by the post-validator below so consumers of the API don't
    # have to re-parse the raw profile text just to read these two fields.
    host_stage: bool | None = None
    sample_name: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _derive_parsed_fields(self):
        """Parse the embedded profile body and surface a couple of common
        top-level ``set`` directives. Best-effort: a profile that fails to
        parse here simply returns with the fields left as None — the body
        validation pipeline lives in the listener, not the DTO.
        """
        try:
            parsed = MalleableProfile()
            parsed.ingest(content=self.data)
        except Exception as exc:
            log.debug(
                "profile_dto: failed to parse %s for derived fields: %s",
                self.name,
                exc,
            )
            return self

        self.host_stage = getattr(parsed, "host_stage", None)
        self.sample_name = getattr(parsed, "sample_name", None)
        return self


class Profiles(BaseModel):
    records: list[Profile]


# name can't be modified atm because of the way name is inferred from the file name.
# could be fixed later on.
class ProfileUpdateRequest(BaseModel):
    data: str


class ProfilePostRequest(BaseModel):
    name: str
    category: str
    data: str
