import base64
import logging
import queue
from socket import socket

from secretsocks import secretsocks

log = logging.getLogger(__name__)


def start_client(agent_task_service, q, session_id, port):
    log.info("Creating SOCKS client...")
    client = EmpireSocksClient(agent_task_service, q, session_id)

    # Start the standard listener with our client
    log.info("Starting SOCKS server...")
    listener = secretsocks.Listener(client, host="127.0.0.1", port=port)
    listener.wait()


class EmpireSocksClient(secretsocks.Client):
    # Initialize our data channel
    def __init__(self, agent_task_service, q, session_id):
        secretsocks.Client.__init__(self)
        self.q = q
        self.agent_task_service = agent_task_service
        self.session_id = session_id
        self.alive = True
        self.start()

    # Receive data from our data channel and push it to the receive queue
    def recv(self):
        while self.alive:
            try:
                data = self.q.get()
                self.recvbuf.put(data)
            except socket.timeout:
                continue
            except:
                self.alive = False

    # Take data from the write queue and send it over our data channel
    def write(self):
        while self.alive:
            try:
                data = self.writebuf.get(timeout=10)
                if data:
                    self.agent_task_service.create_task_socks_data(
                        self.session_id,
                        base64.b64encode(data).decode("UTF-8"),
                    )
            except queue.Empty:
                continue
