import argparse

parent_parser = argparse.ArgumentParser()
subparsers = parent_parser.add_subparsers(dest="subparser_name")

server_parser = subparsers.add_parser("server", help="Launch Empire Server")
client_parser = subparsers.add_parser("client", help="Launch Empire CLI")
sync_starkiller_parser = subparsers.add_parser(
    "sync-starkiller", help="Sync Starkiller submodule with the config"
)

# Client Args
client_parser.add_argument(
    "-l",
    "--log-level",
    dest="log_level",
    type=str.upper,
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    help="Set the logging level",
)
client_parser.add_argument(
    "-r",
    "--resource",
    type=str,
    help="Run the Empire commands in the specified resource file after startup.",
)
client_parser.add_argument(
    "--config",
    type=str,
    nargs=1,
    help="Specify a config.yaml different from the config.yaml in the empire/client directory.",
)
client_parser.add_argument(
    "--reset",
    action="store_true",
    help="Resets Empire's client to defaults and deletes any app data accumulated over previous runs.",
)

# Server Args
general_group = server_parser.add_argument_group("General Options")
general_group.add_argument(
    "-l",
    "--log-level",
    dest="log_level",
    type=str.upper,
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    help="Set the logging level",
)
general_group.add_argument(
    "-d",
    "--debug",
    help="Set the logging level to DEBUG",
    action="store_const",
    dest="log_level",
    const="DEBUG",
    default=None,
)
general_group.add_argument(
    "--reset",
    action="store_true",
    help="Resets Empire's database and deletes any app data accumulated over previous runs.",
)
general_group.add_argument(
    "-v", "--version", action="store_true", help="Display current Empire version."
)
general_group.add_argument(
    "--config",
    type=str,
    nargs=1,
    help="Specify a config.yaml different from the config.yaml in the empire/server directory.",
)

args = parent_parser.parse_args()

if parent_parser.parse_args().subparser_name is None:
    parent_parser.print_help()
