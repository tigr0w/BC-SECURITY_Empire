from unittest.mock import Mock

from empire.server.common.hooks import hooks


def callback_hook(tasking):
    pass


def callback_filter(tasking):
    return {"test": "test"}


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
