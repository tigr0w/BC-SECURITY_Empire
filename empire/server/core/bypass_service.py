import fnmatch
import logging
import os

import yaml
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.utils.data_util import ps_convert_to_oneliner

log = logging.getLogger(__name__)


class BypassService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

        with SessionLocal.begin() as db:
            self.load_bypasses(db)

    def load_bypasses(self, db: Session):
        root_path = f"{self.main_menu.installPath}/bypasses/"
        log.info(f"v2: Loading bypasses from: {root_path}")

        for root, dirs, files in os.walk(root_path):
            for filename in files:
                if not filename.lower().endswith(
                    ".yaml"
                ) and not filename.lower().endswith(".yml"):
                    continue

                file_path = os.path.join(root, filename)

                # don't load up any of the templates
                if fnmatch.fnmatch(filename, "*template.yaml"):
                    continue

                try:
                    with open(file_path, "r") as stream:
                        yaml2 = yaml.safe_load(stream)
                        yaml_bypass = {k: v for k, v in yaml2.items() if v is not None}

                        if (
                            db.query(models.Bypass)
                            .filter(models.Bypass.name == yaml_bypass["name"])
                            .first()
                            is None
                        ):
                            yaml_bypass["script"] = ps_convert_to_oneliner(
                                yaml_bypass["script"]
                            )
                            my_model = models.Bypass(
                                name=yaml_bypass["name"],
                                authors=yaml_bypass["authors"],
                                code=yaml_bypass["script"],
                                language=yaml_bypass["language"],
                            )
                            db.add(my_model)
                except Exception as e:
                    log.error(e)

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
            return None, f"Bypass with name {bypass_req.name} already exists."

        bypass = models.Bypass(
            name=bypass_req.name, code=bypass_req.code, language=bypass_req.language
        )

        db.add(bypass)
        db.flush()

        return bypass, None

    def update_bypass(self, db: Session, db_bypass: models.Bypass, bypass_req):
        if bypass_req.name != db_bypass.name:
            if not self.get_by_name(db, bypass_req.name):
                db_bypass.name = bypass_req.name
            else:
                return None, f"Bypass with name {bypass_req.name} already exists."

        db_bypass.code = bypass_req.code
        db_bypass.language = bypass_req.language

        db.flush()

        return db_bypass, None

    def delete_all_bypasses(self, db: Session):
        db.query(models.Bypass).delete()
        db.flush()
