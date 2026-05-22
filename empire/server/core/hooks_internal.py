import json
import logging
from json.decoder import JSONDecodeError
from typing import Final

import jq
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
# `processes` set spans both PowerShell and Python agents because they share the
# same downstream HostProcess hook.
HOST_PROCESSES_MODULES: Final[frozenset[str]] = frozenset(
    {
        "powershell_situational_awareness_host_processes",
        "python_situational_awareness_host_processes",
    }
)
PS_PROCESSES_MODULE: Final[str] = "powershell_situational_awareness_host_processes"
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


def ps_hook(db: Session, task: models.AgentTask):
    """
    Watches for the processes module and writes processes into the HostProcess
    table. PowerShell/IronPython agents return JSON; Python agents return raw
    `ps` output that we parse via jq. Branch is selected by agent language.
    """
    if task.module_name not in HOST_PROCESSES_MODULES:
        return
    if _empty_output_skip(task, "ps_hook"):
        return

    if task.agent.language == "python":
        output = (
            jq.compile(
                """[sub("\n$";"") | splits("\n") | sub("^ +";"") | [splits(" +")]] | .[0] as $header | .[1:] | [.[] | [. as $x | range($header | length) | {"key": $header[.], "value": $x[.]}] | from_entries]"""
            )
            .input(task.output.split("\r\n ..Command execution completed.")[0])
            .first()
        )
    else:
        try:
            output = json.loads(task.output)
        except JSONDecodeError:
            log.warning("ps_hook: failed to decode JSON from processes module output")
            return

    existing_processes = db.scalars(
        select(models.HostProcess.process_id).where(
            models.HostProcess.host_id == task.agent.host_id
        )
    ).all()

    for process in output:
        process_name = process.get("CMD") or process.get("ProcessName") or ""
        process_id = process.get("PID")
        arch = process.get("Arch")
        user = process.get("UserName") or process.get("USER")
        if process_id:
            # new process
            if int(process_id) not in existing_processes:
                db.add(
                    models.HostProcess(
                        host_id=task.agent.host_id,
                        process_id=process_id,
                        process_name=process_name,
                        architecture=arch,
                        user=user,
                    )
                )
            # update existing process
            elif int(process_id) in existing_processes:
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

    for process in existing_processes:
        # mark processes that are no longer running stale
        if process not in [int(p.get("PID")) for p in output]:
            db_process: models.HostProcess | None = db.scalars(
                select(models.HostProcess).where(
                    and_(
                        models.HostProcess.host_id == task.agent.host_id,
                        models.HostProcess.process_id == process,
                    )
                )
            ).first()
            db_process.stale = True


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
