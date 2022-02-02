import fnmatch
import json
import os

from pydispatch import dispatcher
from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.database import models
from empire.server.database.base import SessionLocal


class ProfileService(object):

    def __init__(self, main_menu):
        self.main_menu = main_menu

        with SessionLocal.begin() as db:
            self.load_malleable_profiles(db)

    @staticmethod
    def load_malleable_profiles(db: Session):
        """
        Load Malleable C2 Profiles to the database
        """
        malleable_path = f"{db.query(models.Config).first().install_path}/data/profiles/"
        print(helpers.color(f"[*] v2: Loading malleable profiles from: {malleable_path}"))

        malleable_directories = os.listdir(malleable_path)

        for malleable_directory in malleable_directories:
            for root, dirs, files in os.walk(malleable_path + '/' + malleable_directory):
                for filename in files:
                    if not filename.lower().endswith('.profile'):
                        continue

                    file_path = os.path.join(root, filename)

                    # don't load up any of the templates
                    if fnmatch.fnmatch(filename, '*template.profile'):
                        continue

                    malleable_split = file_path.split(malleable_path)[-1].split('/')
                    profile_category = malleable_split[1]
                    profile_name = malleable_split[2]

                    # Check if module is in database and load new profiles
                    profile = db.query(models.Profile).filter(models.Profile.name == profile_name).first()
                    if not profile:
                        message = "[*] Loading malleable profile {}".format(profile_name)
                        signal = json.dumps({
                            'print': False,
                            'message': message
                        })
                        # dispatcher.send(signal, sender="empire")

                        with open(file_path, 'r') as stream:
                            profile_data = stream.read()
                            db.add(models.Profile(file_path=file_path,
                                                  name=profile_name,
                                                  category=profile_category,
                                                  data=profile_data,
                                                  ))

    @staticmethod
    def get_all(db: Session):
        return db.query(models.Profile).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Profile).filter(models.Profile.id == uid).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.query(models.Profile).filter(models.Profile.name == name).first()

    @staticmethod
    def delete_profile(db: Session, profile: models.Profile):
        db.delete(profile)

    def create_profile(self, db: Session, profile_req):
        if self.get_by_name(db,profile_req.name):
            return None, f'Malleable Profile with name {profile_req.name} already exists.'

        profile = models.Profile(name=profile_req.name, category=profile_req.category, data=profile_req.data)

        db.add(profile)
        db.flush()

        return profile, None

    @staticmethod
    def update_profile(db: Session, db_profile: models.Profile, profile_req):
        db_profile.data = profile_req.data
        db.flush()

        return db_profile, None
