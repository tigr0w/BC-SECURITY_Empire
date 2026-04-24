import json

import pytest

from empire.server.core.hooks import hooks
from empire.server.core.hooks_internal import (
    _format_table,
    ipconfig_filter,
    ls_filter,
    ps_filter,
    route_filter,
)


def test_format_table():
    result = _format_table(
        ["PID", "ProcessName", "Arch", "UserName", "MemUsage"],
        [
            ["1234", "svchost", "x64", "SYSTEM", "15MB"],
            ["5678", "explorer.exe", "x64", "Admin", "120MB"],
            ["9", "idle", "", "", "0MB"],
            ["42", "System", None, None, "1MB"],
        ],
    )

    expected = (
        " PID   ProcessName   Arch  UserName  MemUsage \n"
        "----------------------------------------------\n"
        " 1234  svchost       x64   SYSTEM    15MB     \n"
        " 5678  explorer.exe  x64   Admin     120MB    \n"
        " 9     idle                          0MB      \n"
        " 42    System        None  None      1MB      "
    )
    assert result == expected


@pytest.fixture
def _existing_processes(session_local, models, host):
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        existing_processes = [
            models.HostProcess(
                host_id=host,
                process_id=1,
                process_name="should_be_stale",
                architecture="x86",
                user="test_user",
            ),
            models.HostProcess(
                host_id=host,
                process_id=2,
                process_name="should_be_updated",
                architecture="x86",
                user="test_user",
            ),
            models.HostProcess(
                host_id=host,
                process_id=3,
                process_name="should_be_same",
                architecture="x86",
                user="test_user",
            ),
        ]
        db.add_all(existing_processes)

    yield

    with session_local.begin() as db:
        db.query(models.HostProcess).delete()


@pytest.fixture
def _python_existing_processes(session_local, models, host):
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        db.add(
            models.HostProcess(
                host_id=host,
                process_id=999,
                process_name="should_be_stale_py",
                architecture=None,
                user="root",
            )
        )

    yield

    with session_local.begin() as db:
        db.query(models.HostProcess).delete()


@pytest.mark.usefixtures("_existing_processes")
def test_ps_hook(client, session_local, models, host, agent):
    with session_local.begin() as db:
        output = json.dumps(
            [
                {
                    "CMD": "has_been_updated",
                    "PID": 2,
                    "Arch": "x86_64",
                    "UserName": "test_user",
                },
                {
                    "CMD": "should_be_same",
                    "PID": 3,
                    "Arch": "x86",
                    "UserName": "test_user",
                },
                {
                    "CMD": "should_be_new",
                    "PID": 4,
                    "Arch": "x86",
                    "UserName": "test_user",
                },
            ]
        )
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = models.AgentTask(
            id=1,
            agent_id=agent,
            agent=db_agent,
            input="(processes module script)",
            module_name="powershell_situational_awareness_host_processes",
            status=models.AgentTaskStatus.pulled,
            output=output,
            original_output=output,
        )
        hooks.run_hooks(hooks.BEFORE_TASKING_RESULT_HOOK, db, task)
        db.flush()
        processes = db.query(models.HostProcess).all()

        expected_processes = 4
        assert len(processes) == expected_processes
        assert processes[0].process_name == "should_be_stale"
        assert processes[0].stale is True
        assert processes[1].process_name == "has_been_updated"
        assert processes[1].stale is False
        assert processes[2].process_name == "should_be_same"
        assert processes[2].stale is False
        assert processes[3].process_name == "should_be_new"
        assert processes[3].stale is False


_PY_EXISTING_PID = 999


@pytest.mark.usefixtures("_python_existing_processes")
def test_ps_hook_python_jq_branch(session_local, models, host, agent):
    """Python agent returns raw `ps -eo pid,user,cmd` text; jq branch parses it."""
    raw_ps = (
        " PID USER CMD\n"
        " 1 root /sbin/init\n"
        " 2 root [kthreadd]\n"
        f" {_PY_EXISTING_PID} root some_process\n"
    )
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_agent.language = "python"
        task = models.AgentTask(
            id=2,
            agent_id=agent,
            agent=db_agent,
            input="(python processes module)",
            module_name="python_situational_awareness_host_processes",
            status=models.AgentTaskStatus.pulled,
            output=raw_ps,
            original_output=raw_ps,
        )
        hooks.run_hooks(hooks.BEFORE_TASKING_RESULT_HOOK, db, task)
        db.flush()

        processes = (
            db.query(models.HostProcess).order_by(models.HostProcess.process_id).all()
        )
        names = {p.process_id: p.process_name for p in processes}
        assert names[1] == "/sbin/init"
        assert names[2] == "[kthreadd]"
        # Existing PID was in the new output too — must not be marked stale.
        assert names[_PY_EXISTING_PID] == "some_process"
        stale_existing = next(p for p in processes if p.process_id == _PY_EXISTING_PID)
        assert stale_existing.stale is False


def _make_ps_task(models, agent, db_agent, module_name, output, language="powershell"):
    db_agent.language = language
    return models.AgentTask(
        id=99,
        agent_id=agent,
        agent=db_agent,
        input="(module script)",
        module_name=module_name,
        status=models.AgentTaskStatus.pulled,
        output=output,
        original_output=output,
    )


def test_ps_filter_formats_json_table(session_local, models, agent):
    output = json.dumps(
        [
            {
                "PID": 1,
                "ProcessName": "init",
                "Arch": "x64",
                "UserName": "root",
                "MemUsage": "1MB",
            }
        ]
    )
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_processes",
            output,
        )
        _, task = ps_filter(db, task)
    assert "PID" in task.output
    assert "ProcessName" in task.output
    assert "init" in task.output


def test_ps_filter_skips_python_agent(session_local, models, agent):
    output = json.dumps([{"PID": 1, "ProcessName": "init"}])
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_processes",
            output,
            language="python",
        )
        _, task = ps_filter(db, task)
    # Python agent runs the python module instead; ps_filter must leave the JSON untouched.
    assert task.output == output


def test_ls_filter_formats_json_table(session_local, models, agent):
    output = json.dumps(
        [
            {
                "Mode": "-a---",
                "Owner": "root",
                "LastWriteTime": "2024-01-01",
                "Length": 5,
                "Name": "x",
            }
        ]
    )
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_dir_list",
            output,
        )
        _, task = ls_filter(db, task)
    assert "Mode" in task.output
    assert "Name" in task.output


def test_ipconfig_filter_handles_single_adapter_dict(session_local, models, agent):
    # Single-adapter case: PowerShell emits a dict, not a list.
    output = json.dumps({"Description": "eth0", "IPAddress": "1.2.3.4"})
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_ipconfig",
            output,
        )
        _, task = ipconfig_filter(db, task)
    assert "Description" in task.output
    assert "1.2.3.4" in task.output


def test_route_filter_formats_json_table(session_local, models, agent):
    output = json.dumps(
        [
            {
                "Destination": "0.0.0.0",
                "Netmask": "0.0.0.0",
                "NextHop": "1.1.1.1",
                "Interface": "eth0",
                "Metric": 1,
            }
        ]
    )
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_route",
            output,
        )
        _, task = route_filter(db, task)
    assert "Destination" in task.output
    assert "0.0.0.0" in task.output


def test_filter_skips_when_output_empty(session_local, models, agent):
    """All four filters must early-exit when task.output is empty."""
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        task = _make_ps_task(
            models,
            agent,
            db_agent,
            "powershell_situational_awareness_host_processes",
            "",
        )
        _, task = ps_filter(db, task)
        # No exception; output stays empty.
        assert task.output == ""
