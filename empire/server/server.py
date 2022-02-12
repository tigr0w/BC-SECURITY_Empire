#!/usr/bin/env python3
import os
import signal
import ssl
import subprocess
import sys
import time
from time import sleep

import urllib3
from flask import Flask, jsonify, make_response, request

# Empire imports
from empire.arguments import args
from empire.server.common import empire, helpers
from empire.server.common.config import empire_config
from empire.server.common.empire import MainMenu
from empire.server.database import models
from empire.server.database.base import SessionLocal
from empire.server.v2.api import v2App

# Disable http warnings
if empire_config.yaml.get("suppress-self-cert-warning", True):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def start_restful_api(empireMenu: MainMenu, suppress=False, ip="0.0.0.0", port=1337):
    app = Flask(__name__)
    main = empireMenu

    # todo vr: can we remove the global obfuscate flag and if not, how should it be handled in v2?
    @app.route("/api/admin/options", methods=["POST"])
    def set_admin_options():
        """
        Admin menu options for obfuscation
        """
        if not request.json:
            return make_response(
                jsonify({"error": "request body must be valid JSON"}), 400
            )

        # Set global obfuscation
        if "obfuscate" in request.json:
            if request.json["obfuscate"].lower() == "true":
                main.obfuscate = True
            else:
                main.obfuscate = False
            msg = f"[*] Global obfuscation set to {request.json['obfuscate']}"

        # if obfuscate command is given then set, otherwise use default
        elif "obfuscate_command" in request.json:
            main.obfuscateCommand = request.json["obfuscate_command"]
            msg = f"[*] Global obfuscation command set to {request.json['obfuscate_command']}"

        elif "preobfuscation" in request.json:
            obfuscate_command = request.json["preobfuscation"]
            if request.json["force_reobfuscation"].lower() == "true":
                force_reobfuscation = True
            else:
                force_reobfuscation = False
            msg = f"[*] Preobfuscating all modules with {obfuscate_command}"
            main.preobfuscate_modules(obfuscate_command, force_reobfuscation)
        else:
            return make_response(
                jsonify({"error": "JSON body must include key valid admin option"}), 400
            )

        print(helpers.color(msg))
        return jsonify({"success": True})

    def shutdown_server():
        """
        Shut down the Flask server and any Empire instance gracefully.
        """
        global serverExitCommand

        print(helpers.color("[*] Shutting down Empire RESTful API"))

        if suppress:
            print(helpers.color("[*] Shutting down the Empire instance"))
            main.shutdown()

        serverExitCommand = "shutdown"

        func = request.environ.get("werkzeug.server.shutdown")
        if func is not None:
            func()

    def signal_handler(signal, frame):
        """
        Overrides the keyboardinterrupt signal handler so we can gracefully shut everything down.
        """

        global serverExitCommand

        with app.test_request_context():
            shutdown_server()

        serverExitCommand = "shutdown"

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
    context.load_cert_chain(
        "%s/empire-chain.pem" % cert_path, "%s/empire-priv.key" % cert_path
    )
    app.run(host=ip, port=int(port), ssl_context=context, threaded=True)

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
    print(helpers.color("[*] Cleaning up test user"))
    user = (
        SessionLocal()
        .query(models.User)
        .filter(models.User.username == username)
        .first()
    )
    SessionLocal().delete(user)
    SessionLocal().commit()


main = empire.MainMenu(args=args)


def run(args):
    if not args.restport:
        args.restport = "1337"
    else:
        args.restport = args.restport[0]

    if not args.restip:
        args.restip = "0.0.0.0"
    else:
        args.restip = args.restip[0]

    if args.version:
        print(empire.VERSION)

    elif args.reset:
        # Reset called from database/base.py
        sys.exit()

    else:
        if not os.path.exists("./empire/server/data/empire-chain.pem"):
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
