import logging
import sys
from pathlib import Path
from typing import Annotated

import netaddr
import yaml
from netaddr.core import AddrFormatError
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger(__name__)


class EmpireBaseModel(BaseModel):
    @field_validator("*")
    @classmethod
    def set_path(cls, v):
        if isinstance(v, Path):
            return v.expanduser().resolve()
        return v


class ApiConfig(EmpireBaseModel):
    ip: str = "0.0.0.0"
    port: int = 1337
    secure: bool = False
    cert_path: Path = "empire/server/data"


class SubmodulesConfig(EmpireBaseModel):
    auto_update: bool = True


class StarkillerConfig(EmpireBaseModel):
    repo: str = "bc-security/starkiller"
    directory: Path = "empire/server/api/v2/starkiller"
    ref: str = "main"
    auto_update: bool = True
    enabled: bool | None = True


class DatabaseDefaultObfuscationConfig(EmpireBaseModel):
    language: str = "powershell"
    enabled: bool = False
    command: str = r"Token\All\1"
    module: str = "invoke-obfuscation"
    preobfuscatable: bool = True


def valid_ip(v: str):
    try:
        if "-" in v:
            start, end = v.split("-")
            netaddr.IPRange(start, end)
        elif "/" in v:
            netaddr.IPNetwork(v)
        else:
            netaddr.IPAddress(v)

        return v
    except AddrFormatError as e:
        raise ValueError(
            f"Invalid IP address {v}. Must be a valid IP Address, Range, or CIDR."
        ) from e


class DatabaseDefaultsConfig(EmpireBaseModel):
    staging_key: str = "RANDOM"
    username: str = "empireadmin"
    password: str = "password123"
    obfuscation: list[DatabaseDefaultObfuscationConfig] = []
    keyword_obfuscation: list[str] = []
    ip_allow_list: list[Annotated[str, AfterValidator(valid_ip)]] = []
    ip_deny_list: list[Annotated[str, AfterValidator(valid_ip)]] = []


class SQLiteDatabaseConfig(EmpireBaseModel):
    location: Path = "empire/server/data/empire.db"


class MySQLDatabaseConfig(EmpireBaseModel):
    url: str = "localhost:3306"
    username: str = ""
    password: str = ""
    database_name: str = "empire"


class DatabaseConfig(EmpireBaseModel):
    use: str = "sqlite"
    sqlite: SQLiteDatabaseConfig
    mysql: MySQLDatabaseConfig
    defaults: DatabaseDefaultsConfig

    def __getitem__(self, key):
        return getattr(self, key)


class DirectoriesConfig(EmpireBaseModel):
    downloads: Path
    module_source: Path
    obfuscated_module_source: Path


class LoggingConfig(EmpireBaseModel):
    level: str = "INFO"
    directory: Path = "empire/server/downloads/logs/"
    simple_console: bool = True


class LastTaskConfig(EmpireBaseModel):
    enabled: bool = False
    file: Path = "empire/server/data/last_task.txt"


class DebugConfig(EmpireBaseModel):
    last_task: LastTaskConfig


class EmpireConfig(EmpireBaseModel):
    supress_self_cert_warning: bool = Field(default=True)
    api: ApiConfig | None = ApiConfig()
    starkiller: StarkillerConfig
    submodules: SubmodulesConfig
    database: DatabaseConfig
    plugins: dict[str, dict[str, str]] = {}
    directories: DirectoriesConfig
    logging: LoggingConfig
    debug: DebugConfig

    model_config = ConfigDict(extra="allow")

    def __init__(self, config_dict: dict):
        super().__init__(**config_dict)
        # For backwards compatibility
        self.yaml = config_dict


def set_yaml(location: str):
    location = Path(location).expanduser().resolve()
    try:
        with location.open() as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        log.warning(exc)
    except FileNotFoundError as exc:
        log.warning(exc)


config_dict = {}
if "--config" in sys.argv:
    location = sys.argv[sys.argv.index("--config") + 1]
    log.info(f"Loading config from {location}")
    config_dict = set_yaml(location)
if len(config_dict.items()) == 0:
    log.info("Loading default config")
    config_dict = set_yaml("./empire/server/config.yaml")

empire_config = EmpireConfig(config_dict)
