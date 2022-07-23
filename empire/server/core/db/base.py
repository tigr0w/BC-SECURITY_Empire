import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.defaults import (
    get_default_config,
    get_default_keyword_obfuscation,
    get_default_obfuscation_config,
    get_default_user,
)
from empire.server.core.db.models import Base

log = logging.getLogger(__name__)

database_config = empire_config.database

if database_config.type == "mysql":
    url = database_config.url
    username = database_config.username
    password = database_config.password
    engine = create_engine(
        f"mysql+pymysql://{username}:{password}@{url}/empire", echo=False
    )
else:
    location = database_config.location
    engine = create_engine(
        f"sqlite:///{location}",
        connect_args={
            "check_same_thread": False,
            # "timeout": 3000
        },
        echo=False,
    )

SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)


def reset_db():
    Base.metadata.drop_all(engine)
    if database_config.type == "sqlite":
        os.unlink(database_config.location)


with SessionLocal.begin() as db:
    # When Empire starts up for the first time, it will create the database and create
    # these default records.
    if len(db.query(models.User).all()) == 0:
        log.info("Setting up database.")
        log.info("Adding default user.")
        db.add(get_default_user())

    if len(db.query(models.Config).all()) == 0:
        log.info("Adding database config.")
        db.add(get_default_config())

    if len(db.query(models.Keyword).all()) == 0:
        log.info("Adding default keyword obfuscation functions.")
        keywords = get_default_keyword_obfuscation()

        for keyword in keywords:
            db.add(keyword)

    if len(db.query(models.ObfuscationConfig).all()) == 0:
        log.info("Adding default obfuscation config.")
        obf_configs = get_default_obfuscation_config()

        for config in obf_configs:
            db.add(config)
