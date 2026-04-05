"""Standalone compilation test for C# modules.

Reads module YAMLs directly and calls the real EmpireCompiler binary,
bypassing the full server/DB startup. Run locally with:

    ./ps-empire test --runslow empire/test/test_compile_csharp.py -v
"""

from pathlib import Path

import pytest
import yaml

try:
    from yaml import CSafeDumper as Dumper
except ImportError:
    from yaml import Dumper

from empire.server.core.dotnet import DotnetCompiler

MODULES_DIR = Path(__file__).resolve().parent.parent / "server" / "modules" / "csharp"
INSTALL_PATH = Path(__file__).resolve().parent.parent / "server"


def _build_compiler_yaml(yaml_module: dict) -> str:
    """Replicate the compiler_yaml generation from ModuleService._load_module."""
    dict_yaml = yaml_module.get("csharp", {}).copy()
    dict_yaml.update(
        {
            "Name": yaml_module.get("name", ""),
            "Language": yaml_module.get("language", ""),
            "TokenTask": False,
        }
    )

    dict_yaml["ReferenceSourceLibraries"] = [
        {
            "Name": ref_lib.get("Name", ""),
            "Description": ref_lib.get("Description", ""),
            "Location": ref_lib.get("Location", ""),
            "Language": ref_lib.get("Language", "CSharp"),
            "CompatibleDotNetVersions": ref_lib.get("CompatibleDotNetVersions", []),
            "ReferenceAssemblies": ref_lib.get("ReferenceAssemblies", []),
            "EmbeddedResources": ref_lib.get("EmbeddedResources", []),
        }
        for ref_lib in dict_yaml.get("ReferenceSourceLibraries", [])
    ]

    return yaml.dump(
        [dict_yaml],
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        Dumper=Dumper,
    )


def _collect_csharp_modules() -> list[tuple[str, dict]]:
    """Return (module_id, parsed_yaml) for every C# module YAML.

    Skips modules with empty Code (e.g. Spawn) that delegate compilation
    to another module at runtime.
    """
    modules = []
    for path in sorted(MODULES_DIR.rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw.get("language") != "csharp":
            continue
        if not raw.get("csharp", {}).get("Code"):
            continue
        module_id = path.relative_to(MODULES_DIR).with_suffix("").as_posix()
        modules.append(pytest.param(module_id, raw, id=module_id))
    return modules


@pytest.fixture(scope="module")
def compiler() -> DotnetCompiler:
    return DotnetCompiler(install_path=str(INSTALL_PATH))


@pytest.mark.slow
@pytest.mark.parametrize(("module_id", "raw"), _collect_csharp_modules())
def test_compile_csharp_module(compiler, module_id, raw):
    """Compile a single C# module with the real EmpireCompiler binary."""
    csharp_section = raw.get("csharp", {})
    dot_net_versions = csharp_section.get("CompatibleDotNetVersions", [])
    assert dot_net_versions, f"{module_id}: no CompatibleDotNetVersions defined"

    compiler_yaml = _build_compiler_yaml(raw)
    dot_net_version = dot_net_versions[0].lower()
    merge_refs = csharp_section.get("MergeReferences", False)

    compiled_path = compiler.compile_task(
        compiler_yaml,
        raw.get("name", module_id),
        dot_net_version=dot_net_version,
        merge_references=merge_refs,
    )
    assert compiled_path.exists(), f"{module_id}: compiled file not found"
    compiled_path.unlink(missing_ok=True)
    compiled_path.with_suffix(".exe").unlink(missing_ok=True)
