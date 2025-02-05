#! /usr/bin/env python3

import sys

from empire import arguments
from empire.server.core.config import config_manager

if __name__ == "__main__":
    args = arguments.args

    if args.subparser_name == "server":
        from empire.server import server

        server.run(args)
    elif args.subparser_name == "sync-starkiller":
        import yaml

        from empire.scripts.sync_starkiller import sync_starkiller

        with open(config_manager.CONFIG_PATH) as f:
            config = yaml.safe_load(f)

        sync_starkiller(config)

    elif args.subparser_name == "sync-empire-compiler":
        import yaml

        from empire.scripts.sync_empire_compiler import load_empire_compiler

        with open(config_manager.CONFIG_PATH) as f:
            config = yaml.safe_load(f)

        load_empire_compiler(config)

    sys.exit(0)
