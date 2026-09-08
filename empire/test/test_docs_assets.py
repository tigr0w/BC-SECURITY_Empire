"""Docs <-> .gitbook/assets integrity.

GitBook publishes docs/ verbatim, so a reference to a missing asset renders as a
broken image and an unreferenced asset is dead weight that still ships in the
repo. Both directions are cheap to check and neither needs a running server.

docs/superpowers/ is excluded: it is gitignored local planning material, not
published documentation.
"""

import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"
ASSETS_DIR = DOCS_DIR / ".gitbook" / "assets"
EXCLUDED_DIRS = {"superpowers"}

# Matches only real references: markdown `![](../.gitbook/assets/x.png)` and
# HTML `<img src="../.gitbook/assets/x.svg">`. Anchoring to `](` or `src=` keeps
# a prose mention of an asset path from counting as a reference — otherwise a
# page merely naming a file would mask it as an orphan.
ASSET_REF = re.compile(r"""(?:\]\(|src=["'])[^)"']*?\.gitbook/assets/([^)"'\s]+)""")


def _published_markdown() -> list[Path]:
    return [
        md
        for md in DOCS_DIR.rglob("*.md")
        if not EXCLUDED_DIRS & set(md.relative_to(DOCS_DIR).parts)
    ]


def _referenced_asset_names() -> set[str]:
    names = set()
    for md in _published_markdown():
        names.update(ASSET_REF.findall(md.read_text(encoding="utf-8")))
    return names


def _asset_files() -> set[str]:
    return {
        str(p.relative_to(ASSETS_DIR)) for p in ASSETS_DIR.rglob("*") if p.is_file()
    }


def test_every_referenced_asset_exists():
    missing = sorted(_referenced_asset_names() - _asset_files())
    assert not missing, (
        f"docs reference assets that do not exist in docs/.gitbook/assets: {missing}"
    )


def test_every_asset_is_referenced():
    orphans = sorted(_asset_files() - _referenced_asset_names())
    assert not orphans, (
        "assets in docs/.gitbook/assets are referenced by no published page. "
        f"Delete them or reference them: {orphans}"
    )
