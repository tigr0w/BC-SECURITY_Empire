import logging
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


def test_unregister_without_event_tolerates_a_miss():
    """A hook is registered under one event, not all of them."""
    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "test_hook", callback_hook)
    # A second event with a registration, so the no-event sweep has to survive
    # a key that doesn't hold the name. Registered here rather than relying on
    # whatever the app boot happened to leave in the singleton.
    hooks.register_hook(hooks.AFTER_AGENT_CHECKIN_HOOK, "survivor", callback_hook)
    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "test_filter", callback_filter
    )

    hooks.unregister_hook("test_hook")
    hooks.unregister_filter("test_filter")
    # The realistic trigger: an on_unload defensively unregistering a hook its
    # on_start never got as far as registering.
    hooks.unregister_hook("never_registered")
    hooks.unregister_filter("never_registered")

    assert hooks.hooks.get(hooks.AFTER_TASKING_RESULT_HOOK).get("test_hook") is None
    assert (
        hooks.filters.get(hooks.BEFORE_TASKING_RESULT_FILTER).get("test_filter") is None
    )
    # Unregistering one name must not clear unrelated events.
    assert hooks.hooks[hooks.AFTER_AGENT_CHECKIN_HOOK]["survivor"] is callback_hook


def test_run_hooks_survives_a_hook_that_unregisters_itself():
    """Now that the no-event form works, the one-shot-hook pattern is reachable."""
    ran = []

    def self_removing(task):
        ran.append("self_removing")
        hooks.unregister_hook("self_removing")

    def other(task):
        ran.append("other")

    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "self_removing", self_removing)
    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "other", other)

    # Without the list() snapshot in run_hooks this raises RuntimeError out of
    # the iterator -- past the handler -- and `other` never runs.
    hooks.run_hooks(hooks.AFTER_TASKING_RESULT_HOOK, {})

    assert ran == ["self_removing", "other"]
    assert hooks.hooks[hooks.AFTER_TASKING_RESULT_HOOK].get("self_removing") is None


def test_run_filters_survives_a_filter_that_unregisters_itself():
    """run_filters needs the same snapshot as run_hooks, on a hotter path.

    Filters run from _process_agent_packet, so a RuntimeError out of the
    iterator lands in agent packet processing rather than being logged.
    """
    ran = []

    def self_removing(task):
        ran.append("self_removing")
        hooks.unregister_filter("self_removing")
        return task

    def other(task):
        ran.append("other")
        return {"test": "updated"}

    hooks.register_filter(
        hooks.BEFORE_TASKING_RESULT_FILTER, "self_removing", self_removing
    )
    hooks.register_filter(hooks.BEFORE_TASKING_RESULT_FILTER, "other", other)

    returned = hooks.run_filters(hooks.BEFORE_TASKING_RESULT_FILTER, {"test": "test"})

    assert ran == ["self_removing", "other"]
    assert returned.get("test") == "updated"


def test_unregister_warns_when_nothing_matched(caplog):
    """Tolerating the miss is deliberate; doing it silently is not.

    A typo'd or renamed name looks exactly like a legitimate defensive
    unregister, but leaves the real hook firing against a torn-down plugin
    with its exceptions swallowed by run_hooks.
    """
    hooks.register_hook(hooks.AFTER_TASKING_RESULT_HOOK, "real_name", callback_hook)

    with caplog.at_level(logging.WARNING):
        hooks.unregister_hook("typo_name")
        hooks.unregister_hook("typo_with_event", hooks.AFTER_TASKING_RESULT_HOOK)
        hooks.unregister_filter("typo_filter")

    assert "typo_name" in caplog.text
    assert "typo_with_event" in caplog.text
    assert "typo_filter" in caplog.text
    # The hook that does exist is untouched, and removing it says nothing.
    # Not `caplog.text == ""`: caplog captures the root logger, so any warning
    # from the session-scoped app's threads would fail this for no reason.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        hooks.unregister_hook("real_name")
    assert "real_name" not in caplog.text


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
