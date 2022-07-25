import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

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


class DownloadService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Download).filter(models.Download.id == uid).first()

    @staticmethod
    def get_all(
        db: Session,
        download_types: Optional[List[DownloadSourceFilter]],
        q: str,
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
                    models.tasking_download_assc.c.download_id.label("download_id")
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

    def create_download(self, db: Session, user: models.User, file: UploadFile):
        """
        Upload the file to the downloads directory and save a reference to the db.
        :param db:
        :param user:
        :param file:
        :return:
        """
        filename = file.filename

        location = (
            Path(empire_config.directories.downloads)
            / "uploads"
            / user.username
            / filename
        )
        location.parent.mkdir(parents=True, exist_ok=True)

        # append number to filename if it already exists
        filename, file_extension = os.path.splitext(filename)
        i = 1
        while os.path.isfile(location):
            temp_name = f"{filename}({i}){file_extension}"
            location = (
                Path(empire_config.directories.downloads)
                / "uploads"
                / user.username
                / temp_name
            )
            i += 1
        filename = location.name

        with location.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        download = models.Download(
            location=str(location), filename=filename, size=os.path.getsize(location)
        )
        db.add(download)
        db.flush()
        db.execute(models.upload_download_assc.insert().values(download_id=download.id))

        return download
