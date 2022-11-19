#! /usr/bin/env python3

import sys

import empire.arguments as arguments

if __name__ == "__main__":
    args = arguments.args

    if args.subparser_name == "server":
        import empire.server.server as server

        server.run(args)
    elif args.subparser_name == "sync-starkiller":
        import yaml

        from empire.scripts.sync_starkiller import sync_starkiller

        with open("empire/server/config.yaml") as f:
            config = yaml.safe_load(f)

        sync_starkiller(config)
    elif args.subparser_name == "client":
        import empire.client.client as client

        client.start(args)

    sys.exit(0)
