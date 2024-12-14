#! /usr/bin/env python3

import sys

from empire import arguments, config_manager

if __name__ == "__main__":
    args = arguments.args
    config_manager.config_init()

    if args.subparser_name == "server":
        from empire.server import server

        server.run(args)
    elif args.subparser_name == "sync-starkiller":
        import yaml

        from empire.scripts.sync_starkiller import sync_starkiller

        with open(config_manager.CONFIG_SERVER_PATH) as f:
            config = yaml.safe_load(f)

        sync_starkiller(config)
    elif args.subparser_name == "client":
        from empire.client import client

        client.start(args)

    sys.exit(0)
