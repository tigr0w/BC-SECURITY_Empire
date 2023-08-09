from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import Author, CustomOptionSchema, to_value_type
from empire.server.api.v2.tag.tag_dto import Tag, domain_to_dto_tag


def domain_to_dto_template(listener, uid: str):
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
            listener.options.items(),
        )
    )

    authors = list(
        map(
            lambda x: {
                "name": x["Name"],
                "handle": x["Handle"],
                "link": x["Link"],
            },
            listener.info.get("Authors") or [],
        )
    )

    return ListenerTemplate(
        id=uid,
        name=listener.info.get("Name"),
        authors=authors,
        description=listener.info.get("Description"),
        category=listener.info.get("Category"),
        comments=listener.info.get("Comments"),
        software=listener.info.get("Software"),
        techniques=listener.info.get("Techniques"),
        tactics=listener.info.get("Tactics"),
        options=options,
    )


def domain_to_dto_listener(listener):
    options = dict(map(lambda x: (x[0], x[1]["Value"]), listener.options.items()))

    return Listener(
        id=listener.id,
        name=listener.name,
        template=listener.module,
        enabled=listener.enabled,
        options=options,
        created_at=listener.created_at,
        tags=list(map(lambda x: domain_to_dto_tag(x), listener.tags)),
    )


class ListenerTemplate(BaseModel):
    id: str
    name: str
    authors: List[Author]
    description: str
    category: str
    comments: List[str]
    tactics: List[str]
    techniques: List[str]
    software: Optional[str]
    options: Dict[str, CustomOptionSchema]

    class Config:
        schema_extra = {
            "example": {
                "id": "http",
                "name": "HTTP[S]",
                "authors": [
                    {
                        "handle": "@harmj0y",
                        "link": "",
                        "name": "",
                    }
                ],
                "description": "Starts a http[s] listener that uses a GET/POST approach.",
                "category": "client_server",
                "comments": [],
                "tactics": [],
                "techniques": [],
                "software": "",
                "options": {
                    "Name": {
                        "description": "Name for the listener.",
                        "required": True,
                        "value": "http",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Host": {
                        "description": "Hostname/IP for staging.",
                        "required": True,
                        "value": "http://192.168.0.20",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "BindIP": {
                        "description": "The IP to bind to on the control server.",
                        "required": True,
                        "value": "0.0.0.0",
                        "suggested_values": ["0.0.0.0"],
                        "strict": False,
                    },
                    "Port": {
                        "description": "Port for the listener.",
                        "required": True,
                        "value": "",
                        "suggested_values": ["1335", "1336"],
                        "strict": False,
                    },
                    "Launcher": {
                        "description": "Launcher string.",
                        "required": True,
                        "value": "powershell -noP -sta -w 1 -enc ",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "StagingKey": {
                        "description": "Staging key for initial agent negotiation.",
                        "required": True,
                        "value": "}q)jFnDKw&px/7QBhE9Y<6~[Z1>{+Ps@",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "DefaultDelay": {
                        "description": "Agent delay/reach back interval (in seconds).",
                        "required": True,
                        "value": "5",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "DefaultJitter": {
                        "description": "Jitter in agent reachback interval (0.0-1.0).",
                        "required": True,
                        "value": "0.0",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "DefaultLostLimit": {
                        "description": "Number of missed checkins before exiting",
                        "required": True,
                        "value": "60",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "DefaultProfile": {
                        "description": "Default communication profile for the agent.",
                        "required": True,
                        "value": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "CertPath": {
                        "description": "Certificate path for https listeners.",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "KillDate": {
                        "description": "Date for the listener to exit (MM/dd/yyyy).",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "WorkingHours": {
                        "description": "Hours for the agent to operate (09:00-17:00).",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Headers": {
                        "description": "Headers for the control server.",
                        "required": True,
                        "value": "Server:Microsoft-IIS/7.5",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "Cookie": {
                        "description": "Custom Cookie Name",
                        "required": False,
                        "value": "xNQsvLdAysjkonT",
                        "suggested_values": [],
                        "strict": False,
                    },
                    "StagerURI": {
                        "description": "URI for the stager. Must use /download/. Example: /download/stager.php",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
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
                    "SlackURL": {
                        "description": "Your Slack Incoming Webhook URL to communicate with your Slack instance.",
                        "required": False,
                        "value": "",
                        "suggested_values": [],
                        "strict": False,
                    },
                },
            }
        }


class ListenerTemplates(BaseModel):
    records: List[ListenerTemplate]


class Listener(BaseModel):
    id: int
    name: str
    enabled: bool
    template: str
    options: Dict[str, str]
    created_at: datetime
    tags: List[Tag]


class Listeners(BaseModel):
    records: List[Listener]


class ListenerPostRequest(BaseModel):
    name: str
    template: str
    options: Dict[str, str]

    class Config:
        schema_extra = {
            "example": {
                "name": "MyListener",
                "template": "http",
                "tactics": [""],
                "techniques": [""],
                "software": "",
                "options": {
                    "Name": "MyListener",  # TODO VR Name should not be an option
                    "Host": "http://localhost:1336",
                    "BindIP": "0.0.0.0",
                    "Port": "1336",
                    "Launcher": "powershell -noP -sta -w 1 -enc ",
                    "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
                    "DefaultDelay": 5,
                    "DefaultJitter": 0.0,
                    "DefaultLostLimit": 60,
                    "DefaultProfile": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
                    "CertPath": "",
                    "KillDate": "",
                    "WorkingHours": "",
                    "Headers": "Server:Microsoft-IIS/7.5",
                    "Cookie": "",
                    "StagerURI": "",
                    "UserAgent": "default",
                    "Proxy": "default",
                    "ProxyCreds": "default",
                    "SlackURL": "",
                },
            }
        }


class ListenerUpdateRequest(BaseModel):
    name: str
    enabled: bool
    options: Dict[str, str]

    def __iter__(self):
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]
