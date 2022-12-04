import logging
import os
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
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


# https://stackoverflow.com/a/13719230
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if type(dbapi_connection) is sqlite3.Connection:  # play well with other DB backends
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


def try_connect(engine_url: str, *args, **kwargs) -> Connection:
    try:
        engine = create_engine(engine_url, *args, **kwargs)
        connection = engine.connect()
    except OperationalError:
        log.error(f"Failed connecting to database using {engine_url}")
        log.error("Perhaps the MySQL service is not running.")
        log.error("Try executing: sudo systemctl mysql start")
        exit(1)

    return connection


database_config = empire_config.database

use = os.environ.get("DATABASE_USE", database_config.use)
database_config.use = use

database_config = database_config[use.lower()]

if use == "mysql":
    url = database_config.url
    username = database_config.username
    password = database_config.password
    database_name = database_config.database_name
    connection = try_connect(f"mysql+pymysql://{username}:{password}@{url}", echo=False)
    text = (
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
        "WHERE SCHEMA_NAME = '%s'" % database_name
    )

    result = connection.scalar(text)
    if not result:
        connection.execute(f"CREATE DATABASE {database_name}")

    connection.close()

    connection = try_connect(
        f"mysql+pymysql://{username}:{password}@{url}/{database_name}", echo=False
    )
else:
    location = database_config.location
    connection = try_connect(
        f"sqlite:///{location}",
        connect_args={
            "check_same_thread": False,
            # "timeout": 3000
        },
        echo=False,
    )

SessionLocal = sessionmaker(bind=connection)

Base.metadata.create_all(connection)


def reset_db():
    SessionLocal.close_all()
    Base.metadata.drop_all(connection)
    if use == "sqlite":
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
