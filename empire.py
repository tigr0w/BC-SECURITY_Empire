#! /usr/bin/env python3
"""Shim for `python empire.py <subcommand>` from a git checkout.

The real dispatcher lives in `empire/main.py` so that an installed
distribution can reach it through the `empire-server` console script. This
file is deliberately not shipped in the wheel: once installed, `import empire`
resolves to the package and a shipped `empire.py` would be permanently
shadowed dead weight.
"""

from empire.main import main

if __name__ == "__main__":
    main()
