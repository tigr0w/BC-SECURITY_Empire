import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette import status

from empire.server.api import app as app_module
from empire.server.api.app import create_app


def test_get_main_returns_503_before_lifespan_startup(admin_auth_header):
    """A request arriving before the lifespan populates app.state.main should
    get a clean 503, not an AttributeError/500.

    Using a bare TestClient (no `with` block) deliberately skips the lifespan,
    so app.state.main stays None — the pre-startup window get_main guards.
    """
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v2/listeners/", headers=admin_auth_header)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "not initialized" in response.json()["detail"].lower()


class FakeApp:
    """`load_starkiller` mounts the build with `app.frontend(...)`; the served
    directory is the thing worth asserting on, so capture it.
    """

    def __init__(self):
        self.served = None

    def frontend(self, _route, directory):
        self.served = directory


def _serve(monkeypatch, starkiller_dir, directory):
    monkeypatch.setattr(app_module, "sync_starkiller", lambda _cfg: starkiller_dir)
    monkeypatch.setattr(app_module.empire_config.starkiller, "directory", directory)
    app = FakeApp()
    app_module.load_starkiller(app, 1337)
    return app.served


def test_load_starkiller_unbuilt_checkout_is_diagnosed_not_served(
    tmp_path, monkeypatch, caplog
):
    """An unbuilt checkout has the entry template and no `dist/`. Serving it
    on the strength of index.html alone would render a blank page; the
    `package.json` beside it is what marks it as source rather than build.
    """
    checkout = tmp_path / "starkiller"
    checkout.mkdir()
    (checkout / "index.html").write_text('<script src="/src/main.js">')
    (checkout / "package.json").write_text("{}")

    with caplog.at_level(logging.WARNING):
        served = _serve(monkeypatch, checkout, str(checkout))

    assert served is None
    assert "has not been built" in caplog.text


def test_load_starkiller_no_build_at_all_names_the_override(
    tmp_path, monkeypatch, caplog
):
    """A directory that exists but holds neither layout. The warning must name
    the key rather than telling an operator who just built Starkiller to build
    Starkiller.
    """
    build_dir = tmp_path / "starkiller-build"
    build_dir.mkdir()  # exists, but holds no build

    with caplog.at_level(logging.WARNING):
        served = _serve(monkeypatch, build_dir, str(build_dir))

    assert served is None
    assert "starkiller.directory" in caplog.text
    assert "Run a Starkiller build first" not in caplog.text


def test_load_starkiller_missing_override_directory_names_the_path(
    tmp_path, monkeypatch, caplog
):
    """A typo'd `directory` doesn't exist at all, so a hint about the expected
    layout is the wrong diagnosis -- it tells the operator to look inside a
    directory that isn't there, when the path itself is the bug.
    """
    missing = tmp_path / "does-not-exist"

    with caplog.at_level(logging.WARNING):
        served = _serve(monkeypatch, missing, str(missing))

    assert served is None
    assert "does not exist" in caplog.text
    assert str(missing) in caplog.text
    assert "must point at a built Starkiller" not in caplog.text


def test_load_starkiller_missing_dist_without_override_keeps_build_hint(
    tmp_path, monkeypatch, caplog
):
    """Without an override the original advice is still the right advice."""
    build_dir = tmp_path / "starkiller-clone"
    build_dir.mkdir()

    with caplog.at_level(logging.WARNING):
        served = _serve(monkeypatch, build_dir, None)

    assert served is None
    assert "Run a Starkiller build first" in caplog.text


@pytest.mark.parametrize("nested", [True, False], ids=["checkout", "flattened"])
def test_a_directory_override_is_actually_served_over_http(
    tmp_path, monkeypatch, nested
):
    """The other `load_starkiller` tests capture the argument on a stub, so they
    pin which directory we would serve, not that it is served. This one mounts
    on a real FastAPI and fetches the page.

    Both layouts, because `app.frontend(route, directory=...)` is upstream's
    contract, not ours: `directory` is typed `str | os.PathLike[str]` and we
    hand it a `Path`. A renamed keyword, a narrowed type, or an index.html
    upstream declines to serve from a mount root would leave every stubbed test
    green and 404 the UI -- and the flattened case is the packaged install this
    override exists for, so "it works for a git checkout" is not enough.
    """
    build = tmp_path / "starkiller"
    served_from = build / "dist" if nested else build
    served_from.mkdir(parents=True)
    (served_from / "index.html").write_text("<h1>starkiller</h1>")

    monkeypatch.setattr(app_module, "sync_starkiller", lambda _cfg: build)
    monkeypatch.setattr(app_module.empire_config.starkiller, "directory", str(build))
    app = FastAPI()
    app_module.load_starkiller(app, 1337)

    response = TestClient(app).get("/")

    assert response.status_code == status.HTTP_200_OK
    assert "<h1>starkiller</h1>" in response.text


def _sync_raises(monkeypatch, directory):
    def boom(_cfg):
        raise OSError("boom")

    monkeypatch.setattr(app_module, "sync_starkiller", boom)
    monkeypatch.setattr(app_module.empire_config.starkiller, "directory", directory)
    app_module.load_starkiller(FakeApp(), 1337)


def test_load_starkiller_ssh_hint_is_suppressed_under_a_directory_override(
    tmp_path, monkeypatch, caplog
):
    """Nothing is fetched under an override, so credentials cannot be the
    cause -- the hint would send the operator to debug ssh keys for what is
    really a filesystem problem.
    """
    with caplog.at_level(logging.WARNING):
        _sync_raises(monkeypatch, str(tmp_path / "starkiller"))

    assert "Failed to load Starkiller" in caplog.text
    assert "ssh credentials" not in caplog.text


def test_load_starkiller_ssh_hint_still_fires_for_the_clone_path(monkeypatch, caplog):
    """The negative half: without an override a clone was attempted, and a
    private Starkiller-Sponsors checkout failing on credentials is the single
    likeliest cause. Paired with the test above so the gate can't be widened
    to "never warn" without one of them failing.
    """
    with caplog.at_level(logging.WARNING):
        _sync_raises(monkeypatch, None)

    assert "ssh credentials" in caplog.text
