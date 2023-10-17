import logging
import sys
from typing import Dict

import yaml

log = logging.getLogger(__name__)


class EmpireCliConfig:
    def __init__(self):
        self.yaml: Dict = {}
        if "--config" in sys.argv:
            location = sys.argv[sys.argv.index("--config") + 1]
            log.info(f"Loading config from {location}")
            self.set_yaml(location)
        if len(self.yaml.items()) == 0:
            log.info("Loading default config")
            self.set_yaml("./empire/client/config.yaml")

    def set_yaml(self, location: str):
        try:
            with open(location) as stream:
                self.yaml = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            log.error(exc)
        except FileNotFoundError as exc:
            log.error(exc)


empire_config = EmpireCliConfig()
