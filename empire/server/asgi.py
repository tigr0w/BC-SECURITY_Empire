"""
Standard ASGI entrypoint for Empire Server.

Run with:
  - uvicorn empire.server.asgi:app
  - fastapi dev empire.server.asgi:app
"""

from empire.server.api.app import create_app

app = create_app()
