import importlib.util
import logging
import typing
from copy import deepcopy
from typing import ClassVar

from sqlalchemy.orm import Session

from empire.server.core.db.base import SessionLocal
from empire.server.utils.listener_template_util import load_listener_template_yaml
from empire.server.utils.string_util import slugify

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class ListenerTemplateService:
    RESERVED_DIRS: ClassVar[set[str]] = {"common", "template"}

    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

        # loaded listener format:
        #     {"listenerModuleName": moduleInstance, ...}
        self._loaded_listener_templates = {}
        # key -> {"info": dict, "options": dict}; only for YAML-backed listeners.
        self._loaded_listener_yaml: dict[str, dict] = {}
        # key -> Listener class (YAML-backed), so we don't re-exec_module.
        self._loaded_listener_classes: dict[str, type] = {}

        with SessionLocal.begin() as db:
            self._load_listener_templates(db)

    def new_instance(self, template: str):
        if template in self._loaded_listener_classes:
            return self._construct(template)

        # Plugin-registered instance: reconstruct from the cached instance's
        # class and apply the standard option defaults (SuggestedValues/Strict/
        # Internal/DependsOn) so it matches the load-time default set.
        instance = type(self._loaded_listener_templates[template])(self.main_menu)
        self._apply_instance_option_defaults(instance)
        return instance

    def get_listener_template(self, name: str) -> object | None:
        return self._loaded_listener_templates.get(name)

    def get_listener_templates(self):
        return self._loaded_listener_templates

    def register_listener_template(self, instance, name: str | None = None) -> str:
        """
        Register an externally-provided listener template (e.g. from a plugin).

        Plugins should call this from ``on_load`` via
        ``BasePlugin.register_listener`` so the template is visible before
        ``ListenerService.start_existing_listeners`` boots DB-persisted
        listeners.

        :param instance: Instantiated listener (already ``Listener(main_menu)``).
        :param name: Optional template name. Defaults to
            ``slugify(instance.info["Name"])``.
        :return: The slugified key the template was registered under.
        :raises ValueError: If a template with that key is already registered.
        """
        if name is None:
            name = instance.info["Name"]
        key = slugify(name)

        if key in self._loaded_listener_templates:
            msg = f"Listener template '{key}' is already registered"
            raise ValueError(msg)

        self._apply_instance_option_defaults(instance)
        self._loaded_listener_templates[key] = instance
        log.info(f"v2: Registered external listener template: {key}")
        return key

    def unregister_listener_template(self, name: str) -> bool:
        """
        Remove a previously-registered listener template.

        Does not stop any listeners already instantiated from it; callers
        are responsible for stopping listeners first. Returns True if a
        template was removed, False if no such template existed.
        """
        key = slugify(name)
        if key not in self._loaded_listener_templates:
            return False
        del self._loaded_listener_templates[key]
        log.info(f"v2: Unregistered listener template: {key}")
        return True

    @staticmethod
    def _apply_instance_option_defaults(instance) -> None:
        for value in instance.options.values():
            value.setdefault("SuggestedValues", [])
            value.setdefault("Strict", False)
            value.setdefault("Internal", False)
            value.setdefault("DependsOn", [])

    def _load_listener_templates(self, db: Session):
        """Load listeners from ``<install>/listeners``.

        Listeners use the folder + YAML format: ``listeners/<name>/listener.py``
        plus a single ``<name>.yaml``. Metadata/options come from the YAML; the
        class is cached and instances are built via :meth:`_construct`.
        Plugin-registered templates use :meth:`register_listener_template`.
        """
        root_path = self.main_menu.install_path / "listeners"
        log.info(f"v2: Loading listener templates from: {root_path}")

        # Folder + YAML listeners.
        for dir_path in sorted(p for p in root_path.iterdir() if p.is_dir()):
            if dir_path.name in self.RESERVED_DIRS:
                continue
            yaml_files = list(dir_path.glob("*.y*ml"))
            listener_py = dir_path / "listener.py"
            if not yaml_files or not listener_py.exists():
                # Not a folder-format listener; simply ignored.
                continue
            if len(yaml_files) > 1:
                log.error(
                    f"v2: {dir_path.name} has multiple YAML files; skipping: "
                    f"{[p.name for p in yaml_files]}"
                )
                continue
            self._load_yaml_listener(dir_path, listener_py, yaml_files[0])

        expected = {
            "http",
            "http_malleable",
            "http_foreign",
            "http_hop",
            "smb",
            "port_forward_pivot",
        }
        missing = expected - set(self._loaded_listener_yaml)
        if missing:
            raise RuntimeError(f"Listener templates failed to load: {sorted(missing)}")

    def _load_yaml_listener(self, dir_path, listener_py, yaml_path):
        parsed = load_listener_template_yaml(yaml_path)
        key = slugify(parsed["id"])
        if key != parsed["id"] or key != dir_path.name:
            raise ValueError(
                f"Listener '{dir_path.name}': id '{parsed['id']}' must be a "
                f"bare slug equal to its folder name (slugify -> '{key}')."
            )

        spec = importlib.util.spec_from_file_location(
            f"{dir_path.name}.listener", listener_py
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self._loaded_listener_classes[key] = mod.Listener
        self._loaded_listener_yaml[key] = {
            "info": parsed["info"],
            "options": parsed["options"],
        }
        self._loaded_listener_templates[key] = self._construct(key)
        log.info(f"v2: Loaded YAML listener template: {key}")

    def _construct(self, key: str):
        """Build a fully populated listener instance for a YAML-backed key.

        Ordering is load-bearing: construct -> inject info/options -> apply
        option defaults -> post_init (which may read option values and the DB).
        """
        instance = self._loaded_listener_classes[key](self.main_menu)
        instance.info = deepcopy(self._loaded_listener_yaml[key]["info"])
        instance.options = deepcopy(self._loaded_listener_yaml[key]["options"])
        self._apply_instance_option_defaults(instance)
        if hasattr(instance, "post_init"):
            instance.post_init()
        return instance
