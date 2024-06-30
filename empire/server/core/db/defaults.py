import hashlib
import logging
import os
import random
import string

from passlib import pwd
from passlib.context import CryptContext

from empire.server.core.config import empire_config
from empire.server.core.db import models

database_config = empire_config.database.defaults

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

log = logging.getLogger(__name__)


def get_default_hashed_password():
    password = database_config.password
    return pwd_context.hash(password)


def get_default_user():
    return models.User(
        username=database_config.username,
        hashed_password=get_default_hashed_password(),
        enabled=True,
        admin=True,
    )


def get_default_config():
    return models.Config(
        staging_key=get_staging_key(),
        ip_whitelist=database_config.ip_whitelist,
        ip_blacklist=database_config.ip_blacklist,
        autorun_command="",
        autorun_data="",
        rootuser=True,
        jwt_secret_key=pwd.genword(length=32, charset="hex"),
    )


def get_default_keyword_obfuscation():
    keyword_obfuscation_list = database_config.keyword_obfuscation
    obfuscated_keywords = []
    for value in keyword_obfuscation_list:
        obfuscated_keywords.append(
            models.Keyword(
                keyword=value,
                replacement="".join(
                    random.choice(string.ascii_uppercase + string.digits)
                    for _ in range(5)
                ),
            )
        )
    return obfuscated_keywords


def get_default_obfuscation_config():
    obfuscation_config_list = database_config.obfuscation
    obfuscation_configs = []

    for config in obfuscation_config_list:
        obfuscation_configs.append(
            models.ObfuscationConfig(
                language=config.language,
                command=config.command,
                module=config.module,
                enabled=config.enabled,
                preobfuscatable=config.preobfuscatable,
            )
        )

    return obfuscation_configs


def get_staging_key():
    # Staging Key is set up via environmental variable or config.yaml. By setting RANDOM a randomly selected password
    # will automatically be selected.
    staging_key = os.getenv("STAGING_KEY") or database_config.staging_key
    punctuation = "!#%&()*+,-./:;<=>?@[]^_{|}~"

    if staging_key == "BLANK":
        choice = input(
            "\n [>] Enter server negotiation password, enter for random generation: "
        )
        if choice not in ("", "RANDOM"):
            return hashlib.md5(choice.encode("utf-8")).hexdigest()

    elif staging_key == "RANDOM":
        log.info("Generating random staging key")
        return "".join(
            random.sample(string.ascii_letters + string.digits + punctuation, 32)
        )

    else:
        log.info("Using configured staging key: {staging_key}")
        return staging_key
