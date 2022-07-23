import json

import jq as jq
import terminaltables
from sqlalchemy import and_
from sqlalchemy.orm import Session

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.hooks import hooks


def ps_hook(db: Session, tasking: models.Tasking):
    """
    This hook watches for the 'ps' command and writes the processes into the processes table.

    For Powershell Agents, the data comes back (as of 4.1) as JSON.
    For Python Agents, the data comes back in the typical 'ls' format.
    For C# Agents, no support yet.

    AFAIK, it is not easy to convert the shell tables into JSON, but I found this jq wizardry
    on StackOverflow, so that's what we'll stick with for now for the python results, even though it is imperfect.
    https://unix.stackexchange.com/a/243485
    """
    if (
        tasking.input.strip() not in ["ps", "tasklist"]
        or tasking.agent.language == "csharp"
    ):
        return

    if tasking.agent.language == "python":
        output = (
            jq.compile(
                """[sub("\n$";"") | splits("\n") | sub("^ +";"") | [splits(" +")]] | .[0] as $header | .[1:] | [.[] | [. as $x | range($header | length) | {"key": $header[.], "value": $x[.]}] | from_entries]"""
            )
            .input(
                tasking.output.decode("utf-8").split(
                    "\r\n ..Command execution completed."
                )[0]
            )
            .first()
        )
    else:
        output = json.loads(tasking.output)

    with SessionLocal.begin() as db:
        existing_processes = (
            db.query(models.HostProcess.process_id)
            .filter(models.HostProcess.host_id == tasking.agent.host_id)
            .all()
        )
        existing_processes = list(map(lambda p: p[0], existing_processes))

        for process in output:
            process_name = process.get("CMD") or process.get("ProcessName") or ""
            process_id = process.get("PID")
            arch = process.get("Arch")
            user = process.get("UserName")
            if process_id:
                # and process_id.isnumeric():
                if int(process_id) not in existing_processes:
                    db.add(
                        models.HostProcess(
                            host_id=tasking.agent.host_id,
                            process_id=process_id,
                            process_name=process_name,
                            architecture=arch,
                            user=user,
                        )
                    )
                elif int(process_id) in existing_processes:
                    db_process: models.HostProcess = (
                        db.query(models.HostProcess)
                        .filter(
                            and_(
                                models.HostProcess.host_id == tasking.agent.host_id,
                                models.HostProcess.process_id == process_id,
                            )
                        )
                        .first()
                    )
                    if not db_process.agent:
                        db_process.architecture = arch
                        db_process.process_name = process_name


def ps_filter(db: Session, tasking: models.Tasking):
    """
    This filter converts the JSON results of the ps command and converts it to a PowerShell-ish table.

    if the results are from the Python or C# agents, it does nothing.
    """
    if tasking.input.strip() not in [
        "ps",
        "tasklist",
    ] or tasking.agent.language not in ["powershell", "ironpython"]:
        return db, tasking

    output = json.loads(tasking.output.decode("utf-8"))
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

    output_list.insert(0, ["PID", "ProcessName", "Arch", "UserName", "MemUsage"])

    table = terminaltables.AsciiTable(output_list)
    table.inner_row_border = False
    table.outer_border = False
    table.inner_column_border = False
    tasking.output = table.table

    return db, tasking


def ls_filter(db: Session, tasking: models.Tasking):
    """
    This filter converts the JSON results of the ls command and converts it to a PowerShell-ish table.

    if the results are from the Python or C# agents, it does nothing.
    """
    tasking_input = tasking.input.strip().split()
    if (
        len(tasking_input) == 0
        or tasking_input[0] not in ["ls", "dir"]
        or tasking.agent.language != "powershell"
    ):
        return db, tasking

    output = json.loads(tasking.output.decode("utf-8"))
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

    output_list.insert(0, ["Mode", "Owner", "LastWriteTime", "Length", "Name"])

    table = terminaltables.AsciiTable(output_list)
    table.inner_row_border = False
    table.outer_border = False
    table.inner_column_border = False
    tasking.output = table.table

    return db, tasking


def ipconfig_filter(db: Session, tasking: models.Tasking):
    """
    This filter converts the JSON results of the ifconfig/ipconfig command and converts it to a PowerShell-ish table.

    if the results are from the Python or C# agents, it does nothing.
    """
    if (
        tasking.input.strip() not in ["ipconfig", "ifconfig"]
        or tasking.agent.language != "powershell"
    ):
        return db, tasking

    output = json.loads(tasking.output.decode("utf-8"))
    if isinstance(output, dict):  # if there's only one adapter, it won't be a list.
        output = [output]

    output_list = []
    for rec in output:
        for key, value in rec.items():
            output_list.append([key, f": {value}"])
        output_list.append([])

    table = terminaltables.AsciiTable(output_list)
    table.inner_heading_row_border = False
    table.inner_row_border = False
    table.outer_border = False
    table.inner_column_border = False
    tasking.output = table.table

    return db, tasking


def route_filter(db: Session, tasking: models.Tasking):
    """
    This filter converts the JSON results of the route command and converts it to a PowerShell-ish table.

    if the results are from the Python or C# agents, it does nothing.
    """
    if tasking.input.strip() not in ["route"] or tasking.agent.language != "powershell":
        return db, tasking

    output = json.loads(tasking.output.decode("utf-8"))

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

    output_list.insert(0, ["Destination", "Netmask", "NextHop", "Interface", "Metric"])

    table = terminaltables.AsciiTable(output_list)
    table.inner_row_border = False
    table.outer_border = False
    table.inner_column_border = False
    tasking.output = table.table

    return db, tasking


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
