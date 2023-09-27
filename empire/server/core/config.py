import logging
import sys
from typing import Dict, List

import yaml
from pydantic import BaseModel, Extra, Field

log = logging.getLogger(__name__)


class StarkillerConfig(BaseModel):
    repo: str = "bc-security/starkiller"
    directory: str = "empire/server/api/v2/starkiller"
    ref: str = "main"
    auto_update: bool = True


class DatabaseDefaultObfuscationConfig(BaseModel):
    language: str = "powershell"
    enabled: bool = False
    command: str = r"Token\All\1"
    module: str = "invoke-obfuscation"
    preobfuscatable: bool = True


class DatabaseDefaultsConfig(BaseModel):
    staging_key: str = "RANDOM"
    username: str = "empireadmin"
    password: str = "password123"
    obfuscation: List[DatabaseDefaultObfuscationConfig] = []
    keyword_obfuscation: List[str] = []
    ip_whitelist: str = Field("", alias="ip-whitelist")
    ip_blacklist: str = Field("", alias="ip-blacklist")


class SQLiteDatabaseConfig(BaseModel):
    location: str = "empire/server/data/empire.db"


class MySQLDatabaseConfig(BaseModel):
    url: str = "localhost:3306"
    username: str = ""
    password: str = ""
    database_name: str = "empire"


class DatabaseConfig(BaseModel):
    use: str = "sqlite"
    sqlite: SQLiteDatabaseConfig
    mysql: MySQLDatabaseConfig
    defaults: DatabaseDefaultsConfig

    def __getitem__(self, key):
        return getattr(self, key)


class DirectoriesConfig(BaseModel):
    downloads: str
    module_source: str
    obfuscated_module_source: str


class LoggingConfig(BaseModel):
    level: str = "INFO"
    directory: str = "empire/server/downloads/logs/"
    simple_console: bool = True


class LastTaskConfig(BaseModel):
    enabled: bool = False
    file: str = "empire/server/data/last_task.txt"


class DebugConfig(BaseModel):
    last_task: LastTaskConfig


class EmpireConfig(BaseModel):
    supress_self_cert_warning: bool = Field(
        alias="supress-self-cert-warning", default=True
    )
    starkiller: StarkillerConfig
    database: DatabaseConfig
    plugins: Dict[str, Dict[str, str]] = {}
    directories: DirectoriesConfig
    logging: LoggingConfig
    debug: DebugConfig

    def __init__(self, config_dict: Dict):
        super().__init__(**config_dict)
        # For backwards compatibility
        self.yaml = config_dict

    class Config:
        extra = Extra.allow


def set_yaml(location: str):
    try:
        with open(location) as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)
    except FileNotFoundError as exc:
        print(exc)


config_dict = {}
if "--config" in sys.argv:
    location = sys.argv[sys.argv.index("--config") + 1]
    log.info(f"Loading config from {location}")
    config_dict = set_yaml(location)
if len(config_dict.items()) == 0:
    log.info("Loading default config")
    config_dict = set_yaml("./empire/server/config.yaml")

empire_config = EmpireConfig(config_dict)
