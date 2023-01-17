import logging
import os
import sqlite3

from sqlalchemy import UniqueConstraint, create_engine, event, text
from sqlalchemy.engine import Engine
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


def try_create_engine(engine_url: str, *args, **kwargs) -> Engine:
    engine = create_engine(engine_url, *args, **kwargs)
    try:
        with engine.connect() as connection:
            pass
    except OperationalError:
        log.error(f"Failed connecting to database using {engine_url}")
        log.error("Perhaps the MySQL service is not running.")
        log.error("Try executing: sudo systemctl start mysql")
        exit(1)

    return engine


def reset_db():
    SessionLocal.close_all()
    Base.metadata.drop_all(engine)
    if use == "sqlite":
        os.unlink(database_config.location)


database_config = empire_config.database
use = os.environ.get("DATABASE_USE", database_config.use)
database_config.use = use
database_config = database_config[use.lower()]

if use == "mysql":
    url = database_config.url
    username = database_config.username
    password = database_config.password
    database_name = database_config.database_name
    mysql_url = f"mysql+pymysql://{username}:{password}@{url}"
    engine = try_create_engine(mysql_url, echo=False)
    with engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE IF NOT EXISTS {database_name}"))
    engine = try_create_engine(f"{mysql_url}/{database_name}", echo=False)
else:
    location = database_config.location
    engine = try_create_engine(
        f"sqlite:///{location}",
        connect_args={
            "check_same_thread": False,
        },
        echo=False,
    )

    models.Host.__table_args__ = (
        UniqueConstraint(
            models.Host.name, models.Host.internal_ip, name="host_unique_idx"
        ),
    )

SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

with SessionLocal.begin() as db:
    if use == "mysql":
        database_name = database_config.database_name

        result = db.execute(
            f"""
            SELECT * FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = '{database_name}'
            AND table_name = 'hosts'
            AND column_name = 'unique_check'
            """
        ).fetchone()
        if not result:
            db.execute(
                """
                ALTER TABLE hosts
                ADD COLUMN unique_check VARCHAR(255) GENERATED ALWAYS AS (MD5(CONCAT(name, internal_ip))) UNIQUE;
                """
            )

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
