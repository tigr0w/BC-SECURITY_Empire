"""Tests for PluginService install/merge helpers that the plugin API tests
(which need real git/network) don't reach: _merge_plugin_config, _download_tar,
and the install_plugin_from_git/tar orchestration.
"""

import shutil
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from empire.server.core import plugin_service
from empire.server.core.exceptions import PluginValidationException


# --------------------------------------------------------------------------- #
# _merge_plugin_config (pure static helper)
# --------------------------------------------------------------------------- #
def _cfg():
    return SimpleNamespace(
        name="myplugin", authors=["orig"], description="orig-desc", comments=["orig"]
    )


def test_merge_plugin_config_no_registry_returns_unchanged(client, main):
    cfg = _cfg()
    assert main.pluginsv2._merge_plugin_config(cfg, None) is cfg


def test_merge_plugin_config_plugin_absent_from_registry(client, main):
    cfg = _cfg()
    result = main.pluginsv2._merge_plugin_config(cfg, {"plugins": {}})
    assert result.authors == ["orig"]
    assert result.description == "orig-desc"


def test_merge_plugin_config_prefers_registry_fields(client, main):
    cfg = _cfg()
    registry = {
        "plugins": {
            "myplugin": {
                "authors": ["registry-author"],
                "description": "registry-desc",
                "comments": ["registry-comment"],
            }
        }
    }
    result = main.pluginsv2._merge_plugin_config(cfg, registry)
    assert result.authors == ["registry-author"]
    assert result.description == "registry-desc"
    assert result.comments == ["registry-comment"]


# --------------------------------------------------------------------------- #
# _download_tar
# --------------------------------------------------------------------------- #
def _make_tar(tmp_path, name="myplug.tar"):
    inner = tmp_path / "content.txt"
    inner.write_text("hello-plugin")
    tar_path = tmp_path / name
    with tarfile.open(tar_path, "w") as tar:
        tar.add(inner, arcname="content.txt")
    return tar_path


def test_download_tar_file_scheme_extracts(client, main, tmp_path):
    tar_path = _make_tar(tmp_path)
    temp_dir = main.pluginsv2._download_tar(f"file://{tar_path}")
    try:
        assert (Path(temp_dir) / "content.txt").read_text() == "hello-plugin"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_download_tar_file_scheme_missing_raises(client, main):
    with pytest.raises(PluginValidationException, match="Failed to download plugin"):
        main.pluginsv2._download_tar("file:///no/such/path/nope.tar")


def test_download_tar_http_success_extracts(client, main, tmp_path, monkeypatch):
    tar_path = _make_tar(tmp_path)
    raw = tar_path.open("rb")
    monkeypatch.setattr(
        plugin_service.requests,
        "get",
        lambda *a, **k: SimpleNamespace(status_code=200, raw=raw),
    )

    temp_dir = main.pluginsv2._download_tar("http://example.com/myplug.tar")
    try:
        assert (Path(temp_dir) / "content.txt").read_text() == "hello-plugin"
    finally:
        raw.close()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_download_tar_http_non_200_raises(client, main, monkeypatch):
    fake_response = SimpleNamespace(status_code=404, text="not found")
    monkeypatch.setattr(plugin_service.requests, "get", lambda *a, **k: fake_response)

    with pytest.raises(PluginValidationException, match="Failed to download plugin"):
        main.pluginsv2._download_tar("http://example.com/plugin.tar")


# --------------------------------------------------------------------------- #
# install_plugin_from_git / _from_tar orchestration
# --------------------------------------------------------------------------- #
def test_install_from_git_clones_then_validates(client, main, monkeypatch):
    svc = main.pluginsv2
    captured = {}
    monkeypatch.setattr(
        plugin_service.git_util, "clone_git_repo", lambda url, ref: "/tmp/cloned-repo"
    )
    monkeypatch.setattr(
        svc,
        "_validate_and_load_plugin",
        lambda *a, **k: captured.setdefault("args", a),
    )

    svc.install_plugin_from_git(
        None,
        "https://github.com/x/y",
        subdir="sub",
        ref="main",
        version_name="1.0",
        registry_data={"r": 1},
    )

    # temp_dir from the clone is forwarded to validation.
    assert captured["args"][1] == "/tmp/cloned-repo"


def test_install_from_tar_downloads_then_validates(client, main, monkeypatch):
    svc = main.pluginsv2
    captured = {}
    monkeypatch.setattr(svc, "_download_tar", lambda url: "/tmp/extracted-tar")
    monkeypatch.setattr(
        svc,
        "_validate_and_load_plugin",
        lambda *a, **k: captured.setdefault("args", a),
    )

    svc.install_plugin_from_tar(
        None,
        "http://x/y.tar",
        subdir="sub",
        version_name="1.0",
        registry_data=None,
    )

    assert captured["args"][1] == "/tmp/extracted-tar"
