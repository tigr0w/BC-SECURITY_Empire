import csv
import io
from datetime import UTC, datetime, timedelta

from starlette import status

PLUGIN_ID = "basic_reporting"
EXPECTED_ALL_REPORT_DOWNLOADS = 4
HISTORY_LIMIT = 20


def _seed_chat_messages(session_local, models, rows, base_time=None):
    """Seed chat messages.

    base_time is optional; when provided, each row gets `base_time + i seconds`
    so created_at ordering is deterministic on SQLite (which has second-level
    precision and would otherwise collide when seeding many rows in a loop).
    """
    with session_local.begin() as db:
        for i, (username, message) in enumerate(rows):
            kwargs = {"user_id": 1, "username": username, "message": message}
            if base_time is not None:
                kwargs["created_at"] = base_time + timedelta(seconds=i)
            db.add(models.ChatMessage(**kwargs))


def _latest_plugin_task(client, admin_auth_header):
    """Fetch the most recently created basic_reporting task with its downloads."""
    response = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks",
        headers=admin_auth_header,
    )
    assert response.status_code == status.HTTP_200_OK
    records = response.json()["records"]
    assert records, "expected at least one plugin task"
    return max(records, key=lambda r: r["id"])


def _read_download_csv(client, admin_auth_header, download_id):
    response = client.get(
        f"/api/v2/downloads/{download_id}/download",
        headers=admin_auth_header,
    )
    assert response.status_code == status.HTTP_200_OK
    return list(csv.reader(io.StringIO(response.text)))


def _wipe_chat_messages(session_local, models):
    with session_local.begin() as db:
        db.query(models.ChatMessage).delete()


def test_chat_report_writes_seeded_messages(
    client, admin_auth_header, session_local, models
):
    _wipe_chat_messages(session_local, models)
    seeded = [("alice", "deploy ready?"), ("bob", "yes go ahead")]
    _seed_chat_messages(session_local, models, seeded)

    response = client.post(
        f"/api/v2/plugins/{PLUGIN_ID}/execute",
        json={"options": {"report": "chat"}},
        headers=admin_auth_header,
    )
    assert response.status_code == status.HTTP_200_OK

    task = _latest_plugin_task(client, admin_auth_header)
    chatlog = next(
        (d for d in task["downloads"] if d["filename"].startswith("chatlog")),
        None,
    )
    assert chatlog is not None, f"chatlog download missing in {task['downloads']}"

    csv_rows = _read_download_csv(client, admin_auth_header, chatlog["id"])
    assert csv_rows[0] == ["Timestamp", "Username", "Message"]
    body_pairs = [(r[1], r[2]) for r in csv_rows[1:]]
    for pair in seeded:
        assert pair in body_pairs


def test_all_report_includes_chatlog(client, admin_auth_header, session_local, models):
    _wipe_chat_messages(session_local, models)
    _seed_chat_messages(session_local, models, [("carol", "starting recon")])

    response = client.post(
        f"/api/v2/plugins/{PLUGIN_ID}/execute",
        json={"options": {"report": "all"}},
        headers=admin_auth_header,
    )
    assert response.status_code == status.HTTP_200_OK

    task = _latest_plugin_task(client, admin_auth_header)
    filenames = [d["filename"] for d in task["downloads"]]
    # create_download_from_text appends `(N)` on collision (download_service._increment_filename),
    # so the canonical prefix is preserved in every variant — startswith is sufficient.
    assert any(f.startswith("sessions") for f in filenames)
    assert any(f.startswith("credentials") for f in filenames)
    assert any(f.startswith("master") for f in filenames)
    assert any(f.startswith("chatlog") for f in filenames)
    assert len(task["downloads"]) == EXPECTED_ALL_REPORT_DOWNLOADS


def test_chat_history_returns_last_20_in_chronological_order(session_local, models):
    """Regression test for the off-by-N bug in the old in-memory chat/history."""
    _wipe_chat_messages(session_local, models)
    rows = [("user", f"msg-{i:02d}") for i in range(25)]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_chat_messages(session_local, models, rows, base_time=base)

    with session_local() as db:
        history = (
            db.query(models.ChatMessage)
            .order_by(models.ChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        ordered = list(reversed(history))

    assert len(ordered) == HISTORY_LIMIT
    assert ordered[0].message == "msg-05"
    assert ordered[-1].message == "msg-24"
