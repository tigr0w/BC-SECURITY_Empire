from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from empire.server.core import plugin_registry_service as prs
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import PluginValidationException
from empire.server.utils.git_util import GitOperationException

REG_NAME = "RECONCILE-TEST"
OLD = {
    "schema_version": 1,
    "plugins": [
        {
            "name": "p",
            "description": "d",
            "versions": [{"name": "1.0.0", "git_url": "git@x:y", "ref": "old"}],
        }
    ],
}
NEW = {
    "schema_version": 1,
    "plugins": [
        {
            "name": "p",
            "description": "d",
            "versions": [{"name": "2.0.0", "git_url": "git@x:y", "ref": "new"}],
        }
    ],
}


@pytest.fixture
def cleanup_row():
    yield
    with SessionLocal.begin() as db:
        db.query(models.PluginRegistry).filter(
            models.PluginRegistry.name == REG_NAME
        ).delete()


@pytest.fixture
def seeded_row(cleanup_row):
    with SessionLocal.begin() as db:
        db.add(models.PluginRegistry(name=REG_NAME, location="l", url="u", data=OLD))


def _service(main):
    return main.pluginregistriesv2


def _patch_registry(monkeypatch, sync, *, location="l", url="u"):
    """Point the service at a single fake registry whose sync is `sync`.

    `auto_install` is kept on the stand-in because the live app booted by the
    session-scoped `client` fixture shares this config singleton.
    """
    monkeypatch.setattr(
        prs.empire_config,
        "plugin_marketplace",
        SimpleNamespace(
            registries=[SimpleNamespace(name=REG_NAME, location=location, url=url)],
            auto_install=[],
        ),
    )
    monkeypatch.setattr(prs, "sync_plugin_registry", sync)


def _synced_file(tmp_path, content: str | bytes):
    f = tmp_path / "registry.yaml"
    if isinstance(content, bytes):
        f.write_bytes(content)
    else:
        f.write_text(content)
    return f


def _row():
    with SessionLocal.begin() as db:
        row = (
            db.query(models.PluginRegistry)
            .filter(models.PluginRegistry.name == REG_NAME)
            .one()
        )
        return SimpleNamespace(data=row.data, location=row.location, url=row.url)


def _reload(main):
    with SessionLocal.begin() as db:
        _service(main).load_plugin_registries(db)


def test_reconcile_updates_existing_when_changed(
    main, seeded_row, monkeypatch, tmp_path
):
    f = _synced_file(tmp_path, yaml.safe_dump(NEW))
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "new"


def test_reconcile_updates_location_and_url_when_data_unchanged(
    main, seeded_row, monkeypatch, tmp_path
):
    # A config edit that only moves the registry leaves registry.yaml
    # byte-identical, so the row's location/url must reconcile independently
    # of the data differ.
    #
    # `location` is a Path in the real config (PluginRegistryConfig.location,
    # normalized by EmpireBaseModel.set_path), so pass one here -- the column
    # is Text and only str() of the Path belongs in it.
    f = _synced_file(tmp_path, yaml.safe_dump(OLD))
    moved = Path("/opt/registries/moved")
    _patch_registry(monkeypatch, lambda _: f, location=moved, url="moved-url")
    _reload(main)
    row = _row()
    assert row.data["plugins"][0]["versions"][0]["ref"] == "old"
    assert row.location == str(moved)
    assert row.url == "moved-url"


def test_reconcile_nulls_unset_location_and_url(
    main, seeded_row, monkeypatch, tmp_path
):
    # A git-only registry has neither `location` nor `url`; they must persist
    # as NULL, not the string "None".
    f = _synced_file(tmp_path, yaml.safe_dump(NEW))
    _patch_registry(monkeypatch, lambda _: f, location=None, url=None)
    _reload(main)
    row = _row()
    assert row.location is None
    assert row.url is None


def test_reconcile_keeps_row_on_sync_git_failure(main, seeded_row, monkeypatch):
    def _sync(_):
        raise GitOperationException("boom")

    _patch_registry(monkeypatch, _sync)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"


def test_reconcile_keeps_row_when_sync_returns_no_path(main, seeded_row, monkeypatch):
    _patch_registry(monkeypatch, lambda _: None)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"


def test_reconcile_keeps_row_on_malformed_yaml(main, seeded_row, monkeypatch, tmp_path):
    f = _synced_file(tmp_path, "plugins: [ unclosed\n  bad: :")
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"


def test_reconcile_keeps_row_on_non_utf8_registry(
    main, seeded_row, monkeypatch, tmp_path
):
    # A non-UTF-8 synced registry.yaml makes read_text(encoding="utf-8") raise
    # UnicodeDecodeError (a ValueError, not an OSError); the guard must keep
    # the last-good row instead of aborting startup.
    f = _synced_file(tmp_path, b"\xff\xff\xff plugins: []")
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"


def test_marketplace_excludes_rows_not_in_config(main, seeded_row):
    # Renaming or dropping a registry in config.yaml leaves its row behind
    # (reconcile only upserts). Surfacing it would list every plugin twice and
    # let install_plugin resolve the previous major line's refs.
    with SessionLocal.begin() as db:
        records = _service(main).get_marketplace(db)["records"]
    assert not any(REG_NAME in r["registries"] for r in records)


def test_install_rejects_registry_not_in_config(main, seeded_row):
    with SessionLocal.begin() as db, pytest.raises(PluginValidationException):
        _service(main).install_plugin(db, "p", "1.0.0", REG_NAME)


def test_reconcile_inserts_when_absent(main, cleanup_row, monkeypatch, tmp_path):
    f = _synced_file(tmp_path, yaml.safe_dump(NEW))
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "new"


def test_reconcile_inserts_null_location_and_url(
    main, cleanup_row, monkeypatch, tmp_path
):
    # The shipped git-only registry has neither `location` nor `url` and hits
    # the insert branch on a fresh install, so NULL has to hold there too --
    # not just on the update branch.
    f = _synced_file(tmp_path, yaml.safe_dump(NEW))
    _patch_registry(monkeypatch, lambda _: f, location=None, url=None)
    _reload(main)
    row = _row()
    assert row.location is None
    assert row.url is None


def test_reconcile_keeps_row_on_invalid_schema(main, seeded_row, monkeypatch, tmp_path):
    # Parses as YAML but fails PluginRegistry validation (no schema_version).
    f = _synced_file(tmp_path, yaml.safe_dump({"plugins": []}))
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"


def test_reconcile_keeps_row_on_unsupported_schema_version(
    main, seeded_row, monkeypatch, tmp_path
):
    f = _synced_file(tmp_path, yaml.safe_dump({**NEW, "schema_version": 99}))
    _patch_registry(monkeypatch, lambda _: f)
    _reload(main)  # must NOT raise
    assert _row().data["plugins"][0]["versions"][0]["ref"] == "old"
