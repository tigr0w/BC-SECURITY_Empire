import json

import pytest

from empire.server.core.hooks import hooks
from empire.server.core.hooks_internal import (
    _coerce_pid,
    _format_table,
    _parse_sharpsploit_table,
    ipconfig_filter,
    ls_filter,
    ps_filter,
    route_filter,
)

# Real SharpSploit ProcessResult column order, from SharpSploit source
# Enumeration/Host.cs -> ProcessResult.ResultProperties.
_CSHARP_HEADERS = ["Pid", "Ppid", "Name", "SessionID", "Owner", "Architecture", "Path"]


def _sharpsploit_table(headers, rows):
    """Render a SharpSploit-style table: left-aligned columns padded to
    max(label, widest value) + 2; underline dashes span only the label width;
    the last column has no trailing padding."""
    widths = [
        max([len(headers[i])] + [len(r[i]) for r in rows]) + 2
        for i in range(len(headers))
    ]
    last = len(headers) - 1

    def render(cells):
        return "".join(
            cells[i].ljust(widths[i]) if i != last else cells[i]
            for i in range(len(cells))
        )

    header_line = render(headers)
    rule_line = render(["-" * len(h) for h in headers])
    body = "\n".join(render(r) for r in rows)
    return f"{header_line}\n{rule_line}\n{body}\n"


_COERCE_PID_VALID = 123
_COERCE_PID_STRIPPED = 7


def test_coerce_pid_rejects_non_ascii_digit():
    # Superscript 2: str.isdigit() is True but int() raises ValueError on it.
    assert _coerce_pid("²") is None
    assert _coerce_pid("123") == _COERCE_PID_VALID
    assert _coerce_pid(None) is None
    assert _coerce_pid("  7 ") == _COERCE_PID_STRIPPED
    assert _coerce_pid("x") is None


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


_LONE_PROCESS_PID = 4321
_VALID_PROCESS_PID = 55


def test_ps_hook_single_process_dict(session_local, models, host, agent):
    """ConvertTo-Json on a single process emits an object, not a list."""
    output = json.dumps(
        {"CMD": "loneproc", "PID": _LONE_PROCESS_PID, "Arch": "x64", "UserName": "root"}
    )
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_agent.language = "powershell"
        task = models.AgentTask(
            id=20,
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
        assert len(processes) == 1
        assert processes[0].process_id == _LONE_PROCESS_PID
        assert processes[0].process_name == "loneproc"


def test_ps_hook_python_multi_token_cmd(session_local, models, host, agent):
    """Command + arguments must survive parsing (was truncated to first token)."""
    raw_ps = " PID USER CMD\n 1 root /sbin/init splash\n"
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_agent.language = "python"
        task = models.AgentTask(
            id=21,
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
        proc = (
            db.query(models.HostProcess)
            .filter(models.HostProcess.process_id == 1)
            .first()
        )
        assert proc.process_name == "/sbin/init splash"


def test_ps_hook_skips_row_without_pid(session_local, models, host, agent):
    """A row missing its PID is skipped, not raised on."""
    output = json.dumps(
        [
            {
                "CMD": "valid",
                "PID": _VALID_PROCESS_PID,
                "Arch": "x64",
                "UserName": "root",
            },
            {"CMD": "no_pid", "Arch": "x64", "UserName": "root"},
        ]
    )
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_agent.language = "powershell"
        task = models.AgentTask(
            id=22,
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
        assert len(processes) == 1
        assert processes[0].process_id == _VALID_PROCESS_PID


def test_parse_sharpsploit_table_handles_wide_values():
    output = _sharpsploit_table(
        _CSHARP_HEADERS,
        [
            ["4", "0", "System", "0", "NT AUTHORITY\\SYSTEM", "x64", ""],
            ["1200", "600", "chrome", "1", "DESKTOP\\me", "x64", "C:\\p f\\chrome.exe"],
        ],
    )
    rows = _parse_sharpsploit_table(output)
    assert rows[0]["Pid"] == "4"
    assert rows[0]["Name"] == "System"
    # wider-than-header value with an internal space, not the last column:
    assert rows[0]["Owner"] == "NT AUTHORITY\\SYSTEM"
    assert rows[0]["Architecture"] == "x64"
    assert rows[1]["Owner"] == "DESKTOP\\me"
    # last column keeps its internal spaces:
    assert rows[1]["Path"] == "C:\\p f\\chrome.exe"


def test_ps_hook_csharp_table(session_local, models, host, agent):
    """C# SharpSploit ProcessList emits an aligned text table (not JSON)."""
    output = _sharpsploit_table(
        _CSHARP_HEADERS,
        [
            ["4", "0", "System", "0", "NT AUTHORITY\\SYSTEM", "x64", ""],
            ["1200", "600", "chrome", "1", "DESKTOP\\me", "x64", "C:\\tmp\\chrome.exe"],
        ],
    )
    with session_local.begin() as db:
        db.query(models.HostProcess).delete()
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_agent.language = "csharp"
        task = models.AgentTask(
            id=23,
            agent_id=agent,
            agent=db_agent,
            input="(csharp processlist module)",
            module_name="csharp_situational_awareness_sharpsploit_processlist",
            status=models.AgentTaskStatus.pulled,
            output=output,
            original_output=output,
        )
        hooks.run_hooks(hooks.BEFORE_TASKING_RESULT_HOOK, db, task)
        db.flush()
        procs = {p.process_id: p for p in db.query(models.HostProcess).all()}
        assert procs[4].process_name == "System"
        assert procs[4].user == "NT AUTHORITY\\SYSTEM"
        assert procs[1200].process_name == "chrome"
        assert procs[1200].architecture == "x64"
        assert procs[1200].user == "DESKTOP\\me"


def test_ps_filter_single_process_dict(session_local, models, agent):
    output = json.dumps(
        {
            "PID": 1,
            "ProcessName": "init",
            "Arch": "x64",
            "UserName": "root",
            "MemUsage": "1MB",
        }
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
    assert "init" in task.output


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
