import logging
import typing

import netaddr
from netaddr.ip.sets import IPSet
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import IpList
from empire.server.core.hooks import hooks

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class IpService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.agent_task_service = main_menu.agenttasksv2

        hooks.register_hook(
            hooks.AFTER_AGENT_CHECKIN_HOOK, "ip_allowed_hook", self.is_ip_allowed_hook
        )

        with SessionLocal.begin() as db:
            self.ip_filtering = db.query(models.Config.ip_filtering).first()[0]
            self.deny_list = self._to_ip_set(self.get_all(db, IpList.deny))
            self.allow_list = self._to_ip_set(self.get_all(db, IpList.allow))

    @staticmethod
    def _to_ip_set(ip_list: list[models.IP]) -> netaddr.IPSet:
        ip_set = netaddr.IPSet()

        for ip in ip_list:
            if "-" in ip.ip_address:
                split = ip.ip_address.split("-")
                ip_set.add(netaddr.IPRange(split[0], split[1]))
            elif "/" in ip.ip_address:
                ip_set.add(netaddr.IPNetwork(ip.ip_address))
            else:
                ip_set.add(netaddr.IPAddress(ip.ip_address))

        return ip_set

    def is_ip_allowed(self, ip_address):
        """
        If no allow list or deny list is set, then all IPs are allowed.
        If only allow list is set, then only IPs in the allow list are allowed.
        If only a deny list is set, then only IPs not in the deny list are allowed.
        If both an allow list and a deny list are set, then IPs in the deny list are not
        allowed, but allow listed IPs take precedence over deny listed IPs.
        """
        if not self.ip_filtering:
            return True

        ip_address = netaddr.IPAddress(ip_address)

        if not self.allow_list and not self.deny_list:
            return True

        if self.allow_list and self._ip_is_in(ip_address, self.allow_list):
            return True

        if self.deny_list and self._ip_is_in(ip_address, self.deny_list):
            return False

        return not (self.allow_list and not self._ip_is_in(ip_address, self.allow_list))

    def _ip_is_in(self, ip_address: str | netaddr.IPAddress, ip_list: IPSet):
        if isinstance(ip_address, str):
            ip_address = netaddr.IPAddress(ip_address)

        ip_address = netaddr.IPAddress(ip_address)

        return ip_address in ip_list

    @staticmethod
    def get_all(db: Session, ip_list: IpList = None) -> list[models.IP]:
        query = db.query(models.IP)

        if ip_list:
            query = query.filter(models.IP.list == ip_list)

        return query.all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.IP).filter(models.IP.id == uid).first()

    def create_ip(self, db: Session, ip_address: str, list: str):
        db_ip = models.IP(ip_address=ip_address, list=list)
        db.add(db_ip)
        db.flush()

        return db_ip

    def delete_ip(self, db: Session, db_ip: models.IP):
        db.delete(db_ip)

    def toggle_ip_filtering(self, db: Session, enable: bool):
        db.query(models.Config).update({"ip_filtering": enable})
        self.ip_filtering = enable

    def is_ip_allowed_hook(self, db: Session, agent: models.Agent):
        if self.is_ip_allowed(agent.external_ip) and self.is_ip_allowed(
            agent.internal_ip
        ):
            return

        log.info(f"Exiting agent {agent.name} due to IP not being allowed.")
        self.agent_task_service.create_task_exit(db, agent, current_user_id=0)
