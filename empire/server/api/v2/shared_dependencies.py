from empire.server.core.db.base import SessionLocal


def get_db():
    with SessionLocal.begin() as db:
        yield db
