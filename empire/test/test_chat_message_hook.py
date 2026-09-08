"""Covers AFTER_CHAT_MESSAGE_HOOK and the persist_and_fire_chat helper."""

import pytest
from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect

from empire.server.api.v2.websocket.socketio import persist_and_fire_chat
from empire.server.core.hooks import hooks


@pytest.fixture(autouse=True)
def _clean_chat_messages(session_local, models):
    """persist_and_fire_chat commits, so drop the rows these tests leave."""
    yield
    with session_local.begin() as db:
        db.query(models.ChatMessage).delete()


def test_after_chat_message_hook_fires_with_usable_message(
    client, admin_auth_header, session_local, models
):
    received = {}

    def _cb(db, message):
        # message must be usable (not expired/detached) here
        received["username"] = message.username
        received["message"] = message.message

    hooks.register_hook(hooks.AFTER_CHAT_MESSAGE_HOOK, "test_chat_hook_cb", _cb)
    try:
        with session_local() as db:
            persist_and_fire_chat(db, user_id=1, username="alice", text="hello ai")
        assert received == {"username": "alice", "message": "hello ai"}
    finally:
        hooks.unregister_hook("test_chat_hook_cb")


def test_created_at_readable_when_dialect_has_no_insert_returning(
    client, admin_auth_header, session_local, models, monkeypatch
):
    """created_at must survive the expunge where the dialect has no RETURNING.

    See persist_and_fire_chat for the mechanism. SQLite and MariaDB >= 10.5 have
    RETURNING and would pass vacuously, so the flag is forced off to exercise
    the MySQL path wherever this runs. The flip rides on private SQLAlchemy
    internals, so the INSERT is asserted to carry no RETURNING - otherwise it
    fails open and passes against unfixed code.
    """
    with session_local() as db:
        bind = db.get_bind()
        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(bind, "before_cursor_execute", _record)
        try:
            # Session-scoped flag: monkeypatch restores it even if this raises.
            monkeypatch.setattr(bind.dialect, "insert_returning", False)
            # The flush compiles INSERTs through the mapper cache, so one built
            # while RETURNING was on gets replayed and defeats the flag above.
            # The engine-level cache never holds this INSERT.
            sa_inspect(models.ChatMessage)._compiled_cache.clear()

            msg = persist_and_fire_chat(db, user_id=1, username="bob", text="hi")

            # The regression itself, before the structural checks below, which
            # would otherwise fail first and mask it. Exactly what on_message
            # evaluates for the emit.
            assert msg.created_at.isoformat()
            assert msg.created_at.tzinfo is not None

            insert = next(
                (s for s in statements if "INSERT INTO CHAT_MESSAGES" in s.upper()),
                None,
            )
            assert insert is not None, (
                f"no chat_messages INSERT was emitted: {statements}"
            )
            assert "RETURNING" not in insert.upper(), (
                "insert_returning flip did not take effect -- this test would "
                f"have passed against unfixed code. INSERT was: {insert}"
            )

            # A whole-row refresh would expire relationships, which the expunge
            # then strands. The scoping shows in the columns selected.
            refresh = next(
                (
                    s
                    for s in statements
                    if s.upper().lstrip().startswith("SELECT")
                    and "chat_messages" in s.lower()
                ),
                None,
            )
            assert refresh is not None, (
                f"created_at was unloaded, so a preload SELECT was expected: {statements}"
            )
            selected = {
                c.strip().split(".")[-1]
                for c in refresh.lower().split("from")[0].split(",")
                if "chat_messages." in c
            }
            assert selected == {"created_at"}, (
                f"preload should re-select only created_at, got {sorted(selected)}: {refresh}"
            )
            assert "users." not in refresh.lower(), (
                f"preload must not pull the user relationship: {refresh}"
            )
        finally:
            event.remove(bind, "before_cursor_execute", _record)
            # Else a non-RETURNING INSERT stays cached for the worker. Guarded
            # so a rename surfaces on the setup line, not from inside finally.
            cache = getattr(sa_inspect(models.ChatMessage), "_compiled_cache", None)
            if cache is not None:
                cache.clear()


def test_no_refresh_when_dialect_supplies_created_at(
    client, admin_auth_header, session_local, models
):
    """The gate must skip the refresh when RETURNING already supplied created_at.

    Dropping the guard for an unconditional refresh leaves every other test
    green while adding a SELECT per message. Skipped on MySQL, which has no
    RETURNING and legitimately needs one.
    """
    with session_local() as db:
        bind = db.get_bind()
        if not bind.dialect.insert_returning:
            pytest.skip("dialect has no INSERT..RETURNING; the guard cannot fire")

        selects = []
        # run_hooks opens its own session on this engine, so an engine-wide
        # listener would blame a registered hook's SELECTs on the helper.
        own_connection = db.connection().connection

        def _record(conn, cursor, statement, parameters, context, executemany):
            if conn.connection is not own_connection:
                return
            if statement.upper().lstrip().startswith("SELECT"):
                selects.append(statement)

        event.listen(bind, "before_cursor_execute", _record)
        try:
            msg = persist_and_fire_chat(db, user_id=1, username="carol", text="yo")
            assert msg.created_at is not None
            assert not [s for s in selects if "chat_messages" in s.lower()], (
                "created_at came back via RETURNING, so persist_and_fire_chat "
                f"should not have re-selected the row: {selects}"
            )
        finally:
            event.remove(bind, "before_cursor_execute", _record)
