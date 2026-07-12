import os
import shutil
from pathlib import Path

import pytest

from empire.server.core.config import paths

# Test dirs use the same side-effect-free `paths` helpers as config_manager, with
# the isolated "empire-test" app name. We import `paths`, NOT `config_manager` —
# importing config_manager at startup would trigger its mkdir/config-copy side
# effects before _reset_test_dirs runs (see _reset_test_dirs for the invariant).
_REPO_ROOT = Path(__file__).resolve().parent
_TEST_CONFIG_DIR = paths.config_dir("empire-test")
_TEST_DATA_DIR = paths.data_dir("empire-test")
_TEST_CACHE_DIR = paths.cache_dir("empire-test")


def _worker_data_dir():
    """DATA_DIR for the current process — per-worker under pytest-xdist.

    Mirrors config_manager's DATA_DIR derivation: under xdist each worker owns
    ``empire-test/worker-<gw>`` (writable state), while the shared base
    ``empire-test`` holds the read-only caches symlinked into each worker dir.
    Keep in sync with the DATA_DIR branch of config_manager.py.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    return _TEST_DATA_DIR / f"worker-{worker}" if worker else _TEST_DATA_DIR


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--nodocker",
        action="store_true",
        default=False,
        help="skip tests that fail in docker",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "no_docker: mark test as failing in docker")
    config.addinivalue_line(
        "markers", "compiler: requires C# compiler (EmpireCompiler)"
    )
    config.addinivalue_line(
        "markers", "mysql: mark test as requiring MySQL (and Docker)"
    )
    _reset_test_dirs()


def _reset_test_dirs():
    """Reseed test-mode CONFIG_DIR and scrub per-run state once per pytest session.

    Owning this here in pytest_configure — rather than as a config_manager
    module-import side effect — makes it fire exactly once per session instead of
    once per subprocess (e.g. the perf-test Empire server), which used to defeat
    the in-process compiler cache.

    It used to ``rmtree`` the *entire* DATA_DIR every session, which wiped the
    cached ~540MB empire-compiler, the Starkiller clone, and the plugin-registry
    clones, forcing a full re-download on every run (~13s on CI, ~30s+ locally) —
    and, under pytest-xdist, once per worker. We now PRESERVE those read-only
    caches and scrub only the per-run mutable state subdirs. Test isolation does
    not depend on this wipe: the database is reset independently by
    reset_db()/startup_db() in the client fixture, and the per-run mutable dirs
    below are recreated by the app as needed.

    Cache dirs preserved (under DATA_DIR): empire-compiler/, starkiller/,
    plugin-registries/. Mutable dirs scrubbed: downloads/,
    obfuscated_module_source/. CACHE_DIR (the separate platform cache dir) holds
    the Go build cache; see the wipe-guard below for its xdist handling.

    The invariant we rely on: nothing imported during pytest startup or
    initial-conftest loading transitively imports config_manager. The first
    config_manager import happens later (during collection of test modules
    or fixture execution), by which point _reset_test_dirs has already run
    and empire/test/conftest.py has set sys.argv to point at
    test_server_config.yaml. So config_manager's module body — and the
    empire_config singleton it builds — uses the test config and sees a
    clean per-worker DATA_DIR.
    """
    if not os.environ.get("TEST_MODE"):
        return

    # CONFIG_DIR is tiny (just a copied config.yaml); a clean slate is cheap.
    shutil.rmtree(_TEST_CONFIG_DIR, ignore_errors=True)
    _TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # CACHE_DIR (separate platform cache dir) holds the shared Go build cache.
    # Without xdist we wipe it for a fresh per-session slate (7.0-dev behavior).
    # Under xdist it is a single location shared across all workers, so wiping it
    # from each worker's pytest_configure would race and force a full Go recompile
    # per worker — preserve it there, as with the DATA_DIR caches below.
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        shutil.rmtree(_TEST_CACHE_DIR, ignore_errors=True)

    # Preserve the heavy read-only caches under the shared base; scrub only the
    # per-run mutable state in this process's DATA_DIR (per-worker under xdist)
    # so cached external deps survive across sessions.
    _TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_dir = _worker_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    for mutable in ("downloads", "obfuscated_module_source"):
        shutil.rmtree(data_dir / mutable, ignore_errors=True)

    shutil.copy(
        _REPO_ROOT / "empire/test/test_registry_1.yaml",
        data_dir / "test_registry_1.yaml",
    )
    shutil.copy(
        _REPO_ROOT / "empire/test/test_registry_2.yaml",
        data_dir / "test_registry_2.yaml",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        pass
    else:
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    if config.getoption("--nodocker"):
        skip_docker = pytest.mark.skip(reason="skipping tests that fail in docker")
        for item in items:
            if "no_docker" in item.keywords:
                item.add_marker(skip_docker)
