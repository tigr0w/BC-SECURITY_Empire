import sys
from typing import Dict, List, Union

import yaml
from pydantic import BaseModel, Extra, Field

from empire.server.common import helpers


class DatabaseConfig(BaseModel):
    type: str
    defaults: Dict[str, Union[bool, int, str]]

    # sqlite
    location: str = "empire/server/data/empire.db"

    # mysql
    url: str = "localhost:3306"
    username: str = ""
    password: str = ""


class ModulesConfig(BaseModel):
    # todo vr In 5.0 we should pick a single naming convention for config.
    retain_last_value: bool = Field(alias="retain-last-value")


class DirectoriesConfig(BaseModel):
    downloads: str
    module_source: str
    obfuscated_module_source: str


class EmpireConfig(BaseModel):
    supress_self_cert_warning: bool = Field(
        alias="supress-self-cert-warning", default=True
    )
    database: DatabaseConfig
    modules: ModulesConfig
    plugins: Dict[str, Dict[str, str]] = {}
    directories: DirectoriesConfig
    keyword_obfuscation: List[str] = []

    def __init__(self, config_dict: Dict):
        super().__init__(**config_dict)
        # For backwards compatibility
        self.yaml = config_dict

    class Config:
        extra = Extra.allow


def set_yaml(location: str):
    try:
        with open(location, "r") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)
    except FileNotFoundError as exc:
        print(exc)


config_dict = {}
if "--config" in sys.argv:
    location = sys.argv[sys.argv.index("--config") + 1]
    print(f"Loading config from {location}")
    config_dict = set_yaml(location)
if len(config_dict.items()) == 0:
    print(helpers.color("[*] Loading default config"))
    config_dict = set_yaml("./empire/server/config.yaml")

empire_config = EmpireConfig(config_dict)
