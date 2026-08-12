"""Unit tests for the CWD-independent path anchors in `paths`."""

from pathlib import Path

from empire.server.core.config import paths


def test_server_root_points_at_the_installed_server_package():
    assert paths.SERVER_ROOT.is_absolute()
    assert paths.SERVER_ROOT.name == "server"
    assert (paths.SERVER_ROOT / "config.yaml").exists()


def test_repo_root_contains_the_empire_package():
    assert paths.REPO_ROOT.is_absolute()
    assert (paths.REPO_ROOT / "empire" / "__init__.py").exists()
    assert paths.SERVER_ROOT == paths.REPO_ROOT / "empire" / "server"


def test_is_git_checkout_follows_repo_root_not_the_cwd(monkeypatch, tmp_path):
    """`is_git_checkout` must ignore the launch directory entirely.

    A packaged Empire launched from inside someone else's repository must not
    conclude that it is a git checkout, and so must not run git against it.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path / "not-a-checkout")

    assert paths.is_git_checkout() is False


def test_is_git_checkout_true_when_repo_root_has_dot_git(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)

    assert paths.is_git_checkout() is True


def test_is_git_checkout_handles_a_dot_git_file(monkeypatch, tmp_path):
    """In a git worktree `.git` is a file, not a directory."""
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)

    assert paths.is_git_checkout() is True


def test_paths_module_stays_side_effect_free():
    """conftest.py imports `paths` at pytest startup precisely because it does
    not create anything; adding a mkdir here would resurrect the DATA_DIR-wipe
    class of bug that forced the split in the first place."""
    source = Path(paths.__file__).read_text()
    for forbidden in ("mkdir(", "shutil."):
        assert forbidden not in source, (
            f"paths.py must stay side-effect-free; found {forbidden!r}"
        )
