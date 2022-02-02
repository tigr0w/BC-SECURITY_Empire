import os
import shutil

from fastapi import UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from empire.server.database import models


class DownloadService(object):

    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Download).filter(models.Download.id == uid).first()

    @staticmethod
    def get_all(db: Session, q: str):
        query = db.query(models.Download)

        if q:
            query = query\
                .filter(or_(models.Download.filename.like(f'%{q}%'),
                            models.Download.location.like(f'%{q}%')))\

        return query.all()

    @staticmethod
    def create_download(db: Session, file: UploadFile):
        """
        Upload the file to the downloads directory and save a reference to the db.
        :param db:
        :param file:
        :return:
        """
        location = f'{db.query(models.Config).first().install_path}/downloads/{file.filename}'
        with open(location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        download = models.Download(location=location, filename=file.filename, size=os.path.getsize(location))
        db.add(download)

        return download
