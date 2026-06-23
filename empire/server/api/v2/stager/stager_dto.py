from datetime import datetime

from pydantic import BaseModel, ConfigDict

from empire.server.api.v2.shared_dto import (
    Author,
    CustomOptionSchema,
    DownloadDescription,
    coerced_dict,
    domain_to_dto_download_description,
)
from empire.server.core.db import models
from empire.server.core.option_types import to_value_type
from empire.server.utils.option_util import LISTENER_OPTION_NAMES


def domain_to_dto_template(
    stager,
    uid: str,
    default_listener: str | None = None,
    listener_names: list[str] | None = None,
):
    def _bypass_language_map(name, opt):
        """Compute the per-payload-language bypass execution-language map for the
        Bypasses option from the stager's Language values plus the option's
        ``BypassLanguage`` default and sparse ``BypassLanguageOverrides``.
        Languages without an override inherit ``BypassLanguage``; if no default is
        declared they map to themselves (identity), matching stagers that deliver
        bypasses in the payload's own language. Returns None for non-Bypasses
        options and single-language stagers (nothing to filter on)."""
        if name.lower() != "bypasses":
            return None
        languages = (stager.options.get("Language") or {}).get("SuggestedValues") or []
        if len(languages) <= 1:
            return None
        default = opt.get("BypassLanguage")
        overrides = opt.get("BypassLanguageOverrides") or {}
        return {
            lang: overrides.get(lang, default if default is not None else lang)
            for lang in languages
        }

    def _option_entry(name, opt):
        is_listener = name.lower() in LISTENER_OPTION_NAMES
        value = opt["Value"]
        if is_listener and value == "" and default_listener:
            value = default_listener
        suggested = (
            listener_names
            if is_listener and listener_names is not None
            else opt["SuggestedValues"]
        )
        return {
            "description": opt["Description"],
            "required": opt["Required"],
            "value": value,
            "strict": opt["Strict"],
            "suggested_values": suggested,
            "value_type": to_value_type(value, opt.get("Type")),
            "depends_on": opt["DependsOn"] if opt["DependsOn"] is not None else [],
            "internal": opt["Internal"] if opt["Internal"] is not None else False,
            "bypass_language_map": _bypass_language_map(name, opt),
        }

    options = {name: _option_entry(name, opt) for name, opt in stager.options.items()}

    authors = [
        {
            "name": x["Name"],
            "handle": x["Handle"],
            "link": x["Link"],
        }
        for x in stager.info.get("Authors") or []
    ]

    return StagerTemplate(
        id=uid,
        name=stager.info.get("Name"),
        authors=authors,
        description=stager.info.get("Description"),
        comments=stager.info.get("Comments"),
        options=options,
    )


def domain_to_dto_stager(stager: models.Stager):
    return Stager(
        id=stager.id,
        name=stager.name,
        template=stager.module,
        one_liner=stager.one_liner,
        downloads=[domain_to_dto_download_description(x) for x in stager.downloads],
        options=stager.options,
        user_id=stager.user_id,
        created_at=stager.created_at,
        updated_at=stager.updated_at,
    )


class StagerTemplate(BaseModel):
    id: str
    name: str
    authors: list[Author]
    description: str
    comments: list[str]
    options: dict[str, CustomOptionSchema]
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "multi_launcher",
                "name": "Launcher",
                "authors": ["@harmj0y"],
                "description": "Generates a one-liner stage0 launcher for Empire.",
                "comments": [""],
                "options": {
                    "Listener": {
                        "description": "Listener to generate stager for.",
                        "required": True,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "Language": {
                        "description": "Language of the stager to generate.",
                        "required": True,
                        "value": "powershell",
                        "suggested_values": ["powershell", "python"],
                        "strict": True,
                        "depends_on": [],
                        "internal": False,
                    },
                    "OutFile": {
                        "description": "Filename that should be used for the generated output.",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "Base64": {
                        "description": "Base64 encode the output.",
                        "required": True,
                        "value": "True",
                        "suggested_values": ["True", "False"],
                        "strict": True,
                        "depends_on": [],
                        "internal": False,
                    },
                    "Obfuscate": {
                        "description": "Obfuscate the launcher powershell code, uses the ObfuscateCommand for obfuscation types.",
                        "required": False,
                        "value": "False",
                        "suggested_values": ["True", "False"],
                        "strict": True,
                        "depends_on": [],
                        "internal": False,
                    },
                    "ObfuscateCommand": {
                        "description": "The Invoke-Obfuscation command to use.",
                        "required": False,
                        "value": "Token\\All\\1",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "UserAgent": {
                        "description": "User-agent string to use for the staging request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "Proxy": {
                        "description": "Proxy to use for request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "ProxyCreds": {
                        "description": "Proxy credentials ([domain\\]username:password) to use for request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                    "Bypasses": {
                        "description": "Bypasses as a space separated list to be prepended to the launcher",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                        "depends_on": [],
                        "internal": False,
                    },
                },
            }
        }
    )


class StagerTemplates(BaseModel):
    records: list[StagerTemplate]


class Stager(BaseModel):
    id: int
    name: str
    template: str
    one_liner: bool
    downloads: list[DownloadDescription]
    options: coerced_dict
    user_id: int
    # optional because if its not saved yet, it will be None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Stagers(BaseModel):
    records: list[Stager]


class StagerPostRequest(BaseModel):
    name: str
    template: str
    options: coerced_dict
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "MyStager",
                "template": "multi_launcher",
                "options": {
                    "Listener": "",
                    "Language": "powershell",
                    "OutFile": "",
                    "Base64": "True",
                    "Obfuscate": "False",
                    "ObfuscateCommand": "Token\\All\\1",
                    "UserAgent": "default",
                    "Proxy": "default",
                    "ProxyCreds": "default",
                    "Bypasses": "",
                },
            }
        }
    )


class StagerUpdateRequest(BaseModel):
    name: str
    options: coerced_dict
