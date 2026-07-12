from unittest.mock import Mock

import pytest

from empire.server.core.hooks import hooks


@pytest.fixture(autouse=True)
def _restore_hooks_registry():
    """Snapshot and restore the process-global hooks/filters registry per test.

    ``hooks`` is a singleton. Several tests below register hooks/filters without
    unregistering them; in serial alphabetical order nothing downstream noticed,
    but under pytest-xdist a leaked BEFORE_TASKING_RESULT_FILTER (e.g.
    ``callback_filter_multi``, which returns a ``{"fake_db": True}`` db) corrupts
    other test files sharing the worker — _process_agent_packet then runs
    ``db.flush()`` on a dict. Restoring keeps every test hermetic regardless of
    cross-file execution order.
    """
    saved_hooks = {k: dict(v) for k, v in hooks.hooks.items()}
    saved_filters = {k: dict(v) for k, v in hooks.filters.items()}
    yield
    hooks.hooks.clear()
    hooks.hooks.update(saved_hooks)
    hooks.filters.clear()
    hooks.filters.update(saved_filters)


def callback_hook(task):
    pass


def callback_filter(task):
    return {"test": "test"}


def callback_filter_multi(db, task):
    return {"fake_db": True}, {"test": "updated"}


def test_register_hook():
    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "test_hook", callback_hook)
    assert (
        hooks.hooks.get(hooks.AFTER_TASKING_RESULT_HOOK).get("test_hook")
        == callback_hook
    )

    hooks.unregister_hook("test_hook", hooks.AFTER_TASKING_RESULT_HOOK)
    assert hooks.hooks.get(hooks.AFTER_TASKING_RESULT_HOOK).get("test_hook") is None


def test_register_filter():
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "test_filter", callback_filter
    )
    assert (
        hooks.filters.get(hooks.BEFORE_TASKING_RESULT_FILTER).get("test_filter")
        == callback_filter
    )

    hooks.unregister_filter("test_filter", hooks.BEFORE_TASKING_RESULT_FILTER)
    assert (
        hooks.filters.get(hooks.BEFORE_TASKING_RESULT_FILTER).get("test_filter") is None
    )


def test_run_hook():
    mock_hook = Mock()
    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "test_hook", mock_hook)

    obj = {}
    hooks.run_hooks(hooks.AFTER_TASKING_RESULT_HOOK, obj)

    assert mock_hook.call_count == 1
    assert mock_hook.call_args[0][0] == obj


def test_run_filter():
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "test_filter", callback_filter
    )

    returned = hooks.run_filters(hooks.BEFORE_TASKING_RESULT_FILTER, {})

    assert returned.get("test") == "test"


def test_run_filter_multi_param():
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "test_filter", callback_filter_multi
    )

    db, task = hooks.run_filters(
        hooks.BEFORE_TASKING_RESULT_FILTER, {"fake_db": True}, {"test": "test"}
    )

    assert db.get("fake_db") is True
    assert task.get("test") == "updated"
