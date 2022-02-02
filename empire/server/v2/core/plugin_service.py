import fnmatch
import importlib
import os
import pkgutil
from importlib.machinery import SourceFileLoader

from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.common.config import empire_config
from empire.server.database import models
from empire.server.database.base import SessionLocal


class PluginService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu
        self.loaded_plugins = {}
        with SessionLocal.begin() as db:
            self.startup_plugins(db)
            self.autostart_plugins()

    def autostart_plugins(self):
        """
        Autorun plugin commands at server startup.
        """
        plugins = empire_config.yaml.get('plugins')
        if plugins:
            for plugin in plugins:
                use_plugin = self.loaded_plugins[plugin]
                for option in plugins[plugin]:
                    value = plugins[plugin][option]
                    use_plugin.options[option]['Value'] = value
                results = use_plugin.execute('')
                if results is False:
                    print(helpers.color(f'[!] Plugin failed to run: {plugin}'))
                else:
                    print(helpers.color(f'[+] Plugin {plugin} ran successfully!'))

    def startup_plugins(self, db: Session):
        """
        Load plugins at the start of Empire
        """
        plugin_path = db.query(models.Config).first().install_path + "/plugins"
        print(helpers.color("[*] Searching for plugins at {}".format(plugin_path)))

        # Import old v1 plugins (remove in 5.0)
        plugin_names = [name for _, name, _ in pkgutil.walk_packages([plugin_path])]
        for plugin_name in plugin_names:
            if plugin_name.lower() != 'example':
                file_path = os.path.join(plugin_path, plugin_name + '.py')
                self.load_plugin(plugin_name, file_path)

        for root, dirs, files in os.walk(plugin_path):
            for filename in files:
                if not filename.lower().endswith('.plugin'):
                    continue

                file_path = os.path.join(root, filename)
                plugin_name = filename.split('.')[0]

                # don't load up any of the templates or examples
                if fnmatch.fnmatch(filename, '*template.plugin'):
                    continue
                elif fnmatch.fnmatch(filename, '*example.plugin'):
                    continue

                self.load_plugin(plugin_name, file_path)

    def load_plugin(self, plugin_name, file_path):
        """ Given the name of a plugin and a menu object, load it into the menu """
        # note the 'plugins' package so the loader can find our plugin
        loader = importlib.machinery.SourceFileLoader(plugin_name, file_path)
        module = loader.load_module()
        plugin_obj = module.Plugin(self.main_menu)

        for key, value in plugin_obj.options.items():
            if value.get('SuggestedValues') is None:
                value['SuggestedValues'] = []
            if value.get('Strict') is None:
                value['Strict'] = False

        self.loaded_plugins[plugin_name] = plugin_obj

    def get_all(self):
        return self.loaded_plugins

    def get_by_id(self, uid: str):
        return self.loaded_plugins[uid]

    def shutdown(self):
        for plugin in self.loaded_plugins:
            plugin.shutdown()
