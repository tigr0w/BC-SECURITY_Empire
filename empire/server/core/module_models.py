from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from empire.server.core.option_types import (
    infer_value_type,
    known_type_tags,
    py_type_for_tag,
    tag_for_value_type,
)


class LanguageEnum(StrEnum):
    python = "python"
    powershell = "powershell"
    csharp = "csharp"
    ironpython = "ironpython"
    go = "go"
    bof = "bof"


class EmpireModuleAdvanced(BaseModel):
    option_format_string: str = '-{{ KEY }} "{{ VALUE }}"'
    option_format_string_boolean: str = "-{{ KEY }}"
    custom_generate: bool = False
    # Path to the .py file containing the custom generate `Module` class.
    # The class is imported + instantiated lazily on first execute via
    # ModuleService._load_custom_generate_class — eager-loading every
    # custom_generate module at boot was costing cold-start time on
    # each MainMenu init / xdist worker boot.
    custom_generate_path: str | None = None
    generate_class: Any = None


class EmpireModuleOption(BaseModel):
    name: str
    name_in_code: str | None = None
    description: str = ""
    # Presence check only: rejects an empty/missing value at validation time.
    # For a normally-toggled boolean it never fires — a bool carries a value
    # (true/false) and the YAML default backfills any unset param. The only way
    # to trip it is a client explicitly POSTing an empty string, which a toggle
    # UI never does. Bool options should use `required: false`; `required: true`
    # buys nothing for a toggle and reads as "must be enabled" to form UIs.
    required: bool = False
    value: str = ""
    suggested_values: list[str] = []
    strict: bool = False
    type: str | None = None
    internal: bool = False
    depends_on: list[dict[str, str | list[str]]] | None = None

    @model_validator(mode="before")
    @classmethod
    def infer_type_and_coerce_value(cls, values):
        """Infer the `type` tag from the raw YAML value and coerce `value` to
        its string storage form.

        Explicit `type:` declarations on the YAML option win — a module author
        writing ``value: "8080"`` with no `type:` is signalling "string that
        happens to look numeric" and inference must not override that.
        ``mode="before"`` is required because the field-level
        ``value: str = ""`` coercion would otherwise hide the raw Python type
        of the value before this validator runs.

        Inference itself delegates to `option_types.infer_value_type` so the
        bool-before-int ordering invariant lives in exactly one place.
        """
        if not isinstance(values, dict):
            return values

        raw_value = values.get("value", "")
        explicit_type = values.get("type")

        if explicit_type is None:
            tag = tag_for_value_type(infer_value_type(raw_value))
            if tag is not None:
                values["type"] = tag

        values["value"] = "" if raw_value is None else str(raw_value)

        return values

    @field_validator("suggested_values", mode="plain")
    @classmethod
    def check_suggested_values(cls, v):
        return [str(value) for value in v]

    @field_validator("type")
    @classmethod
    def check_type_tag(cls, v: str | None) -> str | None:
        """Reject typo'd `type:` tags at module-load time instead of producing
        a misleading "Expected None but got <class 'str'>" error at task
        dispatch. Mirrors the `check_credential_parser` pattern below.
        """
        if v is None:
            return v
        if py_type_for_tag(v) is None:
            known = ", ".join(known_type_tags())
            raise ValueError(f"unknown option type {v!r}; valid types: {known}")
        return v


class EmpireAuthor(BaseModel):
    name: str | None = ""
    handle: str | None = ""
    link: str | None = ""


class BofModuleOption(BaseModel):
    x86: str | None = None
    x64: str | None = None
    entry_point: str | None = None
    format_string: str | None = None


class CSharpOption(BaseModel):
    UnsafeCompile: bool = False
    MergeReferences: bool = False
    CompatibleDotNetVersions: list[str] = []
    Code: str = ""
    ReferenceSourceLibraries: list[dict] | None = []
    ReferenceAssemblies: list[dict] | None = []
    EmbeddedResources: list[dict] | None = []


class EmpireModule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    authors: list[EmpireAuthor] = []
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
    bof: BofModuleOption | None = None
    script_end: str = " {{ PARAMS }}"
    enabled: bool = True
    advanced: EmpireModuleAdvanced = EmpireModuleAdvanced()
    compiler_yaml: str | None = None
    csharp: CSharpOption | None = None
    credential_parser: str | None = None

    @field_validator("credential_parser")
    @classmethod
    def check_credential_parser(cls, v: str | None) -> str | None:
        """Reject YAML typos at module-load time instead of when the first
        credential-producing task completes.
        """
        if v is None:
            return v
        # Deferred import: the parser package pulls in pydantic DTOs from
        # the api layer, which we don't want at model-class-definition time.
        from empire.server.common import credential_parsers  # noqa: PLC0415

        if credential_parsers.get_parser(v) is None:
            known = ", ".join(credential_parsers.registered_parser_names())
            raise ValueError(
                f"unknown credential_parser {v!r}; registered parsers: {known}"
            )
        return v
