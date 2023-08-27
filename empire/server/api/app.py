import json
import logging
import os
from datetime import datetime
from json import JSONEncoder
from pathlib import Path

import socketio
import uvicorn
from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from empire.scripts.sync_starkiller import sync_starkiller
from empire.server.api.middleware import EmpireCORSMiddleware
from empire.server.api.v2.websocket.socketio import setup_socket_events
from empire.server.core.config import empire_config

log = logging.getLogger(__name__)


class MyJsonWrapper(object):
    @staticmethod
    def dumps(*args, **kwargs):
        if "cls" not in kwargs:
            kwargs["cls"] = MyJsonEncoder
        return json.dumps(*args, **kwargs)

    @staticmethod
    def loads(*args, **kwargs):
        return json.loads(*args, **kwargs)


class MyJsonEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.decode("latin-1")
        if hasattr(o, "json") and callable(o.json):
            return o.json()

        return JSONEncoder.default(self, o)


def load_starkiller(v2App, ip, port):
    try:
        sync_starkiller(empire_config.dict())
    except Exception as e:
        log.warning("Failed to load Starkiller: %s", e, exc_info=True)
        log.warning(
            "If you are trying to pull Starkiller from a private repository ("
            "such as Starkiller-Sponsors), make sure you have the proper ssh "
            "credentials set in your Empire config. See "
            "https://docs.github.com/en/github/authenticating-to-github"
            "/connecting-to-github-with-ssh"
        )

    if (Path(empire_config.starkiller.directory) / "dist").exists():
        v2App.mount(
            "/",
            StaticFiles(directory=f"{empire_config.starkiller.directory}/dist"),
            name="static",
        )
        log.info("Starkiller served at the same ip and port as Empire Server")
        log.info(f"Starkiller served at http://localhost:{port}/index.html")


def initialize(secure: bool = False, ip: str = "0.0.0.0", port: int = 1337):
    # Not pretty but allows us to use main_menu by delaying the import
    from empire.server.api.v2.agent import agent_api, agent_file_api, agent_task_api
    from empire.server.api.v2.bypass import bypass_api
    from empire.server.api.v2.credential import credential_api
    from empire.server.api.v2.download import download_api
    from empire.server.api.v2.host import host_api, process_api
    from empire.server.api.v2.listener import listener_api, listener_template_api
    from empire.server.api.v2.meta import meta_api
    from empire.server.api.v2.module import module_api
    from empire.server.api.v2.obfuscation import obfuscation_api
    from empire.server.api.v2.plugin import plugin_api, plugin_task_api
    from empire.server.api.v2.profile import profile_api
    from empire.server.api.v2.stager import stager_api, stager_template_api
    from empire.server.api.v2.tag import tag_api
    from empire.server.api.v2.user import user_api
    from empire.server.server import main

    v2App = FastAPI()

    @v2App.on_event("shutdown")
    def shutdown_event():
        log.info("Shutting down Empire Server...")
        if main:
            log.info("Shutting down MainMenu...")
            main.shutdown()

    v2App.include_router(listener_template_api.router)
    v2App.include_router(listener_api.router)
    v2App.include_router(stager_template_api.router)
    v2App.include_router(stager_api.router)
    v2App.include_router(agent_task_api.router)
    v2App.include_router(agent_api.router)
    v2App.include_router(agent_file_api.router)
    v2App.include_router(user_api.router)
    v2App.include_router(module_api.router)
    v2App.include_router(bypass_api.router)
    v2App.include_router(obfuscation_api.router)
    v2App.include_router(process_api.router)
    v2App.include_router(profile_api.router)
    v2App.include_router(credential_api.router)
    v2App.include_router(host_api.router)
    v2App.include_router(download_api.router)
    v2App.include_router(meta_api.router)
    v2App.include_router(plugin_task_api.router)
    v2App.include_router(plugin_api.router)
    v2App.include_router(tag_api.router)

    v2App.add_middleware(
        EmpireCORSMiddleware,
        allow_origins=[
            "*",
            "http://localhost",
            "http://localhost:8080",
            "http://localhost:8081",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["content-disposition"],
    )

    v2App.add_middleware(GZipMiddleware, minimum_size=500)

    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        # logger=True,
        # engineio_logger=True,
        # https://github.com/miguelgrinberg/flask-socketio/issues/274#issuecomment-231206374
        json=MyJsonWrapper,
    )
    sio_app = socketio.ASGIApp(
        socketio_server=sio, other_asgi_app=v2App, socketio_path="/socket.io/"
    )

    v2App.add_route("/socket.io/", route=sio_app, methods=["GET", "POST"])
    v2App.add_websocket_route("/socket.io/", sio_app)

    setup_socket_events(sio, main)

    load_starkiller(v2App, ip, port)

    cert_path = os.path.abspath("./empire/server/data/")

    if not secure:
        uvicorn.run(
            v2App,
            host=ip,
            port=port,
            log_config=None,
            lifespan="on",
            # log_level="info",
        )
    else:
        uvicorn.run(
            v2App,
            host=ip,
            port=port,
            log_config=None,
            lifespan="on",
            ssl_keyfile=f"{cert_path}/empire-priv.key",
            ssl_certfile=f"{cert_path}/empire-chain.pem",
            # log_level="info",
        )
