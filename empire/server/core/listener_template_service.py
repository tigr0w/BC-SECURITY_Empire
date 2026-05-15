import fnmatch
import importlib.util
import logging
import typing

from sqlalchemy.orm import Session

from empire.server.core.db.base import SessionLocal
from empire.server.utils.string_util import slugify

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class ListenerTemplateService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

        # loaded listener format:
        #     {"listenerModuleName": moduleInstance, ...}
        self._loaded_listener_templates = {}

        with SessionLocal.begin() as db:
            self._load_listener_templates(db)

    def new_instance(self, template: str):
        instance = type(self._loaded_listener_templates[template])(self.main_menu)
        for value in instance.options.values():
            value.setdefault("SuggestedValues", [])
            value.setdefault("Strict", False)

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
        """
        Load listeners from the install + "/listeners/*" path
        """

        root_path = self.main_menu.install_path / "listeners"
        log.info(f"v2: Loading listener templates from: {root_path}")

        for file_path in root_path.rglob("*.py"):
            filename = file_path.name

            # don't load up any of the templates
            if fnmatch.fnmatch(filename, "*template.py"):
                continue

            # instantiate the listener module and save it to the internal cache
            listener_name = file_path.relative_to(root_path).with_suffix("").as_posix()
            spec = importlib.util.spec_from_file_location(listener_name, file_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            listener = mod.Listener(self.main_menu)

            self._apply_instance_option_defaults(listener)

            self._loaded_listener_templates[slugify(listener_name)] = listener
