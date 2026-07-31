import json
import logging
from json.decoder import JSONDecodeError
from typing import Final

from prettytable import PrettyTable
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.hooks import hooks

log = logging.getLogger(__name__)


def _format_table(headers: list[str], rows: list[list]) -> str:
    table = PrettyTable(headers)
    table.border = False
    table.align = "l"
    for row in rows:
        table.add_row(row)
    lines = table.get_string().split("\n")
    lines.insert(1, "-" * len(lines[0]))
    return "\n".join(lines)


# Module IDs are slugified file paths (see module_service._load_module). The
# `processes` set spans PowerShell, Python, and C# (SharpSploit) agents because
# they all feed the same downstream HostProcess hook.
PS_PROCESSES_MODULE: Final[str] = "powershell_situational_awareness_host_processes"
PYTHON_PROCESSES_MODULE: Final[str] = "python_situational_awareness_host_processes"
CSHARP_PROCESSES_MODULE: Final[str] = (
    "csharp_situational_awareness_sharpsploit_processlist"
)
HOST_PROCESSES_MODULES: Final[frozenset[str]] = frozenset(
    {PS_PROCESSES_MODULE, PYTHON_PROCESSES_MODULE, CSHARP_PROCESSES_MODULE}
)
PS_IPCONFIG_MODULE: Final[str] = "powershell_situational_awareness_host_ipconfig"
PS_ROUTE_MODULE: Final[str] = "powershell_situational_awareness_host_route"
PS_DIR_LIST_MODULE: Final[str] = "powershell_situational_awareness_host_dir_list"


def _empty_output_skip(task: models.AgentTask, filter_name: str) -> bool:
    """Log + skip when expected output is missing so silent regressions surface."""
    if not task.output:
        log.warning(
            "%s: skipped, task %s for agent %s has empty output",
            filter_name,
            task.id,
            task.agent_id,
        )
        return True
    return False


def _coerce_pid(value) -> int | None:
    """Return the PID as an int, or None if missing / non-numeric.

    Uses ``isdecimal()`` (not ``isdigit()``): ``str.isdigit()`` accepts Unicode
    digit-category characters like superscripts that ``int()`` then rejects,
    which would raise instead of skipping on crafted agent output.
    """
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text.isdecimal() else None


_PS_ROW_FIELD_COUNT: Final[int] = 3


def _parse_python_ps_output(raw_output: str) -> list[dict[str, str]]:
    """Parse raw `ps -eo pid,user,cmd` text into process dicts.

    Each row is split into at most three fields so the command keeps its
    arguments (`split(None, 2)`), unlike a naive whitespace split.
    """
    raw = raw_output.split("\r\n ..Command execution completed.", maxsplit=1)[0]
    rows = [line for line in raw.splitlines() if line.strip()]
    output = []
    for line in rows[1:]:  # row 0 is the "PID USER CMD" header
        parts = line.split(None, 2)
        if len(parts) < _PS_ROW_FIELD_COUNT:
            continue
        pid, user, cmd = parts
        output.append({"PID": pid, "USER": user, "CMD": cmd})
    return output


_SHARPSPLOIT_MIN_LINES: Final[int] = 2  # header + underline, before any data rows


def _parse_sharpsploit_table(output: str) -> list[dict]:
    """Parse a SharpSploit ``SharpSploitResultList.ToString()`` table into dicts.

    Layout: a header line, an underline line of dash-runs, then data rows. Columns
    are left-aligned. SharpSploit underlines a column with dashes only as wide as
    its *header label*, but a value may be wider than its label -- so a column
    spans from the start of its dash-run to the start of the NEXT column's dash-run
    (the last column runs to end of line). Slicing by a dash-run's own width would
    truncate any value wider than its header. Keys are the header labels verbatim.
    """
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) < _SHARPSPLOIT_MIN_LINES:
        return []
    header_line, rule_line = lines[0], lines[1]

    starts: list[int] = []
    in_run = False
    for i, ch in enumerate(rule_line):
        if ch == "-" and not in_run:
            starts.append(i)
            in_run = True
        elif ch != "-":
            in_run = False
    if not starts:
        return []

    bounds = [
        (starts[k], starts[k + 1] if k + 1 < len(starts) else None)
        for k in range(len(starts))
    ]
    headers = [header_line[s:e].strip() for s, e in bounds]
    rows: list[dict] = []
    for line in lines[2:]:
        values = [line[s:e].strip() for s, e in bounds]
        rows.append(dict(zip(headers, values, strict=False)))
    return rows


def _parse_csharp_processes(output: str) -> list[dict]:
    """Map a SharpSploit ProcessList text table into HostProcess-shaped dicts."""
    return [
        {
            "PID": row.get("Pid"),
            "ProcessName": row.get("Name"),
            "Arch": row.get("Architecture"),
            "UserName": row.get("Owner"),
        }
        for row in _parse_sharpsploit_table(output)
    ]


def _upsert_process(
    db: Session, task: models.AgentTask, process: dict, existing_processes
) -> int | None:
    """Insert/update a single process row; returns its PID, or None if unusable."""
    process_id = _coerce_pid(process.get("PID"))
    if process_id is None:
        return None
    process_name = process.get("CMD") or process.get("ProcessName") or ""
    arch = process.get("Arch")
    user = process.get("UserName") or process.get("USER")

    if process_id not in existing_processes:
        db.add(
            models.HostProcess(
                host_id=task.agent.host_id,
                process_id=process_id,
                process_name=process_name,
                architecture=arch,
                user=user,
            )
        )
        return process_id

    db_process: models.HostProcess = db.scalars(
        select(models.HostProcess).where(
            and_(
                models.HostProcess.host_id == task.agent.host_id,
                models.HostProcess.process_id == process_id,
            )
        )
    ).first()
    if not db_process.agent:
        db_process.architecture = arch
        db_process.process_name = process_name
        db_process.user = user
    return process_id


def _mark_stale_processes(
    db: Session, task: models.AgentTask, existing_processes, current_pids: set[int]
) -> None:
    """Mark processes that are no longer running stale."""
    for process in existing_processes:
        if process not in current_pids:
            db_process: models.HostProcess | None = db.scalars(
                select(models.HostProcess).where(
                    and_(
                        models.HostProcess.host_id == task.agent.host_id,
                        models.HostProcess.process_id == process,
                    )
                )
            ).first()
            db_process.stale = True


def ps_hook(db: Session, task: models.AgentTask):
    """
    Watches for the processes module and writes processes into the HostProcess
    table. PowerShell/IronPython agents return JSON; Python agents return raw
    `ps` output; the C# SharpSploit module returns an aligned text table. Each
    is parsed by its own branch, selected by module id / agent language.
    """
    if task.module_name not in HOST_PROCESSES_MODULES:
        return
    if _empty_output_skip(task, "ps_hook"):
        return

    if task.module_name == CSHARP_PROCESSES_MODULE:
        output = _parse_csharp_processes(task.output)
    elif task.agent.language == "python":
        output = _parse_python_ps_output(task.output)
    else:
        try:
            output = json.loads(task.output)
        except JSONDecodeError:
            log.warning("ps_hook: failed to decode JSON from processes module output")
            return
        if isinstance(output, dict):
            output = [output]

    existing_processes = db.scalars(
        select(models.HostProcess.process_id).where(
            models.HostProcess.host_id == task.agent.host_id
        )
    ).all()

    current_pids: set[int] = set()
    for process in output:
        process_id = _upsert_process(db, task, process, existing_processes)
        if process_id is not None:
            current_pids.add(process_id)

    _mark_stale_processes(db, task, existing_processes, current_pids)


def ps_filter(db: Session, task: models.AgentTask):
    """
    Converts the JSON results of the processes module to a PowerShell-ish
    table. Fires for PowerShell/IronPython agents (both run the PowerShell
    processes module).
    """
    if task.module_name != PS_PROCESSES_MODULE or task.agent.language not in [
        "powershell",
        "ironpython",
    ]:
        return db, task
    if _empty_output_skip(task, "ps_filter"):
        return db, task

    try:
        output = json.loads(task.output)
    except JSONDecodeError:
        log.warning("ps_filter: failed to decode JSON from processes module output")
        return db, task

    if isinstance(output, dict):
        output = [output]

    output_list = []
    for rec in output:
        output_list.append(
            [
                rec.get("PID"),
                rec.get("ProcessName"),
                rec.get("Arch"),
                rec.get("UserName"),
                rec.get("MemUsage"),
            ]
        )

    task.output = _format_table(
        ["PID", "ProcessName", "Arch", "UserName", "MemUsage"], output_list
    )

    return db, task


def ls_filter(db: Session, task: models.AgentTask):
    """Converts dir_list module JSON to a PowerShell-ish table. PS agents only."""
    if task.module_name != PS_DIR_LIST_MODULE or task.agent.language != "powershell":
        return db, task
    if _empty_output_skip(task, "ls_filter"):
        return db, task

    try:
        output = json.loads(task.output)
    except JSONDecodeError:
        log.warning("ls_filter: failed to decode JSON from dir_list module output")
        return db, task

    output_list = []
    for rec in output:
        output_list.append(
            [
                rec.get("Mode"),
                rec.get("Owner"),
                rec.get("LastWriteTime"),
                rec.get("Length"),
                rec.get("Name"),
            ]
        )

    task.output = _format_table(
        ["Mode", "Owner", "LastWriteTime", "Length", "Name"], output_list
    )

    return db, task


def ipconfig_filter(db: Session, task: models.AgentTask):
    """Converts ipconfig module JSON to a PowerShell-ish table. PS agents only."""
    if task.module_name != PS_IPCONFIG_MODULE or task.agent.language != "powershell":
        return db, task
    if _empty_output_skip(task, "ipconfig_filter"):
        return db, task

    try:
        output = json.loads(task.output)
    except JSONDecodeError:
        log.warning(
            "ipconfig_filter: failed to decode JSON from ipconfig module output"
        )
        return db, task

    if isinstance(
        output, dict
    ):  # single-adapter case: PowerShell emits an object, not a list
        output = [output]

    table = PrettyTable(header=False)
    table.border = False
    table.align = "l"
    for rec in output:
        for key, value in rec.items():
            table.add_row([key, f": {value}"])
        table.add_row(["", ""])
    task.output = table.get_string()

    return db, task


def route_filter(db: Session, task: models.AgentTask):
    """Converts route module JSON to a PowerShell-ish table. PS agents only."""
    if task.module_name != PS_ROUTE_MODULE or task.agent.language != "powershell":
        return db, task
    if _empty_output_skip(task, "route_filter"):
        return db, task

    try:
        output = json.loads(task.output)
    except JSONDecodeError:
        log.warning("route_filter: failed to decode JSON from route module output")
        return db, task

    output_list = []
    for rec in output:
        output_list.append(
            [
                rec.get("Destination"),
                rec.get("Netmask"),
                rec.get("NextHop"),
                rec.get("Interface"),
                rec.get("Metric"),
            ]
        )

    task.output = _format_table(
        ["Destination", "Netmask", "NextHop", "Interface", "Metric"], output_list
    )

    return db, task


def initialize():
    hooks.register_hook(hooks.BEFORE_TASKING_RESULT_HOOK, "ps_hook_internal", ps_hook)

    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "ps_filter_internal", ps_filter
    )
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "ls_filter_internal", ls_filter
    )
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "ipconfig_filter_internal", ipconfig_filter
    )
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "route_filter_internal", route_filter
    )
