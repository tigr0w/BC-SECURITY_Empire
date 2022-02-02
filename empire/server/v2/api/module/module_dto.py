from typing import List, Dict, Optional

from pydantic import BaseModel

from empire.server.common.module_models import PydanticModule, LanguageEnum
from empire.server.v2.api.shared_dto import CustomOptionSchema, to_value_type


def domain_to_dto_module(module: PydanticModule, uid: str):
    options = {x.name: x for x in module.options}
    options = dict(map(
        lambda x: (x[0], {
            'description': x[1].description,
            'required': x[1].required,
            'value': x[1].value,
            'strict': x[1].strict,
            'suggested_values': x[1].suggested_values,
            'value_type': to_value_type(x[1].value),
        }), options.items()))
    return Module(
        id=uid,
        name=module.name,
        enabled=module.enabled,
        authors=module.authors,
        description=module.description,
        background=module.background,
        language=module.language,
        min_language_version=module.min_language_version,
        needs_admin=module.needs_admin,
        opsec_safe=module.opsec_safe,
        techniques=module.techniques,
        software=module.software,
        category='module.category',
        comments=module.comments,
        options=options
    )


class Module(BaseModel):
    id: str
    name: str
    enabled: bool
    authors: List[str]
    description: str
    background: bool
    language: LanguageEnum
    min_language_version: Optional[str]
    needs_admin: bool
    opsec_safe: bool
    techniques: List[str]
    software: Optional[str]
    category: Optional[str]
    comments: List[str]
    options: Dict[str, CustomOptionSchema]


class Modules(BaseModel):
    records: List[Module]


class ModuleUpdateRequest(BaseModel):
    enabled: bool


class ModuleBulkUpdateRequest(BaseModel):
    modules: List[str]
    enabled: bool
