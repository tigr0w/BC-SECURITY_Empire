from sqlalchemy.orm import Session

from empire.server.database import models


class BypassService(object):

    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_all(db: Session):
        return db.query(models.Bypass).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Bypass).filter(models.Bypass.id == uid).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.query(models.Bypass).filter(models.Bypass.name == name).first()

    @staticmethod
    def delete_bypass(db: Session, bypass: models.Bypass):
        db.delete(bypass)

    def create_bypass(self, db: Session, bypass_req):
        if self.get_by_name(db, bypass_req.name):
            return None, f'Bypass with name {bypass_req.name} already exists.'

        bypass = models.Bypass(name=bypass_req.name, code=bypass_req.code)

        db.add(bypass)
        db.flush()

        return bypass, None

    def update_bypass(self, db: Session, db_bypass: models.Bypass, bypass_req):
        if bypass_req.name != db_bypass.name:
            if not self.get_by_name(db, bypass_req.name):
                db_bypass.name = bypass_req.name
            else:
                return None, f'Bypass with name {bypass_req.name} already exists.'

        db_bypass.code = bypass_req.code

        db.flush()

        return db_bypass, None
