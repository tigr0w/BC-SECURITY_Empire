from pydantic import BaseModel

from empire.server.api.v2.shared_dto import Author, CustomOptionSchema
from empire.server.core.module_models import EmpireModule, LanguageEnum
from empire.server.core.option_types import to_value_type
from empire.server.utils.option_util import LISTENER_OPTION_NAMES


def domain_to_dto_module(
    module: EmpireModule,
    uid: str,
    default_listener: str | None = None,
    listener_names: list[str] | None = None,
):
    options = {x.name: x for x in module.options}

    def _option_entry(name, opt):
        is_listener = name.lower() in LISTENER_OPTION_NAMES
        value = opt.value
        if is_listener and value == "" and default_listener:
            value = default_listener
        suggested = (
            listener_names
            if is_listener and listener_names is not None
            else opt.suggested_values
        )
        return {
            "description": opt.description,
            "required": opt.required,
            "value": value,
            "strict": opt.strict,
            "suggested_values": suggested,
            "value_type": to_value_type(value, opt.type),
            "depends_on": opt.depends_on if opt.depends_on is not None else [],
            "internal": opt.internal if opt.internal is not None else False,
        }

    options = {name: _option_entry(name, opt) for name, opt in options.items()}

    return Module(
        id=uid,
        name=module.name,
        enabled=module.enabled,
        authors=[a.model_dump() for a in module.authors],
        description=module.description,
        background=module.background,
        language=module.language,
        min_language_version=module.min_language_version,
        needs_admin=module.needs_admin,
        opsec_safe=module.opsec_safe,
        techniques=module.techniques,
        software=module.software,
        tactics=module.tactics,
        comments=module.comments,
        options=options,
    )


class Module(BaseModel):
    id: str
    name: str
    enabled: bool
    authors: list[Author]
    description: str
    background: bool
    language: LanguageEnum
    min_language_version: str | None = None
    needs_admin: bool
    opsec_safe: bool
    techniques: list[str]
    tactics: list[str]
    software: str | None = None
    comments: list[str]
    options: dict[str, CustomOptionSchema]


class Modules(BaseModel):
    records: list[Module]


class ModuleScript(BaseModel):
    module_id: str
    script: str


class ModuleUpdateRequest(BaseModel):
    enabled: bool


class ModuleBulkUpdateRequest(BaseModel):
    modules: list[str]
    enabled: bool
