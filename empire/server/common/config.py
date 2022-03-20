import logging
import sys
from typing import Dict

import yaml

log = logging.getLogger(__name__)


class EmpireConfig(object):
    def __init__(self):
        self.yaml: Dict = {}
        if "--config" in sys.argv:
            location = sys.argv[sys.argv.index("--config") + 1]
            log.info(f"Loading config from {location}")
            self.set_yaml(location)
        if len(self.yaml.items()) == 0:
            default_location = "./empire/server/config.yaml"
            log.info(f"Loading default config from {default_location}")
            self.set_yaml(default_location)

    def set_yaml(self, location: str):
        try:
            with open(location, "r") as stream:
                self.yaml = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            log.error(exc)
        except FileNotFoundError as exc:
            log.error(exc)


empire_config = EmpireConfig()
