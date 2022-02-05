from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from empire.server.database import models


class CredentialService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_all(db: Session):
        return db.query(models.Credential).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Credential).filter(models.Credential.id == uid).first()

    @staticmethod
    def delete_credential(db: Session, credential: models.Credential):
        db.delete(credential)

    @staticmethod
    def create_credential(db: Session, credential_dto):
        credential = models.Credential(**credential_dto.dict())

        try:
            db.add(credential)

            db.flush()

            return credential, None
        except IntegrityError:
            return None, "Credential not created. Duplicate detected."

    @staticmethod
    def update_credential(
        db: Session, db_credential: models.Credential, credential_req
    ):
        db_credential.credtype = credential_req.credtype
        db_credential.domain = credential_req.domain
        db_credential.username = credential_req.username
        db_credential.password = credential_req.password
        db_credential.host = credential_req.host
        db_credential.os = credential_req.os
        db_credential.sid = credential_req.sid
        db_credential.notes = credential_req.notes

        try:
            db.flush()

            return db_credential, None
        except IntegrityError:
            return None, "Credential not updated. Duplicate detected."
