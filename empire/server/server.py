#!/usr/bin/env python3
import logging
import os
import signal
import ssl
import subprocess
import sys
import time
from time import sleep

import flask
import urllib3
from flask import Flask, request, jsonify, make_response

# Empire imports
from empire.arguments import args
from empire.server.common import empire, helpers
from empire.server.common.empire import MainMenu
from empire.server.database import models
from empire.server.database.base import SessionLocal
from empire.server.v2.api import v2App
from empire.server.common.config import empire_config

# Check if running Python 3
if sys.version[0] == '2':
    print(helpers.color("[!] Please use Python 3"))
    sys.exit()

# Disable http warnings
if empire_config.yaml.get('suppress-self-cert-warning', True):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def start_restful_api(empireMenu: MainMenu,
                      suppress=False,
                      ip='0.0.0.0',
                      port=1337):
    app = Flask(__name__)
    main = empireMenu

    # todo vr: can we remove the global obfuscate flag and if not, how should it be handled in v2?
    @app.route('/api/admin/options', methods=['POST'])
    def set_admin_options():
        """
        Admin menu options for obfuscation
        """
        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        # Set global obfuscation
        if 'obfuscate' in request.json:
            if request.json['obfuscate'].lower() == 'true':
                main.obfuscate = True
            else:
                main.obfuscate = False
            msg = f"[*] Global obfuscation set to {request.json['obfuscate']}"

        # if obfuscate command is given then set, otherwise use default
        elif 'obfuscate_command' in request.json:
            main.obfuscateCommand = request.json['obfuscate_command']
            msg = f"[*] Global obfuscation command set to {request.json['obfuscate_command']}"

        elif 'preobfuscation' in request.json:
            obfuscate_command = request.json['preobfuscation']
            if request.json['force_reobfuscation'].lower() == 'true':
                force_reobfuscation = True
            else:
                force_reobfuscation = False
            msg = f"[*] Preobfuscating all modules with {obfuscate_command}"
            main.preobfuscate_modules(obfuscate_command, force_reobfuscation)
        else:
            return make_response(jsonify({'error': 'JSON body must include key valid admin option'}), 400)

        print(helpers.color(msg))
        return jsonify({'success': True})

    def shutdown_server():
        """
        Shut down the Flask server and any Empire instance gracefully.
        """
        global serverExitCommand

        print(helpers.color("[*] Shutting down Empire RESTful API"))

        if suppress:
            print(helpers.color("[*] Shutting down the Empire instance"))
            main.shutdown()

        serverExitCommand = 'shutdown'

        func = request.environ.get('werkzeug.server.shutdown')
        if func is not None:
            func()

    def signal_handler(signal, frame):
        """
        Overrides the keyboardinterrupt signal handler so we can gracefully shut everything down.
        """

        global serverExitCommand

        with app.test_request_context():
            shutdown_server()

        serverExitCommand = 'shutdown'

        # repair the original signal handler
        import signal
        signal.signal(signal.SIGINT, signal.default_int_handler)
        sys.exit()

    try:
        signal.signal(signal.SIGINT, signal_handler)
    except ValueError:
        pass

    # wrap the Flask connection in SSL and start it
    cert_path = os.path.abspath("./empire/server/data/")

    proto = ssl.PROTOCOL_TLS
    context = ssl.SSLContext(proto)
    context.load_cert_chain("%s/empire-chain.pem" % cert_path, "%s/empire-priv.key" % cert_path)
    app.run(host=ip, port=int(port), ssl_context=context, threaded=True)


def start_sockets(empire_menu: MainMenu, ip='0.0.0.0', port: int = 5000, suppress: bool = False):
    app = Flask(__name__)
    app.json_encoder = MyJsonEncoder
    socketio = SocketIO(app, cors_allowed_origins="*", json=flask.json, async_mode="threading")

    empire_menu.socketio = socketio
    room = 'general'  # A socketio user is in the general channel if the join the chat.
    chat_participants = {}
    chat_log = []  # This is really just meant to provide some context to a user that joins the convo.

    # In the future we can expand to store chat messages in the db if people want to retain a whole chat log.

    if suppress:
        # suppress the normal Flask output
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    def get_user_from_token():
        # user = empire_menu.users.get_user_from_token(request.args.get('token', ''))
        if user:
            user['password'] = ''
            user['api_token'] = ''

        return user

    @socketio.on('connect')
    def connect():
        user = get_user_from_token()
        if user:
            print(helpers.color(f"[+] {user['username']} connected to socketio"))
            return

        return False

    @socketio.on('disconnect')
    def test_disconnect():
        user = get_user_from_token()
        print(helpers.color(f"[+] {'Client' if user is None else user['username']} disconnected from socketio"))

    @socketio.on('chat/join')
    def on_join(data=None):
        """
        The calling user gets added to the "general"  chat room.
        Note: while 'data' is unused, it is good to leave it as a parameter for compatibility reasons.
        The server fails if a client sends data when none is expected.
        :return: emits a join event with the user's details.
        """
        user = get_user_from_token()
        if user['username'] not in chat_participants:
            chat_participants[user['username']] = user
        join_room(room)
        socketio.emit("chat/join", {'user': user,
                                    'username': user['username'],
                                    'message': f"{user['username']} has entered the room."}, room=room)

    @socketio.on('chat/leave')
    def on_leave(data=None):
        """
        The calling user gets removed from the "general" chat room.
        :return: emits a leave event with the user's details.
        """
        user = get_user_from_token()
        if user is not None:
            chat_participants.pop(user['username'], None)
            leave_room(room)
            socketio.emit("chat/leave", {'user': user,
                                         'username': user['username'],
                                         'message': user['username'] + ' has left the room.'}, to=room)

    @socketio.on('chat/message')
    def on_message(data):
        """
        The calling user sends a message.
        :param data: contains the user's message.
        :return: Emits a message event containing the message and the user's username
        """
        user = get_user_from_token()
        chat_log.append({'username': user['username'], 'message': data['message']})
        socketio.emit("chat/message", {'username': user['username'], 'message': data['message']}, to=room)

    @socketio.on('chat/history')
    def on_history(data=None):
        """
        The calling user gets sent the last 20 messages.
        :return: Emit chat messages to the calling user.
        """
        sid = request.sid
        for x in range(len(chat_log[-20:])):
            username = chat_log[x]['username']
            message = chat_log[x]['message']
            socketio.emit("chat/message", {'username': username, 'message': message, 'history': True}, to=sid)

    @socketio.on('chat/participants')
    def on_participants(data=None):
        """
        The calling user gets sent a list of "general" chat participants.
        :return: emit participant event containing list of users.
        """
        sid = request.sid
        socketio.emit("chat/participants", list(chat_participants.values()), to=sid)

    print(helpers.color("[*] Starting Empire SocketIO on %s:%s" % (ip, port)))

    cert_path = os.path.abspath("./empire/server/data/")
    proto = ssl.PROTOCOL_TLS
    context = ssl.SSLContext(proto)
    context.load_cert_chain("{}/empire-chain.pem".format(cert_path), "{}/empire-priv.key".format(cert_path))
    socketio.run(app, host=ip, port=port, ssl_context=context)

    # def server_startup_validator():
    #     print(helpers.color('[*] Testing APIs'))
    #     rng = random.SystemRandom()
    #     username = 'test-' + ''.join(rng.choice(string.ascii_lowercase) for i in range(4))
    #     password = ''.join(rng.choice(string.ascii_lowercase) for i in range(10))
    #     main.users.add_new_user(username, password)
    #     response = requests.post(url=f'https://{args.restip}:{args.restport}/api/admin/login',
    #                              json={'username': username, 'password': password},
    #                              verify=False)
    #     if response:
    #         print(helpers.color('[+] Empire RESTful API successfully started'))
    #
    #         try:
    #             sio = socketio.Client(ssl_verify=False)
    #             sio.connect(f'wss://{args.restip}:{args.socketport}?token={response.json()["token"]}')
    #             print(helpers.color('[+] Empire SocketIO successfully started'))
    #         except Exception as e:
    #             print(e)
    #             print(helpers.color('[!] Empire SocketIO failed to start'))
    #             sys.exit()
    #         finally:
    #             cleanup_test_user(username)
    #             sio.disconnect()
    #
    #     else:
    #         print(helpers.color('[!] Empire RESTful API failed to start'))
    #         cleanup_test_user(password)
    #         sys.exit()

def cleanup_test_user(username: str):
    print(helpers.color('[*] Cleaning up test user'))
    user = SessionLocal().query(models.User).filter(models.User.username == username).first()
    SessionLocal().delete(user)
    SessionLocal().commit()


main = empire.MainMenu(args=args)


def run(args):
    if not args.restport:
        args.restport = '1337'
    else:
        args.restport = args.restport[0]

    if not args.restip:
        args.restip = '0.0.0.0'
    else:
        args.restip = args.restip[0]

    if not args.socketport:
        args.socketport = '5000'
    else:
        args.socketport = args.socketport[0]

    if args.version:
        print(empire.VERSION)

    elif args.reset:
        # Reset called from database/base.py
        sys.exit()

    else:
        if not os.path.exists('./empire/server/data/empire-chain.pem'):
            print(helpers.color("[*] Certificate not found. Generating..."))
            subprocess.call("./setup/cert.sh")
            time.sleep(3)

        # start an Empire instance and RESTful API with the teamserver interface

        def thread_v2_api():
            v2App.initialize()

        # thread_v2_api()

        thread3 = helpers.KThread(target=thread_v2_api)
        thread3.daemon = True
        thread3.start()
        sleep(2)

        # server_startup_validator()
        main.teamserver()

    sys.exit()
