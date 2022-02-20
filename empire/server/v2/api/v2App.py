import json
import os
from datetime import datetime
from json import JSONEncoder

import socketio
import uvicorn
from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from empire.server.v2.api.EmpireCORSMiddleware import EmpireCORSMiddleware
from empire.server.v2.api.websocket.v2_socketio import setup_socket_events


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

        # todo TaskingStatus not serializing
        #  Object of type User is not JSON Serializable
        return super(MyJsonEncoder, self).default(o)


def initialize():
    # Not pretty but allows us to use main_menu by delaying the import
    from empire.server.v2.api.agent import agentfilev2, agentv2, taskv2
    from empire.server.v2.api.bypass import bypassv2
    from empire.server.v2.api.credential import credentialv2
    from empire.server.v2.api.download import downloadv2
    from empire.server.v2.api.host import hostv2
    from empire.server.v2.api.keyword import keywordv2
    from empire.server.v2.api.listener import listenertemplatev2, listenerv2
    from empire.server.v2.api.meta import metav2
    from empire.server.v2.api.module import modulev2
    from empire.server.v2.api.plugin import pluginv2
    from empire.server.v2.api.profile import profilev2
    from empire.server.v2.api.stager import stagertemplatev2, stagerv2
    from empire.server.v2.api.user import userv2

    v2App = FastAPI()

    v2App.include_router(listenertemplatev2.router)
    v2App.include_router(listenerv2.router)
    v2App.include_router(stagertemplatev2.router)
    v2App.include_router(stagerv2.router)
    v2App.include_router(taskv2.router)
    v2App.include_router(agentv2.router)
    v2App.include_router(agentfilev2.router)
    v2App.include_router(userv2.router)
    v2App.include_router(modulev2.router)
    v2App.include_router(bypassv2.router)
    v2App.include_router(keywordv2.router)
    v2App.include_router(profilev2.router)
    v2App.include_router(credentialv2.router)
    v2App.include_router(hostv2.router)
    v2App.include_router(downloadv2.router)
    v2App.include_router(metav2.router)
    v2App.include_router(pluginv2.router)

    v2App.add_middleware(
        EmpireCORSMiddleware,
        allow_origins=[
            "*",
            "http://localhost",
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

    from empire.server.server import main

    setup_socket_events(sio, main)

    try:
        v2App.mount(
            "/", StaticFiles(directory="empire/server/v2/api/static"), name="static"
        )
    except Exception as e:
        pass

    cert_path = os.path.abspath("./empire/server/data/")

    # todo this gets the cert working, but ajax requests are not working, since browsers
    #  do not like self signed certs.
    # todo if the server fails to start we should exit.
    uvicorn.run(
        v2App,
        host="0.0.0.0",
        port=1337,
        # ssl_keyfile="%s/empire-priv.key" % cert_path,
        # ssl_certfile="%s/empire-chain.pem" % cert_path,
        # log_level="info",
    )
