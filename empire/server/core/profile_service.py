import fnmatch
import logging
import typing

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

        with SessionLocal.begin() as db:
            self.load_malleable_profiles(db)

    def load_malleable_profiles(self, db: Session):
        """
        Load Malleable C2 Profiles to the database
        """
        malleable_path = self.main_menu.install_path / "data/profiles"
        log.info(f"v2: Loading malleable profiles from: {malleable_path}")

        # Pre-load existing profile names once instead of issuing a
        # SELECT per file (mirrors module_service.load_modules).
        db_existing_names = set(db.scalars(select(models.Profile.name)).all())
        added_in_loop: dict[str, str] = {}

        # Filtered before the loop so the emptiness check below is about files
        # on disk. A tree holding only template.profile is an unusable install,
        # not one profile. Sorted because rglob yields in directory order: two
        # categories holding the same basename would otherwise resolve to a
        # different winner on different machines, since the loop keeps the first.
        profile_files = sorted(
            path
            for path in malleable_path.rglob("*.profile")
            if not fnmatch.fnmatch(path.name, "*template.profile")
        )

        # Keyed on files, not rows inserted -- a normal restart legitimately
        # inserts nothing because the database is already full. Both branches
        # log at ERROR: the shipped tree is missing either way. An install that
        # manages profiles only through the API is the false positive, and one
        # log line is the right price for catching an empty release archive.
        if not profile_files:
            if db_existing_names:
                log.error(
                    "No malleable profiles found on disk under %s; the %d already in the "
                    "database are now the only copy. Restore the directory before "
                    "resetting profiles or creating a new database, or both will leave "
                    "you with none.",
                    malleable_path,
                    len(db_existing_names),
                )
            else:
                log.error(
                    "No malleable profiles found under %s and none in the database, so "
                    "malleable listeners have none to select. Restore the directory from "
                    "a git clone or a release archive that ships it, or add a profile "
                    "through the Malleable Profiles UI.",
                    malleable_path,
                )

        category_and_name_depth = 2
        for file_path in profile_files:
            malleable_split = file_path.relative_to(malleable_path).parts
            # README.md in this directory tells operators to drop new profiles
            # in, so a misplaced one is reachable. Unguarded, a root-level file
            # IndexErrors the whole boot and a nested one silently registers the
            # subdirectory's name as the profile.
            if len(malleable_split) != category_and_name_depth:
                log.warning(
                    "Skipping malleable profile %s; profiles must live at "
                    "<Category>/<name>.profile under %s",
                    file_path,
                    malleable_path,
                )
                continue
            profile_category, profile_name = malleable_split

            if profile_name in db_existing_names:
                continue
            if profile_name in added_in_loop:
                log.warning(
                    "Duplicate malleable profile name %r at %s; keeping first occurrence at %s",
                    profile_name,
                    file_path,
                    added_in_loop[profile_name],
                )
                continue

            log.debug(f"Adding malleable profile: {profile_name}")
            try:
                profile_data = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                # The decode error carries a byte offset but no filename, so an
                # operator who saved a profile as CP1252 would otherwise have to
                # bisect the tree to find which one broke startup.
                raise ValueError(f"{file_path} is not valid UTF-8") from e
            db.add(
                models.Profile(
                    file_path=str(file_path),
                    name=profile_name,
                    category=profile_category,
                    data=profile_data,
                )
            )
            added_in_loop[profile_name] = str(file_path)

    @staticmethod
    def get_all(db: Session):
        return db.scalars(select(models.Profile)).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.scalars(
            select(models.Profile).where(models.Profile.id == uid)
        ).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.scalars(
            select(models.Profile).where(models.Profile.name == name)
        ).first()

    @staticmethod
    def delete_profile(db: Session, profile: models.Profile):
        db.delete(profile)

    def create_profile(self, db: Session, profile_req):
        if self.get_by_name(db, profile_req.name):
            return (
                None,
                f"Malleable Profile with name {profile_req.name} already exists.",
            )

        profile = models.Profile(
            name=profile_req.name, category=profile_req.category, data=profile_req.data
        )

        db.add(profile)
        db.flush()

        return profile, None

    @staticmethod
    def update_profile(db: Session, db_profile: models.Profile, profile_req):
        db_profile.data = profile_req.data
        db.flush()

        return db_profile, None

    @staticmethod
    def delete_all_profiles(db: Session):
        db.execute(delete(models.Profile))
        db.flush()
