"""Covers the AFTER_CHAT_MESSAGE_HOOK core hook and the persist_and_fire_chat
helper the chat Socket.IO handler was refactored onto.

The hook fires with an expunged (detached but fully-populated) ChatMessage so
a registered callback can read its attributes without a DetachedInstanceError,
even though the session commits with expire_on_commit=True.
"""

from empire.server.api.v2.websocket.socketio import persist_and_fire_chat
from empire.server.core.hooks import hooks


def test_after_chat_message_hook_fires_with_usable_message(
    client, admin_auth_header, session_local, models
):
    received = {}

    def _cb(db, message):
        # message must be usable (not expired/detached) here
        received["username"] = message.username
        received["message"] = message.message

    hooks.register_hook(hooks.AFTER_CHAT_MESSAGE_HOOK, "test_chat_hook_cb", _cb)
    try:
        with session_local() as db:
            persist_and_fire_chat(db, user_id=1, username="alice", text="hello ai")
        assert received == {"username": "alice", "message": "hello ai"}
    finally:
        hooks.unregister_hook("test_chat_hook_cb")
