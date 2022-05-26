import sys

from pyVNC import Client


def vnc_client(host: str, port: int, password: str):
    vnc = Client.Client(
        host=host,
        password=password,
        port=port,
        depth=32,
        fast=True,
        shared=True,
        gui=True,
    )
    vnc.start()


if __name__ == "__main__":
    vnc_client(host=sys.argv[1], port=int(sys.argv[2]), password=sys.argv[3])
    sys.exit(0)
