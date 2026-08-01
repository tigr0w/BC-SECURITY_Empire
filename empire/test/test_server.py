from pathlib import Path

from empire.server import server


def test_clean_wipes_config_data_and_cache(monkeypatch):
    """`server --clean` must wipe CONFIG_DIR, DATA_DIR, and CACHE_DIR.

    The CACHE_DIR wipe is load-bearing now that the cache lives outside DATA_DIR
    (platformdirs migration, #960); previously ``rmtree(DATA_DIR)`` covered it.
    """
    removed: list[Path] = []
    monkeypatch.setattr(server.shutil, "rmtree", lambda p, **k: removed.append(Path(p)))
    monkeypatch.setattr(server.base, "reset_db", lambda: None)

    server.clean()

    assert set(removed) == {server.CONFIG_DIR, server.DATA_DIR, server.CACHE_DIR}
