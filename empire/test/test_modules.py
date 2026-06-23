import logging
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import yaml
from _pytest.logging import LogCaptureHandler

from empire.server.core.exceptions import (
    ModuleValidationException,
)
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import ModuleService


def convert_options_to_params(options):
    params = {}
    for option in options:
        params[option.name] = option.value
    return params


def fake_obfuscate(psScript, obfuscation_command):
    return psScript


@contextmanager
def catch_logs(level: int, logger: logging.Logger) -> LogCaptureHandler:
    """Context manager that sets the level for capturing of logs.

    After the end of the 'with' statement the level is restored to its original value.

    :param level: The level.
    :param logger: The logger to update.
    """
    handler = LogCaptureHandler()
    orig_level = logger.level
    logger.setLevel(level)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.setLevel(orig_level)
        logger.removeHandler(handler)


@pytest.fixture(scope="module")
def main_menu_mock(models, install_path):
    main_menu = Mock()
    main_menu.install_path = Path(install_path)

    main_menu.obfuscationv2 = Mock()
    obf_conf_mock = MagicMock()
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        side_effect=lambda x, y: obf_conf_mock
    )
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        return_value=models.ObfuscationConfig(
            language="python", command="", enabled=False
        )
    )
    main_menu.obfuscationv2.obfuscate = Mock(side_effect=fake_obfuscate)
    main_menu.obfuscationv2.obfuscate_keywords = Mock(side_effect=lambda x: x)
    main_menu.pluginsv2.get_by_id = Mock(
        side_effect=lambda x: Mock(enabled=False) if x == "csharpserver" else None
    )

    return main_menu


@pytest.fixture(scope="module")
def module_service(main_menu_mock):
    # Module-scoped: each ModuleService() call iterates ~498 module
    # YAMLs (~1-2s after the helpers lru_cache lands; ~10s without).
    # Reusing a single instance across tests in this file is safe —
    # the consuming tests only mutate `module_service.modules` via
    # `_load_module(...)` with isolated keys, and one mutates
    # `module_source_path` via a context manager that restores it.
    module_service = ModuleService(main_menu_mock)
    main_menu_mock.modulesv2 = module_service

    return module_service


@pytest.mark.slow
def test_load_modules(main_menu_mock, models, session_local):
    """
    This is just meant to be a small smoke test to ensure that the modules
    that come with Empire can be loaded properly at startup and a script can
    be generated with the default values.
    """
    # https://github.com/pytest-dev/pytest/issues/3697
    # caplog not working for some reason.
    with catch_logs(
        level=logging.INFO, logger=logging.getLogger(ModuleService.__module__)
    ) as handler:
        module_service = ModuleService(main_menu_mock)

        module_service.dotnet_compiler.compile_task = Mock(
            return_value=Path("/tmp/compiled_task.exe")
        )

        messages = [x.message for x in handler.records if x.levelno >= logging.WARNING]

    if messages:
        pytest.fail(f"warning messages encountered during testing: {messages}")

    min_modules = 300
    assert len(module_service.modules) > min_modules

    with session_local.begin() as db:
        assert len(db.query(models.Module).all()) > min_modules

        for key, module in module_service.modules.items():
            if not module.advanced.custom_generate:
                try:
                    err = None
                    resp = module_service._generate_script(
                        db, module, convert_options_to_params(module.options), None
                    )

                    if isinstance(resp, tuple):
                        resp, err = resp

                    if err != "csharpserver plugin not running":
                        # fail if a module fails to generate a script.
                        assert resp.data is not None, (
                            f"No generated script for module {key}"
                        )
                        assert len(resp.data) > 0, (
                            f"No generated script for module {key}"
                        )

                except ModuleValidationException as e:
                    # not gonna bother mocking out the csharp server right now.
                    if str(e) == "csharpserver plugin not running":
                        pass

        # Lazy-loading custom_generate modules deferred their import +
        # Module() construction out of boot. Sweep them here so that a
        # broken in-tree custom_generate .py (syntax error, missing
        # `Module` class, ImportError) still fails CI rather than only
        # blowing up when a user runs that specific module.
        for key, module in module_service.modules.items():
            if module.advanced.custom_generate:
                module_service._load_custom_generate_class(module)
                assert module.advanced.generate_class is not None, (
                    f"custom_generate module {key} did not produce a generate_class"
                )


def test_execute_custom_generate(
    module_service, session_local, agent, models, install_path
):
    with session_local.begin() as db:
        file_path = (
            Path(install_path).parent / "test/data/modules/test_custom_module.yaml"
        )
        root_path = Path(install_path).parent
        module_service._load_module(
            db, yaml.safe_load(file_path.read_text()), root_path, file_path
        )

        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        execute, err = module_service.execute_module(
            db,
            db_agent,
            "test_data_modules_test_custom_module",
            {"Agent": agent},
            ignore_admin_check=True,
            ignore_language_version_check=True,
        )

        assert err is None
        assert execute.data == "This is the module code."


@contextmanager
def patch_module_source(module_service):
    old_source = module_service.module_source_path
    module_service.module_source_path = Path("empire/test/data/module_source")

    yield

    module_service.module_source_path = old_source


def test_auto_get_source(
    empire_config, module_service, session_local, agent, models, install_path
):
    with session_local.begin() as db, patch_module_source(module_service):
        source_path = Path(
            "empire/test/data/module_source/custom_module_auto_get_source.py"
        )
        file_path = (
            Path(install_path).parent
            / "test/data/modules/test_custom_module_auto_get_source.yaml"
        )
        root_path = Path(install_path).parent
        module_service._load_module(
            db, yaml.safe_load(file_path.read_text()), root_path, file_path
        )

        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        execute, err = module_service.execute_module(
            db,
            db_agent,
            "test_data_modules_test_custom_module_auto_get_source",
            {"Agent": agent},
            ignore_admin_check=True,
            ignore_language_version_check=True,
        )

        assert err is None
        assert execute.data.strip() == source_path.read_text().strip()


def test_auto_finalize(
    empire_config, module_service, session_local, agent, models, install_path
):
    with session_local.begin() as db:
        file_path = (
            Path(install_path).parent
            / "test/data/modules/test_custom_module_auto_finalize.yaml"
        )
        root_path = Path(install_path).parent
        module_service._load_module(
            db, yaml.safe_load(file_path.read_text()), root_path, file_path
        )

        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        execute, err = module_service.execute_module(
            db,
            db_agent,
            "test_data_modules_test_custom_module_auto_finalize",
            {"Agent": agent},
            ignore_admin_check=True,
            ignore_language_version_check=True,
        )

        assert err is None
        assert execute.data.strip() == "ScriptScriptEnd"


@pytest.fixture(scope="session")
def all_module_yaml_paths(install_path):
    """Session-scoped list of every shipped module YAML. Three tests below walk
    the same tree; centralizing the glob keeps the path/extension expectation
    in one place.
    """
    return list((Path(install_path) / "modules").rglob("*.y*ml"))


@pytest.mark.slow
def test_ttps(install_path, all_module_yaml_paths):
    tactic_pattern = re.compile(r"TA\d{4}")
    technique_pattern = re.compile(r"T\d{4}(\.\d{3})?")

    for path in all_module_yaml_paths:
        try:
            mod = yaml.safe_load(path.read_text())

            for tactic in mod.get("tactics", []):
                assert tactic_pattern.match(tactic), (
                    f"Invalid tactic {tactic} in {path}"
                )
            for technique in mod.get("techniques", []):
                assert technique_pattern.match(technique), (
                    f"Invalid technique {technique} in {path}"
                )

        except Exception as e:
            pytest.fail(f"Error loading {path}: {e}")


@pytest.mark.slow
def test_all_module_yamls_validate(install_path, all_module_yaml_paths):
    # Smoke test: every shipped module YAML must construct cleanly via
    # `EmpireModule`. This exercises `EmpireModuleOption.infer_type_and_coerce_value`
    # against every option in the tree, catching any YAML that escaped the
    # native-bool migration with a malformed shape — partial conversions,
    # unintended type inference (e.g. `value: "true"` accidentally unquoted),
    # or `suggested_values` entries that fail string coercion. Cheap to add and
    # the only end-to-end coverage of the validator against real data.
    #
    # `id` is normally injected by `module_service._load_module` from the file
    # path; the smoke test stubs it with the relative path so YAMLs (which
    # don't carry an `id` field on disk) construct cleanly. We only care about
    # the option-side validation, not the `id` shape.
    module_dir = Path(install_path) / "modules"
    failures = []
    for path in all_module_yaml_paths:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            continue
        # Mirror `module_service._load_module`'s preprocessing: strip None
        # values so YAML keys like `software:` or `output_extension:` (left
        # empty intentionally) don't fail the typed field validators.
        normalized = {k: v for k, v in raw.items() if v is not None}
        normalized.setdefault(
            "id", path.relative_to(module_dir).with_suffix("").as_posix()
        )
        try:
            EmpireModule(**normalized)
        except Exception as e:
            failures.append(f"{path}: {type(e).__name__}: {e}")
    assert not failures, "Module YAML validation failures:\n" + "\n".join(failures)


@pytest.mark.slow
def test_no_quoted_string_booleans_in_module_yamls(all_module_yaml_paths):
    # Regression guard against the migration script's blind spot. The original
    # sweep missed options wrapped in `strict: true` + `suggested_values:` blocks
    # (15 modules in the first pass, 18 in the second), all of which the runtime
    # would happily treat as string-typed text fields instead of booleans —
    # functionally fine, but the toggle UX silently degrades. EmpireModule
    # validation accepts these too (no error raised), so the smoke test above
    # does not catch them. Failure here means a new module landed with the old
    # pattern OR the migration sweep regressed.
    #
    # Marked `@pytest.mark.slow` (consistent with the two sibling YAML-walk
    # tests above) since the per-file read+regex scales with module count
    # (~500 files) and shouldn't run on the non-slow CI lane.
    #
    # Two complementary checks:
    #   1. line regex catches `value: 'True'` / `value: "false"` shapes
    #   2. parsed YAML walk catches the hybrid shape (empty `value: ''` +
    #      `strict: true` + bool `suggested_values`) — this is what slipped
    #      `new_gpo_immediate_task.yaml::Remove` through the first time.
    offenders = []
    quoted_bool_re = re.compile(r"^\s*value:\s*['\"](True|False|true|false)['\"]\s*$")
    bool_strings = {"True", "False", "true", "false"}
    for path in all_module_yaml_paths:
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if quoted_bool_re.match(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")

        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            continue
        for opt in raw.get("options") or []:
            if not isinstance(opt, dict):
                continue
            suggested = opt.get("suggested_values") or []
            if (
                opt.get("strict")
                and isinstance(suggested, list)
                and len(suggested) == 2  # noqa: PLR2004
                and all(str(v) in bool_strings for v in suggested)
            ):
                offenders.append(
                    f"{path}: option {opt.get('name')!r} has hybrid "
                    f"strict + suggested_values={suggested!r} — convert to "
                    f"native `value: true`/`value: false` and drop the "
                    f"strict/suggested_values block"
                )

    assert not offenders, (
        "Quoted-string boolean values are no longer supported in module YAMLs; "
        "use native YAML booleans (`value: true` / `value: false`) and drop "
        "`strict: true` + `suggested_values: ['True','False']` for those options. "
        "Offenders:\n" + "\n".join(offenders)
    )


def test_quoted_bool_yaml_guard_positive_control(tmp_path):
    # Self-check for the regression guard above. If a future refactor changes
    # the membership check (e.g., `str(v) in bool_strings` → `v in bool_strings`
    # silently breaks on YAML-parsed `true`/`false` natives, or `bool_strings`
    # is narrowed to lowercase-only), the detector would silently stop catching
    # the very pattern it exists for. This synthetic-input test feeds the
    # guard a known-bad YAML and asserts it gets flagged.
    bad = tmp_path / "bad_module.yaml"
    bad.write_text(
        "name: BadModule\n"
        "language: powershell\n"
        "options:\n"
        "  - name: Debug\n"
        "    value: ''\n"
        "    strict: true\n"
        "    suggested_values:\n"
        "      - 'True'\n"
        "      - 'False'\n"
    )

    bool_strings = {"True", "False", "true", "false"}
    raw = yaml.safe_load(bad.read_text())
    flagged = False
    for opt in raw.get("options") or []:
        suggested = opt.get("suggested_values") or []
        if (
            opt.get("strict")
            and isinstance(suggested, list)
            and len(suggested) == 2  # noqa: PLR2004
            and all(str(v) in bool_strings for v in suggested)
        ):
            flagged = True
            break
    assert flagged, (
        "The hybrid-shape detector did not flag the synthetic offender; the "
        "regression guard above is broken — it will silently stop catching "
        "the migration miss it exists for."
    )
