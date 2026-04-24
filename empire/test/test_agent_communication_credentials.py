"""Integration tests for the module-declared credential ingestion dispatch
path in AgentCommunicationService. Uses a kerberoast-tagged module so the
assertions cover both the new YAML field lookup and parser output landing
in the credentials table via the real CredentialService + DB session.
"""

import logging

import pytest
from sqlalchemy import func

from empire.server.core.db.models import AgentTaskStatus


def _kerberoast_output(sam: str = "sqlservice") -> bytes:
    return (
        f"[*] SamAccountName         : {sam}\r\n"
        f"[*] ServicePrincipalName   : MSSQLSvc/sql1.example.local:1433\r\n"
        "\r\n"
        f"$krb5tgs$23$*{sam}$example.local$MSSQLSvc/sql1.example.local:1433*$"
        "FEEDFACECAFEBEEF0102030405060708\r\n"
    ).encode()


def _mimikatz_output(username: str = "bob", password: str = "BobPass1!") -> bytes:
    return (
        b"Hostname: WIN-AGENT.example.local/S-1-5-21-1\n"
        b"\n"
        b"Authentication Id : 0 ; 1\n"
        b"\tmsv :\n"
        b"\t * Username : " + username.encode() + b"\n"
        b"\t * Domain   : EXAMPLE\n"
        b"\t * NTLM     : " + b"a" * 32 + b"\n"
        b"\t tspkg :\n"
        b"\t * Username : " + username.encode() + b"\n"
        b"\t * Domain   : EXAMPLE\n"
        b"\t * Password : " + password.encode() + b"\n"
        b"\t wdigest :\n"
        b"\t * Username : (null)\n"
        b"\t * Domain   : (null)\n"
        b"\t * Password : (null)\n"
        b"\t kerberos :\n"
        b"\t ssp :\n"
        b"\t credman :\n"
    )


@pytest.fixture
def create_tasking(session_local, models):
    """Insert an AgentTask with the given module_name and return its id."""

    def _make(agent_id: str, module_name: str | None, task_name: str) -> int:
        # AgentTask has a composite primary key (id, agent_id); the id is
        # assigned manually (see agent_task_service.py around line 663).
        with session_local.begin() as db:
            current_max = (
                db.query(func.max(models.AgentTask.id))
                .filter(models.AgentTask.agent_id == agent_id)
                .scalar()
                or 0
            )
            tasking = models.AgentTask(
                id=current_max + 1,
                agent_id=agent_id,
                input="",
                module_name=module_name,
                task_name=task_name,
                status=AgentTaskStatus.queued,
            )
            db.add(tasking)
            db.flush()
            return tasking.id

    return _make


def _credential_count_for_host(session_local, models, host: str, credtype: str) -> int:
    with session_local.begin() as db:
        return (
            db.query(models.Credential)
            .filter(
                models.Credential.host == host,
                models.Credential.credtype == credtype,
            )
            .count()
        )


def test_ingest_kerberoast_via_module_declaration(
    main, session_local, models, agent, create_tasking
):
    """When a module declares `credential_parser: kerberoast`, a
    $krb5tgs$ blob coming back through `TASK_POWERSHELL_CMD_WAIT` lands
    in the credentials table with credtype=krbtgs.
    """
    task_id = create_tasking(
        agent, "powershell_credentials_invoke_kerberoast", "TASK_POWERSHELL_CMD_WAIT"
    )
    sam = f"svc_{task_id}"  # unique per test run to avoid dedup collisions

    with session_local.begin() as db:
        main.agentcommsv2._process_agent_packet(
            db, agent, "TASK_POWERSHELL_CMD_WAIT", task_id, _kerberoast_output(sam)
        )

    with session_local.begin() as db:
        creds = (
            db.query(models.Credential)
            .filter(models.Credential.credtype == "krbtgs")
            .filter(models.Credential.username == sam)
            .all()
        )
        # Read attributes inside the session to avoid DetachedInstanceError
        # once the `with` block commits and expires instances.
        assert len(creds) == 1
        sql = creds[0]
        assert sql.domain == "example.local"
        assert sql.password.startswith(
            f"$krb5tgs$23$*{sam}$example.local$MSSQLSvc/sql1.example.local:1433*$"
        )
        assert "kerberoast" in (sql.notes or "")


def test_ingest_mimikatz_via_prefix_fallback(
    main, session_local, models, agent, create_tasking
):
    """A task with no module_name should fall back to `Hostname:` prefix
    detection and still ingest mimikatz output — exercises the legacy path
    used by ad-hoc shell invocations.
    """
    task_id = create_tasking(agent, None, "TASK_POWERSHELL_CMD_WAIT")
    username = f"fb_user_{task_id}"
    password = f"fb_pw_{task_id}"

    with session_local.begin() as db:
        main.agentcommsv2._process_agent_packet(
            db,
            agent,
            "TASK_POWERSHELL_CMD_WAIT",
            task_id,
            _mimikatz_output(username=username, password=password),
        )

    with session_local.begin() as db:
        plain = (
            db.query(models.Credential)
            .filter(models.Credential.username == username)
            .filter(models.Credential.credtype == "plaintext")
            .all()
        )
        assert len(plain) == 1
        assert plain[0].password == password
        assert plain[0].host == "WIN-AGENT"


def test_unknown_credential_parser_aborts_ingestion(
    main, session_local, models, agent, create_tasking, caplog
):
    """If a module declares a parser name that isn't registered, the
    dispatcher logs an error and skips ingestion — it does NOT fall back
    to prefix detection, because that would mask a broken module YAML.
    """
    fake_module = type("M", (), {"credential_parser": "not_a_real_parser"})()
    main.agentcommsv2.module_service.modules["__fake_cred_module__"] = fake_module

    try:
        task_id = create_tasking(
            agent, "__fake_cred_module__", "TASK_POWERSHELL_CMD_WAIT"
        )
        username = f"unk_user_{task_id}"
        password = f"unk_pw_{task_id}"

        with (
            session_local.begin() as db,
            caplog.at_level(
                logging.ERROR,
                logger="empire.server.core.agent_communication_service",
            ),
        ):
            main.agentcommsv2._process_agent_packet(
                db,
                agent,
                "TASK_POWERSHELL_CMD_WAIT",
                task_id,
                _mimikatz_output(username=username, password=password),
            )
    finally:
        main.agentcommsv2.module_service.modules.pop("__fake_cred_module__", None)

    assert any(
        "declares unknown credential_parser" in r.message for r in caplog.records
    ), "expected an error log about the unknown parser name"

    with session_local.begin() as db:
        hits = (
            db.query(models.Credential)
            .filter(models.Credential.username == username)
            .all()
        )
        assert len(hits) == 0, (
            "credentials from a module with an unknown parser name must not "
            "land via the prefix heuristic — that would mask the YAML bug"
        )
