import base64
import logging
import struct
import time
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from empire.server.common.empire import MainMenu
from empire.server.utils.string_util import is_valid_session_id

log = logging.getLogger(__name__)


# Copied from the agent.py file for Python agent
class compress:
    """
    Base clase for init of the package. This will handle
    the initial object creation for conducting basic functions.
    """

    CRC_HSIZE = 4
    COMP_RATIO = 9

    def __init__(self, verbose=False):
        """
        Populates init.
        """
        pass

    def comp_data(self, data, cvalue=COMP_RATIO):
        """
        Takes in a string and computes
        the comp obj.
        data = string wanting compression
        cvalue = 0-9 comp value (default 6)
        """
        cdata = zlib.compress(data, cvalue)
        return cdata

    def crc32_data(self, data):
        """
        Takes in a string and computes crc32 value.
        data = string before compression
        returns:
        HEX bytes of data
        """
        crc = zlib.crc32(data) & 0xFFFFFFFF
        return crc

    def build_header(self, data, crc):
        """
        Takes comp data, org crc32 value,
        and adds self header.
        data =  comp data
        crc = crc32 value
        """
        header = struct.pack("!I", crc)
        built_data = header + data
        return built_data


@pytest.fixture(scope="function", autouse=True)
def agents(session_local, models, host):
    with session_local.begin() as db:
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        agent = models.Agent(
            name="TEST123",
            session_id="TEST123",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        agent2 = models.Agent(
            name="SECOND",
            session_id="SECOND",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        agent3 = models.Agent(
            name="archived",
            session_id="archived",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=True,
        )

        agent4 = models.Agent(
            name="STALE",
            session_id="STALE",
            delay=1,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        db.add(agent)
        db.add(agent2)
        db.add(agent3)
        db.add(agent4)
        db.add(models.AgentCheckIn(agent_id=agent.session_id))
        db.add(models.AgentCheckIn(agent_id=agent2.session_id))
        db.add(models.AgentCheckIn(agent_id=agent3.session_id))
        db.add(
            models.AgentCheckIn(
                agent_id=agent4.session_id,
                checkin_time=datetime.now(UTC) - timedelta(days=2),
            )
        )
        db.flush()
        agents = [agent, agent2, agent3, agent4]

        agent_ids = [agent.session_id for agent in agents]

    yield agent_ids

    with session_local.begin() as db:
        db.query(models.Agent).delete()


def test_stale_expression(empire_config):
    from empire.server.core.db import models
    from empire.server.core.db.base import SessionLocal

    db = SessionLocal()

    # assert all 4 agents are in the database
    agents = db.query(models.Agent).all()
    assert len(agents) == 4

    # assert one of the agents is stale via its hybrid property
    assert any(agent.stale for agent in agents)

    # assert we can filter on stale via the hybrid expression
    stale = (
        db.query(models.Agent).filter(models.Agent.stale == True).all()  # noqa: E712
    )
    assert len(stale) == 1

    # assert we can filter on stale via the hybrid expression
    not_stale = (
        db.query(models.Agent).filter(models.Agent.stale == False).all()  # noqa: E712
    )
    assert len(not_stale) == 3


def test_large_internal_ip_works(session_local, host, models, agent):
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        db_agent.internal_ip = "192.168.1.75 fe90::51e7:5dc7:be5d:b22e 3600:1900:7bb0:90d0:4d3c:2cd6:3fe:883b 5600:1900:3aa0:80d1:18a4:4431:5023:eef7 6600:1500:1aa0:20d0:fd69:26ff:5c4c:8d27 2900:2700:4aa0:80d0::47 192.168.214.1 fe90::a24c:82de:578b:8626 192.168.245.1 fe00::f321:a1e:18d3:ab9"

        db.flush()

        db_host.internal_ip = db_agent.internal_ip

        db.flush()


def test_duplicate_host(session_local, models, host):
    with pytest.raises(IntegrityError), session_local.begin() as db:
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        host2 = models.Host(name=db_host.name, internal_ip=db_host.internal_ip)

        db.add(host2)
        db.flush()


def test_duplicate_checkin_raises_exception(session_local, models, agent):
    with pytest.raises(IntegrityError), session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        timestamp = datetime.now(UTC)
        checkin = models.AgentCheckIn(
            agent_id=db_agent.session_id, checkin_time=timestamp
        )
        checkin2 = models.AgentCheckIn(
            agent_id=db_agent.session_id, checkin_time=timestamp
        )

        db.add(checkin)
        db.add(checkin2)
        db.flush()


def test_can_ignore_duplicate_checkins(session_local, models, agent, main):
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        prev_checkin_count = len(db_agent.checkins.all())
        # Need to ensure that these two checkins are not the same second
        # as the original checkin
        time.sleep(2)

        main.agentsv2.update_agent_lastseen(db, db_agent.session_id)
        main.agentsv2.update_agent_lastseen(db, db_agent.session_id)

    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        checkin_count = len(db_agent.checkins.all())

        assert checkin_count == prev_checkin_count + 1


def test_update_dir_list(session_local, models, agent, main: MainMenu):
    with session_local.begin() as db:
        message = {
            "directory_path": "C:\\",
            "directory_name": "C:\\",
            "items": [
                {
                    "path": "C:\\Users\\vinnybod\\Desktop\\test.txt",
                    "name": "test.txt",
                    "is_file": True,
                },
                {
                    "path": "C:\\Users\\vinnybod\\Desktop\\test2.txt",
                    "name": "test2.txt",
                    "is_file": True,
                },
            ],
        }
        main.agentcommsv2._update_dir_list(db, agent, message)

        file, _ = main.agentfilesv2.get_file_by_path(
            db, agent, "C:\\Users\\vinnybod\\Desktop\\test.txt"
        )

        assert file.path == "C:\\Users\\vinnybod\\Desktop\\test.txt"
        assert file.name == "test.txt"
        assert file.is_file is True
        assert file.parent_id is not None

        db.query(models.AgentFile).delete()


def test_update_dir_list_with_existing_joined_file(
    session_local, models, agent, main: MainMenu, empire_config
):
    with session_local.begin() as db:
        message = {
            "directory_path": "C:\\",
            "directory_name": "C:\\",
            "items": [
                {
                    "path": "C:\\Users\\vinnybod\\Desktop\\test.txt",
                    "name": "test.txt",
                    "is_file": True,
                },
                {
                    "path": "C:\\Users\\vinnybod\\Desktop\\test2.txt",
                    "name": "test2.txt",
                    "is_file": True,
                },
            ],
        }
        main.agentcommsv2._update_dir_list(db, agent, message)

        file, _ = main.agentfilesv2.get_file_by_path(
            db, agent, "C:\\Users\\vinnybod\\Desktop\\test.txt"
        )

        download_path = Path("empire/test/avatar.png")
        file.downloads.append(
            models.Download(
                location=str(download_path.absolute()),
                filename=download_path.name,
                size=download_path.stat().st_size,
            )
        )

        # This previously raised a Foreign Key Constraint error, but should succeed now.
        main.agentcommsv2._update_dir_list(db, agent, message)

        file2, _ = main.agentfilesv2.get_file_by_path(
            db, agent, "C:\\Users\\vinnybod\\Desktop\\test.txt"
        )

        if empire_config.database.use != "sqlite":
            # sqlite reuses ids and apparently doesn't cascade the delete to the
            # association table. This can result in files being linked to the wrong
            # download after refreshing a directory for sqlite.
            assert file.id != file2.id
            assert len(file2.downloads) == 0

        assert file.name == file2.name

        db.query(models.AgentFile).delete()


@pytest.mark.parametrize(
    "session_id,expected",
    [
        ("ABCDEFGH", True),
        ("12345678", True),
        ("ABCDEF1H", True),
        ("A1B2C3D4", True),
        ("ABCDEFG", False),
        ("ABCDEFGHI", False),
        ("ABCD_EFG", False),
        ("       ", False),
        ("", False),
        (12345678, False),
        (None, False),
        ("./../../", False),
    ],
)
def test_is_valid_session_id(session_id, expected):
    assert (
        is_valid_session_id(session_id) == expected
    ), f"Test failed for session_id: {session_id}"


def test_skywalker_exploit_protection(caplog, agent, db, main: MainMenu):
    # Malicious file path attempting directory traversal
    malicious_directory = (
        main.installPath + r"/downloads/..\\..\\..\\..\\..\\etc\\cron.d\\evil"
    )
    encodedPart = b"test"
    c = compress()
    start_crc32 = c.crc32_data(encodedPart)
    comp_data = c.comp_data(encodedPart)
    encodedPart = c.build_header(comp_data, start_crc32)
    encodedPart = base64.b64encode(encodedPart).decode("UTF-8")

    malicious_data = "|".join(
        [
            "0",
            malicious_directory,
            "6",
            encodedPart,
        ]
    )

    main.agentcommsv2._process_agent_packet(
        db, agent, "TASK_DOWNLOAD", "1", malicious_data
    )

    expected_message_part = "attempted skywalker exploit!"
    assert any(expected_message_part in message for message in caplog.messages)
