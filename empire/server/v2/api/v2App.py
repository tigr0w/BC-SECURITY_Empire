import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates


def initialize():
    # Not pretty but allows us to use main_menu by delaying the import
    from empire.server.v2.api.agent import agentv2
    from empire.server.v2.api.agent import taskv2
    from empire.server.v2.api.agent import agentfilev2
    from empire.server.v2.api.stager import stagertemplatev2
    from empire.server.v2.api.stager import stagerv2
    from empire.server.v2.api.listener import listenertemplatev2
    from empire.server.v2.api.listener import listenerv2
    from empire.server.v2.api.user import userv2
    from empire.server.v2.api.module import modulev2
    from empire.server.v2.api.bypass import bypassv2
    from empire.server.v2.api.keyword import keywordv2
    from empire.server.v2.api.profile import profilev2
    from empire.server.v2.api.credential import credentialv2
    from empire.server.v2.api.host import hostv2
    from empire.server.v2.api.download import downloadv2
    from empire.server.v2.api.meta import metav2
    from empire.server.v2.api.plugin import pluginv2

    from empire.server.v2.api.websocket import v2_socket

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
    v2App.include_router(v2_socket.router) # todo naming convention

    v2App.add_middleware(
        CORSMiddleware,
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
    #
    v2App.add_middleware(GZipMiddleware, minimum_size=500)

    # todo this kind of works for serving starkiller.
    #  need to get html5 router working and make it so access is not only via
    #  /index.html.
    # https://stackoverflow.com/questions/64522736/how-to-connect-vue-js-as-frontend-and-fastapi-as-backend
    # https://stackoverflow.com/questions/62928450/how-to-put-backend-and-frontend-together-returning-react-frontend-from-fastapi
    v2App.mount("/", StaticFiles(directory="empire/server/v2/api/static"), name="static")

    @v2App.get("/ws-tester")
    async def ws_tester():
        return HTMLResponse("""
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <h2>Your ID: <span id="ws-id"></span></h2>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var client_id = Date.now()
            document.querySelector("#ws-id").textContent = client_id;
            var ws = new WebSocket(`ws://localhost:8000/ws/${client_id}`);
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
""")


    uvicorn.run(v2App, host="0.0.0.0", port=8000)
