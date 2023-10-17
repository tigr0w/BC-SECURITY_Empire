import os
import shutil
from operator import and_
from pathlib import Path
from typing import List, Optional, Tuple, Union

from fastapi import UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from empire.server.api.v2.download.download_dto import (
    DownloadOrderOptions,
    DownloadSourceFilter,
)
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.config import empire_config
from empire.server.core.db import models


class DownloadService:
    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Download).filter(models.Download.id == uid).first()

    @staticmethod
    def get_all(
        db: Session,
        download_types: Optional[List[DownloadSourceFilter]],
        tags: List[str] = None,
        q: str = None,
        limit: int = -1,
        offset: int = 0,
        order_by: DownloadOrderOptions = DownloadOrderOptions.updated_at,
        order_direction: OrderDirection = OrderDirection.desc,
    ) -> Tuple[List[models.Download], int]:
        query = db.query(
            models.Download, func.count(models.Download.id).over().label("total")
        )

        download_types = download_types or []
        sub = []
        if DownloadSourceFilter.agent_task in download_types:
            sub.append(
                db.query(
                    models.agent_task_download_assc.c.download_id.label("download_id")
                )
            )
        if DownloadSourceFilter.agent_file in download_types:
            sub.append(
                db.query(
                    models.agent_file_download_assc.c.download_id.label("download_id")
                )
            )
        if DownloadSourceFilter.stager in download_types:
            sub.append(
                db.query(models.stager_download_assc.c.download_id.label("download_id"))
            )
        if DownloadSourceFilter.upload in download_types:
            sub.append(
                db.query(models.upload_download_assc.c.download_id.label("download_id"))
            )

        subquery = None
        if len(sub) > 0:
            subquery = sub[0]
            if len(sub) > 1:
                subquery = subquery.union(*sub[1:])
            subquery = subquery.subquery()

        if subquery is not None:
            query = query.join(subquery, subquery.c.download_id == models.Download.id)

        if q:
            query = query.filter(
                or_(
                    models.Download.filename.like(f"%{q}%"),
                    models.Download.location.like(f"%{q}%"),
                )
            )

        if tags:
            tags_split = [tag.split(":", 1) for tag in tags]
            query = query.join(models.Download.tags).filter(
                and_(
                    models.Tag.name.in_([tag[0] for tag in tags_split]),
                    models.Tag.value.in_([tag[1] for tag in tags_split]),
                )
            )

        if order_by == DownloadOrderOptions.filename:
            order_by_prop = func.lower(models.Download.filename)
        elif order_by == DownloadOrderOptions.location:
            order_by_prop = func.lower(models.Download.location)
        elif order_by == DownloadOrderOptions.size:
            order_by_prop = models.Download.size
        elif order_by == DownloadOrderOptions.created_at:
            order_by_prop = models.Download.created_at
        else:
            order_by_prop = models.Download.updated_at

        if order_direction == OrderDirection.asc:
            query = query.order_by(order_by_prop.asc())
        else:
            query = query.order_by(order_by_prop.desc())

        if limit > 0:
            query = query.limit(limit).offset(offset)

        results = query.all()

        total = 0 if len(results) == 0 else results[0].total
        results = list(map(lambda x: x[0], results))

        return results, total

    def create_download_from_text(
        self,
        db: Session,
        user: models.User,
        file: str,
        filename: str,
        subdirectory: Optional[str] = None,
    ):
        """
        Upload the file to the downloads directory and save a reference to the db.
        If a subdirectory is supplied, it will use that, otherwise it will use the user
        """
        subdirectory = subdirectory or f"user/{user.username}"
        location = (
            Path(empire_config.directories.downloads)
            / "uploads"
            / subdirectory
            / filename
        )
        location.parent.mkdir(parents=True, exist_ok=True)

        filename, location = self._increment_filename(filename, location)

        with location.open("w") as buffer:
            buffer.write(file)

        return self._save_download(db, filename, location)

    def create_download(
        self, db: Session, user: models.User, file: Union[UploadFile, Path]
    ):
        """
        Upload the file to the downloads directory and save a reference to the db.
        :param db:
        :param user:
        :param file:
        :return:
        """
        if isinstance(file, Path):
            filename = file.name
        else:
            filename = file.filename

        location = (
            Path(empire_config.directories.downloads)
            / "uploads"
            / user.username
            / filename
        )
        location.parent.mkdir(parents=True, exist_ok=True)

        filename, location = self._increment_filename(filename, location)

        with location.open("wb") as buffer:
            if isinstance(file, Path):
                with file.open("rb") as f:
                    shutil.copyfileobj(f, buffer)
            else:
                shutil.copyfileobj(file.file, buffer)

        return self._save_download(db, filename, location)

    @staticmethod
    def _increment_filename(filename, location):
        filename, file_extension = os.path.splitext(filename)
        i = 1
        while os.path.isfile(location):
            temp_name = f"{filename}({i}){file_extension}"
            location = location.parent / temp_name
            i += 1
        filename = location.name

        return filename, location

    @staticmethod
    def _save_download(db, filename, location):
        download = models.Download(
            location=str(location), filename=filename, size=os.path.getsize(location)
        )
        db.add(download)
        db.flush()
        db.execute(models.upload_download_assc.insert().values(download_id=download.id))

        return download
