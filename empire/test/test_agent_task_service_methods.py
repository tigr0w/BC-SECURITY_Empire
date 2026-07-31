"""Service-level tests for AgentTaskService: the chunked-upload state machine,
the get_tasks query-builder branches, and the task-creation helpers that the
API tests don't reach.
"""

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from empire.server.api.v2.agent.agent_task_dto import AgentTaskOrderOptions
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.agent_task_service import _resolve_processes_module


def _db_agent(db, models, session_id):
    return db.query(models.Agent).filter(models.Agent.session_id == session_id).first()


_CSHARP = "csharp_situational_awareness_sharpsploit_processlist"
_PYTHON = "python_situational_awareness_host_processes"


@pytest.mark.parametrize(
    ("language", "os_details", "expected"),
    [
        ("powershell", "Windows 10", _CSHARP),
        ("ironpython", "Windows 10", _CSHARP),
        ("csharp", "Windows Server 2019", _CSHARP),
        ("go", "Windows 10 x64", _CSHARP),
        ("go", "Linux 5.15", None),
        ("go", None, None),
        ("python", "Linux 5.15", _PYTHON),
        ("python", None, _PYTHON),
        ("PowerShell", "Windows 10", _CSHARP),  # case-insensitive language
        ("perl", "whatever", None),
        (None, None, None),
    ],
)
def test_resolve_processes_module(language, os_details, expected):
    agent = SimpleNamespace(language=language, os_details=os_details)
    assert _resolve_processes_module(agent) == expected


# --------------------------------------------------------------------------- #
# get_tasks query-builder branches
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "order_by",
    [
        AgentTaskOrderOptions.status,
        AgentTaskOrderOptions.updated_at,
        AgentTaskOrderOptions.agent,
        AgentTaskOrderOptions.id,
    ],
)
def test_get_tasks_order_by_options(client, session_local, agent, main, order_by):
    with session_local.begin() as db:
        results, total = main.agenttasksv2.get_tasks(
            db,
            agents=[agent],
            order_by=order_by,
            order_direction=OrderDirection.asc,
        )

    assert isinstance(results, list)
    assert isinstance(total, int)


def test_get_tasks_filters_match_existing_task(
    client, session_local, agent, agent_task, main
):
    # agent_task fixture queues a shell task: echo "HELLO WORLD"
    with session_local.begin() as db:
        results, total = main.agenttasksv2.get_tasks(
            db,
            agents=[agent],
            users=[0, 1],
            since=datetime.now(UTC) - timedelta(days=1),
            q="HELLO",
            limit=10,
        )

        # Read attributes inside the session -- results detach on block exit.
        assert total >= 1
        assert any("HELLO" in (t.input or "") for t in results)


# --------------------------------------------------------------------------- #
# Chunked upload state machine
# --------------------------------------------------------------------------- #
def test_upload_chunked_single_chunk_creates_no_pending(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"abc")
    svc = main.agenttasksv2

    with session_local.begin() as db:
        resp, err = svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 3, "C:\\d.bin", chunk_size=1024
        )

    assert err is None
    assert resp is not None
    assert agent not in svc._pending_uploads


def test_upload_chunked_multi_chunk_queues_remaining(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")  # 10 bytes / 4 => 3 chunks
    svc = main.agenttasksv2

    try:
        with session_local.begin() as db:
            _resp, err = svc.create_task_upload_chunked(
                db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
            )

        assert err is None
        pending = svc._pending_uploads.get(agent)
        assert pending is not None
        assert pending["total_chunks"] == 3  # noqa: PLR2004
        assert pending["next_index"] == 1
        assert pending["dest_path"] == "C:\\d.bin"
        assert pending["chunk_size"] == 4  # noqa: PLR2004
    finally:
        svc._pending_uploads.pop(agent, None)


def test_upload_chunked_overwrites_existing_pending(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2

    try:
        with session_local.begin() as db:
            svc.create_task_upload_chunked(
                db, _db_agent(db, models, agent), str(f), 10, "C:\\a.bin", chunk_size=4
            )
        first_id = svc._pending_uploads[agent]["upload_id"]

        # A second chunked upload for the same agent replaces the first.
        with session_local.begin() as db:
            svc.create_task_upload_chunked(
                db, _db_agent(db, models, agent), str(f), 10, "C:\\b.bin", chunk_size=4
            )
        pending = svc._pending_uploads[agent]
        assert pending["dest_path"] == "C:\\b.bin"
        assert pending["upload_id"] != first_id
    finally:
        svc._pending_uploads.pop(agent, None)


def test_upload_chunked_read_error_returns_message(
    client, session_local, agent, main, models, tmp_path
):
    svc = main.agenttasksv2
    missing = tmp_path / "does-not-exist.bin"

    with session_local.begin() as db:
        resp, err = svc.create_task_upload_chunked(
            db,
            _db_agent(db, models, agent),
            str(missing),
            100,
            "C:\\d.bin",
            chunk_size=4,
        )

    assert resp is None
    assert err.startswith("Failed to read upload file")


def test_queue_next_upload_chunk_progresses_to_completion(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")  # 3 chunks of 4
    svc = main.agenttasksv2

    with session_local.begin() as db:
        svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
        )

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)
    assert svc._pending_uploads[agent]["next_index"] == 2  # noqa: PLR2004

    # Final chunk clears the pending entry.
    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)
    assert agent not in svc._pending_uploads


def test_queue_next_upload_chunk_no_pending_is_noop(client, session_local, agent, main):
    with session_local.begin() as db:
        result = main.agenttasksv2.queue_next_upload_chunk(db, "no-such-session")

    assert result is None


def test_queue_next_chunk_file_vanished_cancels(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2

    with session_local.begin() as db:
        svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
        )
    f.unlink()  # file disappears before the next chunk is read

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)

    assert agent not in svc._pending_uploads


def test_queue_next_chunk_empty_read_cancels(
    client, session_local, agent, main, models, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2

    with session_local.begin() as db:
        svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
        )
    f.write_bytes(b"01")  # truncated: next chunk offset is now past EOF

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)

    assert agent not in svc._pending_uploads


def test_queue_next_chunk_agent_gone_cancels(client, session_local, main, tmp_path):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2
    with svc._pending_uploads_lock:
        svc._pending_uploads["ghost-sess"] = {
            "upload_id": 5,
            "file_location": str(f),
            "chunk_size": 4,
            "total_chunks": 3,
            "next_index": 1,
            "dest_path": "C:\\d.bin",
            "started_at": time.time(),
            "user_id": None,
        }

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, "ghost-sess")

    assert "ghost-sess" not in svc._pending_uploads


def test_queue_next_chunk_add_task_error_cancels(
    client, session_local, agent, main, models, monkeypatch, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2

    with session_local.begin() as db:
        svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
        )
    monkeypatch.setattr(svc, "add_task", lambda *a, **k: (None, "queue full"))

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)

    assert agent not in svc._pending_uploads


def test_queue_next_chunk_add_task_exception_cancels(
    client, session_local, agent, main, models, monkeypatch, tmp_path
):
    f = tmp_path / "u.bin"
    f.write_bytes(b"0123456789")
    svc = main.agenttasksv2

    with session_local.begin() as db:
        svc.create_task_upload_chunked(
            db, _db_agent(db, models, agent), str(f), 10, "C:\\d.bin", chunk_size=4
        )

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "add_task", boom)

    with session_local.begin() as db:
        svc.queue_next_upload_chunk(db, agent)

    assert agent not in svc._pending_uploads


def _fake_pending(started_at):
    return {
        "upload_id": 999,
        "file_location": "/nonexistent",
        "chunk_size": 4,
        "total_chunks": 5,
        "next_index": 1,
        "dest_path": "C:\\d.bin",
        "started_at": started_at,
        "user_id": None,
    }


def test_cleanup_stale_uploads_removes_old_entries(client, main):
    svc = main.agenttasksv2
    with svc._pending_uploads_lock:
        svc._pending_uploads["stale-sess"] = _fake_pending(time.time() - 3600)

    svc.cleanup_stale_uploads()

    assert "stale-sess" not in svc._pending_uploads


def test_cleanup_stale_uploads_keeps_fresh_entries(client, main):
    svc = main.agenttasksv2
    with svc._pending_uploads_lock:
        svc._pending_uploads["fresh-sess"] = _fake_pending(time.time())

    try:
        svc.cleanup_stale_uploads()
        assert "fresh-sess" in svc._pending_uploads
    finally:
        svc._pending_uploads.pop("fresh-sess", None)


def test_cancel_pending_uploads_removes_entry(client, main):
    svc = main.agenttasksv2
    with svc._pending_uploads_lock:
        svc._pending_uploads["cancel-sess"] = _fake_pending(time.time())

    svc.cancel_pending_uploads("cancel-sess")

    assert "cancel-sess" not in svc._pending_uploads


# --------------------------------------------------------------------------- #
# Task-creation helpers not exercised by the API tests
# --------------------------------------------------------------------------- #
def test_create_task_smb(client, session_local, agent, main, models):
    with session_local.begin() as db:
        resp, err = main.agenttasksv2.create_task_smb(
            db, _db_agent(db, models, agent), "empire_pipe"
        )

    assert err is None
    assert resp is not None


def test_create_task_socks_data_adds_temporary_task(client, agent, main):
    svc = main.agenttasksv2
    svc.temporary_tasks.pop(agent, None)

    svc.create_task_socks_data(agent, "socks-bytes")

    assert len(svc.temporary_tasks[agent]) == 1
    svc.temporary_tasks.pop(agent, None)


def test_update_sleep_python_sets_delay_and_uses_python_cmd(
    client, session_local, agent, main, models
):
    with session_local.begin() as db:
        db_agent = _db_agent(db, models, agent)
        db_agent.language = "python"
        resp, err = main.agenttasksv2.create_task_update_sleep(db, db_agent, 10, 0.25)

        assert err is None
        assert resp is not None
        assert db_agent.delay == 10  # noqa: PLR2004
        assert db_agent.jitter == 0.25  # noqa: PLR2004


def test_update_sleep_csharp(client, session_local, agent, main, models):
    with session_local.begin() as db:
        db_agent = _db_agent(db, models, agent)
        db_agent.language = "csharp"
        resp, err = main.agenttasksv2.create_task_update_sleep(db, db_agent, 5, 0.1)

        assert err is None
        assert resp is not None


def test_update_sleep_unsupported_language(client, session_local, agent, main, models):
    with session_local.begin() as db:
        db_agent = _db_agent(db, models, agent)
        db_agent.language = "go"
        resp, err = main.agenttasksv2.create_task_update_sleep(db, db_agent, 5, 0.1)

    assert resp is None
    assert err == "Unsupported language."
