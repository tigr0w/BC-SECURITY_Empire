"""Unit tests for ListenerTemplateService plugin-registration hooks.

These tests avoid the session-scoped ``client`` fixture so they run
quickly and don't require a full Empire boot. The service is
instantiated against a minimal stub ``MainMenu`` that just exposes an
``install_path``.
"""

from pathlib import Path

import pytest

from empire.server.core.listener_template_service import ListenerTemplateService


class _StubMainMenu:
    def __init__(self, install_path: Path):
        self.install_path = install_path


class _StubListener:
    """Minimal listener-template-shaped object for registration tests."""

    def __init__(self, main_menu, name: str = "FakeBridge"):
        self.main_menu = main_menu
        self.info = {
            "Name": name,
            "Authors": [],
            "Description": "test",
            "Comments": [],
            "Software": "",
            "Techniques": [],
            "Tactics": [],
        }
        self.options = {
            "Name": {
                "Description": "Name",
                "Required": True,
                "Value": name.lower(),
            },
            "PollInterval": {
                "Description": "Seconds between polls",
                "Required": True,
                "Value": 5,
            },
        }


@pytest.fixture
def service(client, install_path):
    """Fresh ListenerTemplateService per test.

    Depends on ``client`` solely to ensure ``startup_db`` has run so that
    ``SessionLocal.begin()`` inside the service constructor works; we do
    not touch the running Empire instance.
    """
    _ = client
    return ListenerTemplateService(_StubMainMenu(Path(install_path)))


class TestRegisterListenerTemplate:
    def test_registers_new_template_under_slugified_name(self, service):
        listener = _StubListener(service.main_menu, name="Bridge OneDrive")

        key = service.register_listener_template(listener)

        assert key == "bridge_onedrive"
        assert service.get_listener_template("bridge_onedrive") is listener

    def test_applies_option_defaults(self, service):
        listener = _StubListener(service.main_menu)

        service.register_listener_template(listener)

        for opt in listener.options.values():
            assert opt["SuggestedValues"] == []
            assert opt["Strict"] is False
            assert opt["Internal"] is False
            assert opt["DependsOn"] == []

    def test_rejects_duplicate_registration(self, service):
        listener = _StubListener(service.main_menu, name="DupBridge")
        service.register_listener_template(listener)

        with pytest.raises(ValueError, match="already registered"):
            service.register_listener_template(
                _StubListener(service.main_menu, "DupBridge")
            )

    def test_explicit_name_overrides_info_name(self, service):
        listener = _StubListener(service.main_menu, name="IgnoredName")

        key = service.register_listener_template(listener, name="Custom Name")

        assert key == "custom_name"
        assert service.get_listener_template("custom_name") is listener

    def test_in_tree_templates_still_loaded(self, service):
        # Sanity check: the auto-discovered listeners (http, smb, etc.) are
        # still present alongside any we register.
        assert service.get_listener_template("http") is not None


class TestUnregisterListenerTemplate:
    def test_removes_registered_template(self, service):
        # "Remove Me" slugifies to "remove_me"; "RemoveMe" slugifies to
        # "removeme". Use a two-word name so the round-trip exercises
        # the slugify path rather than accidentally asserting a miss.
        listener = _StubListener(service.main_menu, name="Remove Me")
        key = service.register_listener_template(listener)
        assert key == "remove_me"
        assert service.get_listener_template("remove_me") is listener

        assert service.unregister_listener_template("Remove Me") is True
        assert service.get_listener_template("remove_me") is None

    def test_returns_false_when_missing(self, service):
        assert service.unregister_listener_template("never_existed") is False

    def test_registering_in_tree_slug_is_rejected(self, service):
        """A plugin must not be able to shadow an auto-discovered template
        (e.g. ``http``) by registering under the same slug."""
        listener = _StubListener(service.main_menu, name="HTTP")
        with pytest.raises(ValueError, match="already registered"):
            service.register_listener_template(listener)


class TestConstructFreshInstance:
    def test_new_instance_populates_options_for_yaml_listener(self, service):
        # http is a known in-tree listener; after migration it is YAML-backed.
        # Pre-migration it is flat .py. Either way, new_instance must return an
        # instance whose options are populated (regression guard for the
        # empty-options critical).
        instance = service.new_instance("http")
        assert "Name" in instance.options
        assert "Host" in instance.options
        for opt in instance.options.values():
            assert "SuggestedValues" in opt
            assert "Strict" in opt

    def test_new_instance_returns_distinct_instances(self, service):
        a = service.new_instance("http")
        b = service.new_instance("http")
        assert a is not b


class TestReservedDirsSkipped:
    def test_template_dir_is_skipped(self, service):
        # ``listeners/template/`` is a documentation example, not a usable
        # listener. The loader skips it by reserved-name, so it must never be
        # registered.
        assert service.get_listener_template("template") is None
