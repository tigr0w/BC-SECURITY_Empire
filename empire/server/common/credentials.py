"""

Credential handling functionality for Empire.

"""
import logging
import warnings

from sqlalchemy import and_, or_

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal

log = logging.getLogger(__name__)


class Credentials:
    """
    Class that handles interaction with the backend credential model
    (adding creds, displaying, etc.).
    """

    def __init__(self, MainMenu, args=None):
        # pull out the controller objects
        self.mainMenu = MainMenu
        self.installPath = self.mainMenu.installPath
        self.args = args

        # credential database schema:
        #   (ID, credtype, domain, username, password, host, OS, notes, sid)
        # credtype = hash or plaintext
        # sid is stored for krbtgt

    def is_credential_valid(self, credentialID):
        """
        Check if this credential ID is valid.
        """
        warnings.warn(
            "This has been deprecated and may be removed. Use credential_service.get_by_id() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal() as db:
            if (
                db.query(models.Credential)
                .filter(models.Credential.id == credentialID)
                .first()
            ):
                return True

        return False

    def get_credentials(self, filter_term=None, credtype=None, note=None, os=None):
        """
        Return credentials from the database.

        'credtype' can be specified to return creds of a specific type.
        Values are: hash, plaintext, and token.
        """
        warnings.warn(
            "This has been deprecated and may be removed. Use credential_service.get_all().",
            DeprecationWarning,
            stacklevel=2,
        )
        # if we're returning a single credential by ID
        with SessionLocal() as db:
            if self.is_credential_valid(filter_term):
                results = (
                    db.query(models.Credential)
                    .filter(models.Credential.id == filter_term)
                    .first()
                )

            # if we're filtering by host/username
            elif filter_term and filter_term != "":
                filter_term = filter_term.replace("*", "%")
                search = f"%{filter_term}%"
                results = (
                    db.query(models.Credential)
                    .filter(
                        or_(
                            models.Credential.domain.like(search),
                            models.Credential.username.like(search),
                            models.Credential.host.like(search),
                            models.Credential.password.like(search),
                        )
                    )
                    .all()
                )

            # if we're filtering by credential type (hash, plaintext, token)
            elif credtype and credtype != "":
                results = (
                    db.query(models.Credential)
                    .filter(models.Credential.credtype.ilike("%credtype%"))
                    .all()
                )

            # if we're filtering by content in the note field
            elif note and note != "":
                search = f"%{note}%"
                results = (
                    db.query(models.Credential)
                    .filter(models.Credential.note.ilike("%search%"))
                    .all()
                )

            # if we're filtering by content in the OS field
            elif os and os != "":
                search = f"%{os}%"
                results = (
                    db.query(models.Credential)
                    .filter(models.Credential.os.ilike("%search%"))
                    .all()
                )

            # otherwise return all credentials
            else:
                results = db.query(models.Credential).all()

            return results

    def add_credential(
        self, credtype, domain, username, password, host, os="", sid="", notes=""
    ):
        """
        Add a credential with the specified information to the database.
        """
        warnings.warn(
            "This has been deprecated and may be removed. Use credential_service.create_credential().",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal.begin() as db:
            results = (
                db.query(models.Credential)
                .filter(
                    and_(
                        models.Credential.credtype.like(credtype),
                        models.Credential.domain.like(domain),
                        models.Credential.username.like(username),
                        models.Credential.password.like(password),
                    )
                )
                .all()
            )

            if len(results) == 0:
                credential = models.Credential(
                    credtype=credtype,
                    domain=domain,
                    username=username,
                    password=password,
                    host=host,
                    os=os,
                    sid=sid,
                    notes=notes,
                )
                db.add(credential)
                db.flush()
