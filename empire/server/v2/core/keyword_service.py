from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.database.base import SessionLocal


class KeywordService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_all(db: Session):
        return db.query(models.Keyword).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Keyword).filter(models.Keyword.id == uid).first()

    @staticmethod
    def get_by_keyword(db: Session, keyword: str):
        return (
            db.query(models.Keyword).filter(models.Keyword.keyword == keyword).first()
        )

    @staticmethod
    def delete_keyword(db: Session, keyword: models.Keyword):
        db.delete(keyword)

    def create_keyword(self, db: Session, keyword_req):
        if self.get_by_keyword(db, keyword_req.keyword):
            return None, f"Keyword with name {keyword_req.keyword} already exists."

        db_keyword = models.Keyword(
            keyword=keyword_req.keyword, replacement=keyword_req.replacement
        )

        db.add(db_keyword)
        db.flush()

        return db_keyword, None

    def update_keyword(self, db: Session, db_keyword: models.Keyword, keyword_req):
        if keyword_req.keyword != db_keyword.keyword:
            if not self.get_by_keyword(db, keyword_req.keyword):
                db_keyword.keyword = keyword_req.keyword
            else:
                return None, f"Keyword with name {keyword_req.keyword} already exists."

        db_keyword.replacement = keyword_req.replacement

        db.flush()

        return db_keyword, None
