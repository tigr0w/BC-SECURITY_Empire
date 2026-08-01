import logging
import typing
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import select

from empire.server.core.config.config_manager import empire_config
from empire.server.core.config.data_manager import sync_plugin_registry
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import PluginValidationException
from empire.server.core.module_models import EmpireAuthor
from empire.server.utils.git_util import GitOperationException

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class PluginRegistryPluginVersion(BaseModel):
    git_url: str | None = None
    tar_url: str | None = None
    subdirectory: str | None = None
    ref: str | None = None
    name: str

    @model_validator(mode="before")
    @classmethod
    def validate_git_or_tar(cls, values):
        if not values.get("git_url") and not values.get("tar_url"):
            raise ValueError("Either git_url or tar_url must be set")
        return values


class PluginRegistryPlugin(BaseModel):
    name: str
    homepage_url: str | None = None
    source_url: str | None = None
    authors: list[EmpireAuthor] = []
    versions: list[PluginRegistryPluginVersion] = []
    description: str


class PluginRegistry(BaseModel):
    schema_version: int
    plugins: list[PluginRegistryPlugin]


class PluginRegistryService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.plugin_service = main_menu.pluginsv2

        with SessionLocal.begin() as db:
            self.load_plugin_registries(db)

    def load_plugin_registries(self, db):
        registries = empire_config.plugin_marketplace.registries
        for r in registries:
            try:
                synced_path = sync_plugin_registry(r)
                registry_file = Path(synced_path) if synced_path else None
                if not (registry_file and registry_file.exists()):
                    log.error(f"Failed to load plugin registry {r.name}")
                    continue
                registry_data = yaml.safe_load(
                    registry_file.read_text(encoding="utf-8")
                )
                registry = PluginRegistry.model_validate(registry_data)
            except (GitOperationException, OSError, UnicodeError, yaml.YAMLError):
                log.exception(
                    f"Plugin registry {r.name}: sync/parse failed; "
                    "keeping the last-good row if one exists"
                )
                continue
            except ValidationError as e:
                log.exception(
                    f"Plugin registry {r.name} has invalid schema: {e.errors()}"
                )
                continue

            if registry.schema_version != SCHEMA_VERSION:
                log.error(
                    f"Plugin registry {r.name} has an unsupported schema version."
                )
                continue

            existing = db.scalar(
                select(models.PluginRegistry).where(
                    models.PluginRegistry.name == r.name
                )
            )

            # `location`/`url` are optional in the config (a git-only registry
            # has neither), so they must stay NULL rather than the string
            # "None" that str() would produce.
            location = str(r.location) if r.location else None
            url = str(r.url) if r.url else None

            if existing:
                if existing.data != registry_data:
                    existing.data = registry_data
                    log.info(f"Updated plugin registry {r.name} from synced ref")
                # Reconciled unconditionally: a config edit that only moves the
                # registry's location/url leaves `data` byte-identical.
                existing.location = location
                existing.url = url
            else:
                db.add(
                    models.PluginRegistry(
                        name=r.name,
                        location=location,
                        url=url,
                        data=registry_data,
                    )
                )
                log.info(f"Loaded plugin registry: {r.name}")

        db.flush()

    def get_marketplace(self, db):
        # The config is the source of truth for which registries are live.
        # Reconcile only upserts, so a registry renamed or dropped from the
        # config leaves its row behind; serving it would list its plugins a
        # second time and let `install_plugin` resolve the refs of whatever
        # major line the row was last synced against.
        #
        # Filtered here rather than pruned in reconcile: the delete set would be
        # "every row not in the current view of config", and a reconcile running
        # under a narrowed or empty `registries` list would wipe the table.
        configured = [r.name for r in empire_config.plugin_marketplace.registries]
        registries = db.scalars(
            select(models.PluginRegistry).where(
                models.PluginRegistry.name.in_(configured)
            )
        ).all()
        installed_plugins = self.plugin_service.get_all(db)
        installed_plugins = {p.db_plugin.name: p.db_plugin for p in installed_plugins}
        merged = {}
        for registry in registries:
            for plugin in registry.data["plugins"]:
                # Copied, not stamped in place: annotating `plugin` would edit
                # the loaded row's own state, so anything else reading `data`
                # off this session sees a key the registry never had.
                entry = {**plugin, "registry": registry.name}
                merged.setdefault(plugin["name"], {})[registry.name] = entry

        return {
            "records": [
                {
                    "name": plugin_name,
                    "registries": plugin_registries,
                    "installed": installed_plugins.get(plugin_name) is not None,
                    "installed_version": (
                        installed_plugins.get(plugin_name).installed_version
                        if installed_plugins.get(plugin_name)
                        else None
                    ),
                }
                for plugin_name, plugin_registries in merged.items()
            ]
        }

    def install_plugin(self, db, name, version, registry):
        registry_entry, version = self._validate_install(db, name, registry, version)

        if version.get("git_url"):
            self.plugin_service.install_plugin_from_git(
                db,
                version["git_url"],
                version.get("subdirectory"),
                version.get("ref"),
                version.get("name"),
                registry_entry,
            )

        else:
            self.plugin_service.install_plugin_from_tar(
                db,
                version["tar_url"],
                version.get("subdirectory"),
                version.get("name"),
                registry_entry,
            )

    def _validate_install(self, db, name, registry, version):
        marketplace = self.get_marketplace(db)
        plugin_reference = next(
            (p for p in marketplace["records"] if p["name"] == name), None
        )

        if not plugin_reference:
            raise PluginValidationException("Plugin not found in marketplace")

        if plugin_reference["installed"]:
            raise PluginValidationException("Plugin already installed")

        plugin = plugin_reference["registries"].get(registry)
        if not plugin:
            raise PluginValidationException("Plugin not found in registry")

        version = next((v for v in plugin["versions"] if v["name"] == version), None)

        if not version:
            raise PluginValidationException("Version not found in plugin")

        return plugin, version
