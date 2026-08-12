"""The `empire-server` dispatcher.

The CLI dispatch (subcommand handling, the bare-invocation usage error) can
only be exercised end-to-end as a subprocess, since it drives argv and calls
`sys.exit`. `main.py` is otherwise uncovered: `arguments.py` builds its parser
at import but no longer parses at import, so importing the module is safe --
which `test_importing_the_dispatcher_does_not_parse_argv` pins in place.
"""

import importlib
import os
import subprocess
import sys

from empire.server.core.config import paths

# argparse's own exit code for a usage error.
USAGE_ERROR = 2


def test_importing_the_dispatcher_does_not_parse_argv():
    """`import empire.main` must not touch argv or exit.

    The console-script target is imported by anything that resolves the entry
    point -- a packager's import check (nixpkgs `pythonImportsCheck`), autodoc,
    `python -c "import empire.main"`. Parsing at import made all of those exit 2
    on the test runner's argv.
    """
    importlib.import_module("empire.main")


def _run_bare(**env_overrides):
    return subprocess.run(
        [sys.executable, "empire.py"],
        cwd=paths.REPO_ROOT,
        env={**os.environ, **env_overrides},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_a_bare_invocation_is_a_usage_error():
    result = _run_bare()

    assert result.returncode == USAGE_ERROR, result.stdout + result.stderr
    assert "usage: " in result.stdout


def test_a_bare_invocation_never_reaches_the_server():
    """The usage error must be reported before anything is imported.

    argparse prints help and returns, so the dispatcher used to fall through
    and import the whole server -- and `db.base` builds its engine at import
    time, which for MySQL connects. Pointing at a closed port proves nothing
    on that path runs: a connection attempt here could only fail.
    """
    result = _run_bare(
        EMPIRE_DATABASE__USE="mysql",
        EMPIRE_DATABASE__MYSQL__URL="127.0.0.1:1",
    )

    assert result.returncode == USAGE_ERROR, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
