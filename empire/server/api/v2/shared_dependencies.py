from empire.server.database.base import SessionLocal


def get_db():
    with SessionLocal.begin() as db:
        yield db
