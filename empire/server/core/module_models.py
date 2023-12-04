from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class LanguageEnum(str, Enum):
    python = "python"
    powershell = "powershell"
    csharp = "csharp"


class EmpireModuleAdvanced(BaseModel):
    option_format_string: str = '-{{ KEY }} "{{ VALUE }}"'
    option_format_string_boolean: str = "-{{ KEY }}"
    custom_generate: bool = False
    generate_class: Any = None


class EmpireModuleOption(BaseModel):
    name: str
    name_in_code: str | None = None
    description: str = ""
    required: bool = False
    value: str = ""
    suggested_values: list[str] = []
    strict: bool = False
    type: str | None = None

    # Ensure the functionality of pydantic v1 coercing values to strings
    # https://github.com/pydantic/pydantic/issues/5606
    @field_validator("value", mode="plain")
    @classmethod
    def check_value(cls, v):
        return str(v)

    # @classmethod
    @field_validator("suggested_values", mode="plain")
    @classmethod
    def check_suggested_values(cls, v):
        return [str(value) for value in v]


class EmpireModuleAuthor(BaseModel):
    name: str
    handle: str
    link: str


class EmpireModule(BaseModel):
    id: str
    name: str
    authors: list[EmpireModuleAuthor] = []
    description: str = ""
    software: str = ""
    techniques: list[str] = []
    tactics: list[str] = []
    background: bool = False
    output_extension: str | None = None
    needs_admin: bool = False
    opsec_safe: bool = False
    language: LanguageEnum
    min_language_version: str | None = None
    comments: list[str] = []
    options: list[EmpireModuleOption] = []
    script: str | None = None
    script_path: str | None = None
    script_end: str = " {{ PARAMS }}"
    enabled: bool = True
    advanced: EmpireModuleAdvanced = EmpireModuleAdvanced()
    compiler_yaml: str | None = None

    def matches(self, query: str, parameter: str = "any") -> bool:
        query = query.lower()
        match = {
            "name": query in self.name.lower(),
            "description": query in self.description.lower(),
            "comments": any(query in comment.lower() for comment in self.comments),
            "authors": any(query in author.lower() for author in self.authors),
        }

        if parameter == "any":
            return any(match.values())

        return match[parameter]

    @property
    def info(self) -> dict:
        desc = self.dict(include={"name", "authors", "description", "comments"})
        desc["options"] = [option.dict() for option in self.options]
        return desc
