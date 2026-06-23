"""Canonical option-type vocabulary shared across core, utils, and the API.

This is a leaf module (stdlib-only imports) so module models, option
validation, and the response DTOs can all depend on it without import cycles.
The string→type knowledge lives here in exactly one place: `_TYPE_STR_TO_PY`
is *derived* from the single alias table below, so a new type alias only ever
has to be added once. `_VALUETYPE_TO_TAG` is a small hand-maintained inverse
keyed on `ValueType` (not on the aliases), so new aliases never touch it.
"""

from enum import StrEnum
from typing import Any


class ValueType(StrEnum):
    string = "STRING"
    float = "FLOAT"
    integer = "INTEGER"
    boolean = "BOOLEAN"
    file = "FILE"


def infer_value_type(value: Any) -> ValueType:
    """Infer a `ValueType` from the Python type of a raw option value.

    `bool` must precede `int` — `isinstance(True, int)` is `True` because
    `bool` subclasses `int`. That ordering is the single invariant this helper
    exists to protect; callers should delegate here rather than open-coding it.
    """
    if isinstance(value, bool):
        return ValueType.boolean
    if isinstance(value, int):
        return ValueType.integer
    if isinstance(value, float):
        return ValueType.float
    return ValueType.string


# The single alias list: every accepted YAML/API `type:` tag → canonical
# `ValueType`. Many-to-one (`bool` and `boolean` both map to BOOLEAN). The
# projections below are derived from this; add a new alias here only.
_TYPE_STR_TO_VALUETYPE: dict[str, ValueType] = {
    "file": ValueType.file,
    "bool": ValueType.boolean,
    "boolean": ValueType.boolean,
    "int": ValueType.integer,
    "integer": ValueType.integer,
    "float": ValueType.float,
    "str": ValueType.string,
    "string": ValueType.string,
}

# Canonical `ValueType` → the Python type `safe_cast` coerces to. `file` is a
# sentinel (file values are resolved before any cast), so it maps to the
# string "file" rather than a callable type. Keyed on the enum, so it never
# needs a new entry when an alias is added.
_VALUETYPE_TO_PYTYPE: dict[ValueType, type | str] = {
    ValueType.boolean: bool,
    ValueType.integer: int,
    ValueType.float: float,
    ValueType.string: str,
    ValueType.file: "file",
}

# Derived: tag → Python type, for `safe_cast` dispatch (formerly hand-kept in
# `option_util`). Composed from the two tables above, never edited directly.
_TYPE_STR_TO_PY: dict[str, type | str] = {
    tag: _VALUETYPE_TO_PYTYPE[vtype] for tag, vtype in _TYPE_STR_TO_VALUETYPE.items()
}

# Inverse: the canonical `type:` tag written back onto an option for each
# inferred `ValueType`. Only the types `infer_value_type` produces from a raw
# scalar appear here: `ValueType.string` is intentionally absent so inferred
# strings keep `type=None` (the legacy "untyped string" YAML shape), and
# `ValueType.file` never arises from inference at all.
_VALUETYPE_TO_TAG: dict[ValueType, str] = {
    ValueType.boolean: "bool",
    ValueType.integer: "int",
    ValueType.float: "float",
}


def py_type_for_tag(tag: str) -> type | str | None:
    """The Python type `safe_cast` coerces a `type:` tag to.

    Returns the ``"file"`` sentinel for file options and None for an unknown
    tag, letting callers tell a valid type from an unrecognized one. The public
    accessor for the private `_TYPE_STR_TO_PY` table.
    """
    return _TYPE_STR_TO_PY.get(tag.lower())


def known_type_tags() -> list[str]:
    """Sorted list of every accepted `type:` tag, for error messages."""
    return sorted(_TYPE_STR_TO_VALUETYPE)


def tag_for_value_type(value_type: ValueType) -> str | None:
    """The canonical `type:` tag to write back for an inferred `ValueType`.

    Returns None for `string`/`file`, which stay untyped (see `_VALUETYPE_TO_TAG`).
    """
    return _VALUETYPE_TO_TAG.get(value_type)


def to_value_type(value: Any, type: str = "") -> ValueType:
    """Resolve the `ValueType` for an option.

    Explicit `type` declaration (e.g. ``"bool"``, ``"int"``) wins; otherwise
    falls back to `infer_value_type` on the Python type of `value`. Unknown
    explicit types fall through to inference rather than raising — typo'd
    `type:` tags render as their Python-inferred type (typically STRING, since
    `value` is already str-coerced by the time the API layer sees it).
    """
    type_lower = (type or "").lower()
    if type_lower in _TYPE_STR_TO_VALUETYPE:
        return _TYPE_STR_TO_VALUETYPE[type_lower]
    return infer_value_type(value)
