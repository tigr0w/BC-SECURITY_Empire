import fnmatch
import importlib.util
import os
from typing import Optional

from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.database import models
from empire.server.database.base import SessionLocal


class ListenerTemplateService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

        # loaded listener format:
        #     {"listenerModuleName": moduleInstance, ...}
        self._loaded_listener_templates = {}

        with SessionLocal.begin() as db:
            self._load_listener_templates(db)

    def new_instance(self, template: str):
        instance = type(self._loaded_listener_templates[template])(self.main_menu)
        for key, value in instance.options.items():
            if value.get('SuggestedValues') is None:
                value['SuggestedValues'] = []
            if value.get('Strict') is None:
                value['Strict'] = False

        return instance

    def get_listener_template(self, name: str) -> Optional[object]:  # would be nice to have a BaseListener object.
        return self._loaded_listener_templates.get(name)

    def get_listener_templates(self):
        return self._loaded_listener_templates.items()

    def _load_listener_templates(self, db: Session):
        """
        Load listeners from the install + "/listeners/*" path
        """

        root_path = f"{db.query(models.Config).first().install_path}/listeners/"
        pattern = '*.py'
        print(helpers.color("[*] v2: Loading listeners from: %s" % root_path))

        for root, dirs, files in os.walk(root_path):
            for filename in fnmatch.filter(files, pattern):
                file_path = os.path.join(root, filename)

                # don't load up any of the templates
                if fnmatch.fnmatch(filename, '*template.py'):
                    continue

                # extract just the listener module name from the full path
                listener_name = file_path.split("/listeners/")[-1][0:-3]

                # instantiate the listener module and save it to the internal cache
                spec = importlib.util.spec_from_file_location(listener_name, file_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                listener = mod.Listener(self.main_menu, [])

                for key, value in listener.options.items():
                    if value.get('SuggestedValues') is None:
                        value['SuggestedValues'] = []
                    if value.get('Strict') is None:
                        value['Strict'] = False

                self._loaded_listener_templates[slugify(listener_name)] = listener


def slugify(listener_name: str):
    return listener_name.lower().replace("/", "_")
