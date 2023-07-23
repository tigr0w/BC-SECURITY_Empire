from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import (
    Author,
    CustomOptionSchema,
    DownloadDescription,
    domain_to_dto_download_description,
    to_value_type,
)
from empire.server.core.db import models


def domain_to_dto_template(stager, uid: str):
    options = dict(
        map(
            lambda x: (
                x[0],
                {
                    "description": x[1]["Description"],
                    "required": x[1]["Required"],
                    "value": x[1]["Value"],
                    "strict": x[1]["Strict"],
                    "suggested_values": x[1]["SuggestedValues"],
                    "value_type": to_value_type(x[1]["Value"], x[1].get("Type")),
                },
            ),
            stager.options.items(),
        )
    )

    authors = list(
        map(
            lambda x: {
                "name": x["Name"],
                "handle": x["Handle"],
                "link": x["Link"],
            },
            stager.info.get("Authors") or [],
        )
    )

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
        downloads=list(
            map(lambda x: domain_to_dto_download_description(x), stager.downloads)
        ),
        options=stager.options,
        user_id=stager.user_id,
        created_at=stager.created_at,
        updated_at=stager.updated_at,
    )


class StagerTemplate(BaseModel):
    id: str
    name: str
    authors: List[Author]
    description: str
    comments: List[str]
    options: Dict[str, CustomOptionSchema]

    class Config:
        schema_extra = {
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
                    },
                    "Language": {
                        "description": "Language of the stager to generate.",
                        "required": True,
                        "value": "powershell",
                        "suggested_values": ["powershell", "python"],
                        "strict": True,
                    },
                    "StagerRetries": {
                        "description": "Times for the stager to retry connecting.",
                        "required": False,
                        "value": "0",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "OutFile": {
                        "description": "Filename that should be used for the generated output.",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Base64": {
                        "description": "Switch. Base64 encode the output.",
                        "required": True,
                        "value": "True",
                        "suggested_values": ["True", "False"],
                        "strict": True,
                    },
                    "Obfuscate": {
                        "description": "Switch. Obfuscate the launcher powershell code, uses the ObfuscateCommand for obfuscation types. For powershell only.",
                        "required": False,
                        "value": "False",
                        "suggested_values": ["True", "False"],
                        "strict": True,
                    },
                    "ObfuscateCommand": {
                        "description": "The Invoke-Obfuscation command to use. Only used if Obfuscate switch is True. For powershell only.",
                        "required": False,
                        "value": "Token\\All\\1",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "SafeChecks": {
                        "description": "Switch. Checks for LittleSnitch or a SandBox, exit the staging process if True. Defaults to True.",
                        "required": True,
                        "value": "True",
                        "suggested_values": ["True", "False"],
                        "strict": True,
                    },
                    "UserAgent": {
                        "description": "User-agent string to use for the staging request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Proxy": {
                        "description": "Proxy to use for request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "ProxyCreds": {
                        "description": "Proxy credentials ([domain\\]username:password) to use for request (default, none, or other).",
                        "required": False,
                        "value": "default",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Bypasses": {
                        "description": "Bypasses as a space separated list to be prepended to the launcher",
                        "required": False,
                        "value": "mattifestation etw",
                        "suggested_values": [],
                        "strict": False,
                    },
                },
            }
        }


class StagerTemplates(BaseModel):
    records: List[StagerTemplate]


class Stager(BaseModel):
    id: int
    name: str
    template: str
    one_liner: bool
    downloads: List[DownloadDescription]
    options: Dict[str, str]
    user_id: int
    created_at: Optional[
        datetime
    ]  # optional because if its not saved yet, it will be None
    updated_at: Optional[datetime]


class Stagers(BaseModel):
    records: List[Stager]


class StagerPostRequest(BaseModel):
    name: str
    template: str
    options: Dict[str, str]

    class Config:
        schema_extra = {
            "example": {
                "name": "MyStager",
                "template": "multi_launcher",
                "options": {
                    "Listener": "",
                    "Language": "powershell",
                    "StagerRetries": "0",
                    "OutFile": "",
                    "Base64": "True",
                    "Obfuscate": "False",
                    "ObfuscateCommand": "Token\\All\\1",
                    "SafeChecks": "True",
                    "UserAgent": "default",
                    "Proxy": "default",
                    "ProxyCreds": "default",
                    "Bypasses": "mattifestation etw",
                },
            }
        }


class StagerUpdateRequest(BaseModel):
    name: str
    options: Dict[str, str]

    def __iter__(self):
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]
