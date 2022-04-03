import json

from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.common.hooks import hooks
from empire.server.database import models
from empire.server.database.base import SessionLocal
from empire.server.v2.api import jwt_auth
from empire.server.v2.api.agent.agent_dto import domain_to_dto_agent
from empire.server.v2.api.agent.task_dto import domain_to_dto_task
from empire.server.v2.api.listener.listener_dto import domain_to_dto_listener
from empire.server.v2.api.user.user_dto import domain_to_dto_user


def setup_socket_events(sio, empire_menu):
    empire_menu.socketio = sio
    # A socketio user is in the general channel if they join the chat.
    room = "general"

    chat_participants = {}

    # This is really just meant to provide some context to a user that joins the convo.
    # In the future we can expand to store chat messages in the db if people want to retain a whole chat log.
    chat_log = []

    sid_to_user = {}

    async def get_user_from_token(sid, token):
        user = await jwt_auth.get_current_user(token, SessionLocal())
        if user is None:
            return False
        sid_to_user[sid] = user.id

        return user

    def get_user_from_sid(sid):
        user_id = sid_to_user.get(sid)
        if user_id is None:
            return None

        return (
            SessionLocal().query(models.User).filter(models.User.id == user_id).first()
        )

    @sio.on("connect")
    async def on_connect(sid, environ, auth):
        user = await get_user_from_token(sid, auth["token"])
        if user:
            print(helpers.color(f"[+] {user.username} connected to socketio"))
            return

        return False

    @sio.on("disconnect")
    async def on_disconnect(sid):
        user = get_user_from_sid(sid)
        print(
            helpers.color(
                f"[+] {'Client' if user is None else user.username} disconnected from socketio"
            )
        )

    @sio.on("chat/join")
    async def on_join(sid, data=None):
        """
        The calling user gets added to the "general"  chat room.
        Note: while 'data' is unused, it is good to leave it as a parameter for compatibility reasons.
        The server fails if a client sends data when none is expected.
        :return: emits a join event with the user's details.
        """
        user = get_user_from_sid(sid)
        if user.username not in chat_participants:
            chat_participants[user.username] = user.username
        sio.enter_room(sid, room)
        await sio.emit(
            "chat/join",
            {
                "user": domain_to_dto_user(user),
                "username": user.username,
                "message": f"{user.username} has entered the room.",
            },
            room=room,
        )

    @sio.on("chat/leave")
    async def on_leave(sid, data=None):
        """
        The calling user gets removed from the "general" chat room.
        :return: emits a leave event with the user's details.
        """
        user = get_user_from_sid(sid)
        if user is not None:
            chat_participants.pop(user.username, None)
            sio.leave_room(sid, room)
            await sio.emit(
                "chat/leave",
                {
                    "user": domain_to_dto_user(user),
                    "username": user.username,
                    "message": user.username + " has left the room.",
                },
                room=room,
            )

    @sio.on("chat/message")
    async def on_message(sid, data):
        """
        The calling user sends a message.
        :param data: contains the user's message.
        :return: Emits a message event containing the message and the user's username
        """
        user = get_user_from_sid(sid)
        if isinstance(data, str):
            data = json.loads(data)
        chat_log.append({"username": user.username, "message": data["message"]})
        await sio.emit(
            "chat/message",
            {"username": user.username, "message": data["message"]},
            room=room,
        )

    @sio.on("chat/history")
    async def on_history(sid, data=None):
        """
        The calling user gets sent the last 20 messages.
        :return: Emit chat messages to the calling user.
        """
        for x in range(len(chat_log[-20:])):
            username = chat_log[x]["username"]
            message = chat_log[x]["message"]
            await sio.emit(
                "chat/message",
                {"username": username, "message": message, "history": True},
                room=sid,
            )

    @sio.on("chat/participants")
    async def on_participants(sid, data=None):
        """
        The calling user gets sent a list of "general" chat participants.
        :return: emit participant event containing list of users.
        """
        await sio.emit("chat/participants", list(chat_participants.values()), room=sid)

    async def agent_socket_hook(db: Session, agent: models.Agent):
        await sio.emit("agents/new", domain_to_dto_agent(agent).dict())

    async def task_socket_hook(db: Session, task: models.Tasking):
        if "function Get-Keystrokes" not in task.input:
            await sio.emit(
                f"agents/{task.agent_id}/task", domain_to_dto_task(task).dict()
            )

    async def listener_socket_hook(db: Session, listener: models.Listener):
        await sio.emit("listeners/new", domain_to_dto_listener(listener).dict())

    hooks.register_hook(
        hooks.AFTER_AGENT_CHECKIN_HOOK, "agent_socket_hook", agent_socket_hook
    )
    hooks.register_hook(
        hooks.AFTER_TASKING_RESULT_HOOK, "task_socket_hook", task_socket_hook
    )
    hooks.register_hook(
        hooks.AFTER_LISTENER_CREATED_HOOK, "listener_socket_hook", listener_socket_hook
    )
