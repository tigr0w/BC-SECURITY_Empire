import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from empire.server.core.db.models import all_tag_assc_tables
from empire.server.core.hooks import hooks
from empire.server.core.tag_service import TagService, color_from_name

HEX_COLOR_LENGTH = 7  # "#" + 6 hex digits
# delete_tag runs one `db.execute(delete(assc))` per association table, THEN the
# `db.execute(delete(models.Tag))`. begin_nested()'s SAVEPOINT is emitted at the
# connection level (not via Session.execute), so it doesn't count — the tags
# delete is therefore the (N assoc tables + 1)th execute. Targeting that exact
# call is what makes this test guard "the tags delete happens inside the
# savepoint": force the failure anywhere earlier and it would pass even if the
# tags delete were moved outside the savepoint.
TAGS_DELETE_CALL_INDEX = len(all_tag_assc_tables) + 1


def test_color_from_name_is_deterministic():
    assert color_from_name("prod") == color_from_name("prod")


def test_color_from_name_differs_by_name():
    assert color_from_name("prod") != color_from_name("staging")


def test_color_from_name_is_valid_hex():
    c = color_from_name("prod")
    assert c.startswith("#")
    assert len(c) == HEX_COLOR_LENGTH
    int(c[1:], 16)  # raises ValueError if not hex


def test_tag_hooks_exist():
    assert hooks.AFTER_TAG_ATTACHED_HOOK == "after_tag_attached_hook"
    assert hooks.AFTER_TAG_CREATED_HOOK == "after_tag_created_hook"
    assert hooks.AFTER_TAG_UPDATED_HOOK == "after_tag_updated_hook"


def test_update_tag_no_op_does_not_fire_updated_hook(session_local, models):
    service = TagService(None)
    calls = []
    hooks.register_hook(
        hooks.AFTER_TAG_UPDATED_HOOK, "test_no_op", lambda db, tag: calls.append(tag.id)
    )
    try:
        with session_local.begin() as db:
            tag = models.Tag(name="no_op_test", color="#abcdef")
            db.add(tag)
            db.flush()
            tag_id = tag.id

            # No fields changed -> the hook must not fire.
            service.update_tag(db, tag)
            assert calls == []

            # An actual change -> the hook fires exactly once.
            service.update_tag(db, tag, color="#123456")
            assert calls == [tag_id]
    finally:
        hooks.unregister_hook("test_no_op", hooks.AFTER_TAG_UPDATED_HOOK)


def test_delete_tag_converts_concurrent_attach_conflict_to_value_error(
    session_local, models, monkeypatch
):
    """SQLite doesn't enforce the tag_id FK (no PRAGMA foreign_keys=ON), so a real
    concurrent-attach-during-delete race can't be reproduced locally. Force the
    `IntegrityError` the FK would raise on MySQL to prove the savepoint around the
    deletes (not a later, separate flush) actually catches it."""
    service = TagService(None)
    with session_local.begin() as db:
        tag = models.Tag(name="delete_race_test", color="#abcdef")
        db.add(tag)
        db.flush()

        real_execute = db.execute
        calls = {"n": 0}

        def fake_execute(stmt, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == TAGS_DELETE_CALL_INDEX:
                raise IntegrityError("DELETE", {}, Exception("FK constraint failed"))
            return real_execute(stmt, *args, **kwargs)

        monkeypatch.setattr(db, "execute", fake_execute)

        with pytest.raises(ValueError, match="concurrently"):
            service.delete_tag(db, tag)


def test_attach_tag_survives_concurrent_attach_conflict(session_local, models):
    """Regression: a concurrent double-attach of the SAME existing tag to the SAME
    entity must NOT crash the request with an unhandled 500.

    The bug: `taggable.tags.append(tag)` ran BEFORE `begin_nested()`, so entering
    the savepoint autoflushed the conflicting association INSERT OUTSIDE the
    savepoint's protection. That poisoned the outer transaction, so the
    `except IntegrityError` recovery (`db.refresh(...)`) blew up with
    PendingRollbackError — an uncaught 500. Fix: append INSIDE the savepoint, so
    the conflicting flush rolls back to the savepoint and the recovery runs on a
    healthy transaction.

    Staged deterministically by committing the rival association from a second
    session while the SUT session holds a stale, empty tags collection. This drives
    the flush-conflict → recovery path (asserted below by "does not raise"). NOTE:
    we deliberately do NOT assert the 200-vs-404 recovery outcome here — whether
    the locking `db.refresh` observes the rival's just-committed row is
    isolation-level/engine dependent (on MariaDB REPEATABLE READ it may not), and
    that visibility question is orthogonal to the crash this test guards.
    """
    service = TagService(None)
    name = f"race_{uuid.uuid4().hex[:8]}"

    with session_local.begin() as setup:
        download = models.Download(location="racepath", filename="racefile", size=1)
        tag = models.Tag(name=name, color="#abcdef")
        setup.add_all([download, tag])
        setup.flush()
        download_id, tag_id = download.id, tag.id

    db = session_local()
    db.begin()
    try:
        taggable = db.get(models.Download, download_id)
        list(taggable.tags)  # load the (empty) collection — the stale snapshot

        # Operator A commits the rival association from a separate session.
        with session_local.begin() as other:
            other.execute(
                models.download_tag_assc.insert().values(
                    download_id=download_id, tag_id=tag_id
                )
            )

        # Operator B attaches the same tag. The pre-fix code raised
        # PendingRollbackError here (uncaught 500); post-fix it returns cleanly.
        _tag, created = service.attach_tag(db, taggable, tag_id=tag_id)
        assert created is False
        db.commit()
    finally:
        db.close()
