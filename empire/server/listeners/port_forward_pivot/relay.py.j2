import socket
import threading

LISTEN_HOST = "{{ listen_host }}"
LISTEN_PORT = {{ listen_port }}
CONNECT_HOST = "{{ connect_host }}"
CONNECT_PORT = {{ connect_port }}


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass


def _handle(client):
    upstream = None
    try:
        upstream = socket.create_connection((CONNECT_HOST, CONNECT_PORT))
    except OSError as e:
        print(
            f"[port_forward_pivot] upstream {CONNECT_HOST}:{CONNECT_PORT} unreachable: {e}",
            flush=True,
        )
        client.close()
        return
    try:
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
        _pipe(upstream, client)
    finally:
        client.close()
        upstream.close()


try:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(50)
except OSError as e:
    print(
        f"[port_forward_pivot] LISTEN_FAIL {LISTEN_HOST}:{LISTEN_PORT}: {e}",
        flush=True,
    )
    raise SystemExit(1) from e
print(f"[port_forward_pivot] LISTEN_OK {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
while True:
    client, _ = server.accept()
    threading.Thread(target=_handle, args=(client,), daemon=True).start()
