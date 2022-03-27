import hashlib
import os
import random
import string

from passlib import pwd
from passlib.context import CryptContext

from empire.server.common.config import empire_config
from empire.server.database import models

database_config = empire_config.database.defaults

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_default_hashed_password():
    password = database_config.get("password", "password123")
    return pwd_context.hash(password)


def get_default_user():
    return models.User(
        username=database_config.get("username", "empireadmin"),
        hashed_password=get_default_hashed_password(),
        enabled=True,
        admin=True,
    )


def get_default_config():
    # Calculate the install path. We know the project directory will always be two levels up of the current directory.
    # Any modifications of the folder structure will need to be applied here.
    install_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    return models.Config(
        staging_key=get_staging_key(),
        install_path=install_path,
        ip_whitelist=database_config.get("ip-whitelist", ""),
        ip_blacklist=database_config.get("ip-blacklist", ""),
        autorun_command="",
        autorun_data="",
        rootuser=True,
        obfuscate=database_config.get("obfuscate", False),
        obfuscate_command=database_config.get("obfuscate-command", r"Token\All\1"),
        jwt_secret_key=pwd.genword(length=32, charset="hex"),
    )


def get_default_keyword_obfuscation():
    keyword_obfuscation_list = empire_config.yaml.get("keyword_obfuscation", {})
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


def get_staging_key():
    # Staging Key is set up via environmental variable or config.yaml. By setting RANDOM a randomly selected password
    # will automatically be selected.
    staging_key = os.getenv("STAGING_KEY") or database_config.get(
        "staging-key", "BLANK"
    )
    punctuation = "!#%&()*+,-./:;<=>?@[]^_{|}~"
    if staging_key == "BLANK":
        choice = input(
            "\n [>] Enter server negotiation password, enter for random generation: "
        )
        if choice != "" and choice != "RANDOM":
            return hashlib.md5(choice.encode("utf-8")).hexdigest()

    print("\x1b[1;34m[*] Generating random staging key\x1b[0m")
    return "".join(
        random.sample(string.ascii_letters + string.digits + punctuation, 32)
    )
