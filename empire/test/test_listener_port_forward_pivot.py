import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from empire.server.core.db import models


@pytest.fixture
def main_menu_mock():
    main_menu = Mock()
    main_menu.installPath = ""
    main_menu.install_path = Path()
    main_menu.listeners.activeListeners = {}
    main_menu.listeners.listeners = {}
    return main_menu


@pytest.fixture
def listener(monkeypatch, main_menu_mock):
    from empire.server.listeners.http import Listener as HttpListener
    from empire.server.listeners.port_forward_pivot import Listener

    packets = Mock()
    packets.build_routing_packet.return_value = b"routing packet"
    monkeypatch.setattr("empire.server.listeners.port_forward_pivot.packets", packets)

    secrets_mock = MagicMock()
    secrets_mock.choice.side_effect = lambda x: x[0]
    monkeypatch.setattr(
        "empire.server.listeners.port_forward_pivot.secrets", secrets_mock
    )

    pivot = Listener(main_menu_mock)
    pivot.options.update(HttpListener(main_menu_mock).options)
    pivot.options["Host"] = {"Value": "http://localhost"}
    pivot.options["Port"] = {"Value": "80"}
    pivot.host_address = "http://localhost/"

    main_menu_mock.listeners.activeListeners = {
        "fake_listener": {"options": pivot.options}
    }
    pivot.threads = {"fake_listener": {"fake_thread": {}}}
    return pivot


def test_generate_launcher_go(listener, main_menu_mock):
    go_compile_mock = MagicMock(return_value="/tmp/gopire-pivot.exe")
    main_menu_mock.stagergenv2.generate_go_stageless = go_compile_mock

    result = listener.generate_launcher(
        listener_name="fake_listener", language="go", encode=False
    )

    assert result == "/tmp/gopire-pivot.exe"
    go_compile_mock.assert_called_once()
    _, kwargs = go_compile_mock.call_args
    assert kwargs["listener_name"] == "fake_listener"


def test_generate_launcher_csharp(listener, main_menu_mock):
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"
    compile_mock = MagicMock(return_value="/tmp/sharpire-pivot.exe")
    main_menu_mock.dotnet_compiler.compile_stager = compile_mock

    result = listener.generate_launcher(
        listener_name="fake_listener", language="csharp", encode=False
    )

    assert result == "/tmp/sharpire-pivot.exe"
    compile_mock.assert_called_once()
    assert compile_mock.call_args[0][1] == "Sharpire"


def test_generate_launcher_unknown_language_returns_none(listener):
    assert (
        listener.generate_launcher(listener_name="fake_listener", language="elixir")
        is None
    )


@pytest.mark.parametrize("language", ["csharp", "go"])
def test_generate_stager_stageless(listener, language):
    assert listener.generate_stager(listener.options, language=language) == ""


@pytest.mark.parametrize("language", ["csharp", "go"])
def test_generate_agent_stageless(listener, language):
    assert listener.generate_agent(listener.options, language=language) == ""


@pytest.mark.parametrize("language", ["csharp", "go"])
def test_generate_comms_stageless(listener, language):
    assert listener.generate_comms(listener.options, language=language) == ""


def test_generate_stager_unknown_language_returns_none(listener):
    assert listener.generate_stager(listener.options, language="elixir") is None


def test_generate_agent_unknown_language_returns_none(listener):
    assert listener.generate_agent(listener.options, language="elixir") is None


def test_generate_comms_unknown_language_returns_none(listener):
    assert listener.generate_comms(listener.options, language="elixir") is None


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("http://1.2.3.4", "80", ("1.2.3.4", 80)),
        ("https://example.com", "443", ("example.com", 443)),
        ("https://example.com:8443", "443", ("example.com", 8443)),
        ("1.2.3.4", "5555", ("1.2.3.4", 5555)),
        ("1.2.3.4:9999", "80", ("1.2.3.4", 9999)),
    ],
)
def test_split_connect_target(host, port, expected):
    from empire.server.listeners.port_forward_pivot import _split_connect_target

    assert _split_connect_target(host, port) == expected


def test_render_python_relay_substitutes_placeholders(listener, main_menu_mock):
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"

    rendered = listener._render_relay(
        "port_forward_pivot/relay.py",
        listen_host="10.0.0.5",
        listen_port=8443,
        connect_host="c2.example.com",
        connect_port=443,
    )

    assert 'LISTEN_HOST = "10.0.0.5"' in rendered
    assert "LISTEN_PORT = 8443" in rendered
    assert 'CONNECT_HOST = "c2.example.com"' in rendered
    assert "CONNECT_PORT = 443" in rendered
    assert "{{ listen_host }}" not in rendered
    # The sentinels are what the listener's verification poll keys off of —
    # if they go missing, start() can't tell success from failure.
    assert "[port_forward_pivot] LISTEN_OK" in rendered
    assert "[port_forward_pivot] LISTEN_FAIL" in rendered


def test_render_powershell_relay_substitutes_placeholders(listener, main_menu_mock):
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"

    rendered = listener._render_relay(
        "port_forward_pivot/relay.ps1",
        listen_host="10.0.0.5",
        listen_port=8443,
        connect_host="c2.example.com",
        connect_port=443,
    )

    assert '"10.0.0.5"' in rendered
    assert "TcpListener" in rendered
    assert "::new($listenAddress, 8443)" in rendered
    assert '$connectHost = "c2.example.com"' in rendered
    assert "$connectPort = 443" in rendered
    assert "{{ listen_host }}" not in rendered
    assert "[port_forward_pivot] LISTEN_OK" in rendered
    assert "[port_forward_pivot] LISTEN_FAIL" in rendered


@pytest.fixture
def started_listener(monkeypatch, listener, main_menu_mock):
    """Wires up the mocks needed for start()/shutdown(): SessionLocal,
    agentsv2.get_by_id, listenersv2 lookups."""
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"
    listener.options["Agent"] = {"Value": "AGENTID1"}
    listener.options["ListenPort"] = {"Value": 8443}

    session_mock = MagicMock()
    session_mock.begin.return_value.__enter__.return_value = MagicMock()
    session_mock.begin.return_value.__exit__.return_value = False
    monkeypatch.setattr(
        "empire.server.listeners.port_forward_pivot.SessionLocal", session_mock
    )

    agent = MagicMock(
        session_id="AGENTID1",
        internal_ip="10.0.0.5",
        listener="parent_listener",
        high_integrity=True,
    )
    main_menu_mock.agentsv2.get_by_id.return_value = agent
    main_menu_mock.agenttasksv2.create_task_shell.return_value = (MagicMock(), None)

    # Parent listener mimics an HTTP listener — has Host/Port/Name/etc. but
    # NOT the pivot-specific keys (ListenPort, Agent, internalIP). start()
    # must merge the pivot's own options back over the deep-copied parent
    # options so shutdown() can still find ListenPort.
    parent_options = {
        k: v
        for k, v in dict(listener.options).items()
        if k not in ("ListenPort", "Agent", "internalIP")
    }
    parent_listener_obj = MagicMock(options=parent_options)
    main_menu_mock.listenersv2.get_by_name.return_value = parent_listener_obj
    main_menu_mock.listenersv2.get_active_listener_by_name.side_effect = lambda lname: (
        parent_listener_obj if lname == "parent_listener" else None
    )

    return listener, agent


def _set_language(main_menu_mock, language: str):
    main_menu_mock.agentsv2.get_by_id.return_value.language = language


FAKE_TASK_ID = 42


@pytest.mark.parametrize(
    ("language", "expected_task"),
    [
        ("powershell", "TASK_POWERSHELL_CMD_JOB"),
        ("csharp", "TASK_POWERSHELL_CMD_JOB"),
        ("go", "TASK_POWERSHELL_CMD_JOB"),
        ("python", "TASK_PYTHON_CMD_JOB"),
    ],
)
def test_start_dispatches_correct_task_for_language(
    started_listener, main_menu_mock, language, expected_task
):
    pivot, agent = started_listener
    _set_language(main_menu_mock, language)

    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True
    assert pivot._relay_task_id == FAKE_TASK_ID

    main_menu_mock.agenttasksv2.add_task.assert_called_once()
    args = main_menu_mock.agenttasksv2.add_task.call_args.args
    assert args[1] is agent
    assert args[2] == expected_task

    relay_payload = args[3]
    assert "8443" in relay_payload
    assert "10.0.0.5" in relay_payload


def test_start_returns_false_when_add_task_fails(started_listener, main_menu_mock):
    pivot, _ = started_listener
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.add_task.return_value = (None, "boom")

    assert pivot.start() is False
    assert pivot._relay_task_id is None
    main_menu_mock.agentsv2.save_agent_log.assert_not_called()


def test_start_rejects_unsupported_language(started_listener, main_menu_mock):
    pivot, _ = started_listener
    _set_language(main_menu_mock, "ironpython3")

    assert pivot.start() is False
    main_menu_mock.agenttasksv2.add_task.assert_not_called()


@pytest.mark.parametrize(
    ("language", "expected_keyword"),
    [
        ("csharp", "Sharpire build with multi-packet tasking blob decoding"),
        ("go", "Gopire build with backgrounded TASK_POWERSHELL_CMD_JOB"),
    ],
)
def test_start_warns_about_required_agent_build_for_csharp_and_go(
    started_listener, main_menu_mock, caplog, language, expected_keyword
):
    """csharp/go pivots depend on companion-PR agent capabilities (Sharpire
    multi-packet tasking, Gopire backgrounded jobs + TASK_STOPJOB) that are
    not advertised via agent.language_version. Until a build-version field
    exists, start() must surface a clear warning so operators can verify the
    relay actually came up."""
    pivot, _ = started_listener
    _set_language(main_menu_mock, language)
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    with caplog.at_level(
        logging.WARNING,
        logger="empire.server.listeners.port_forward_pivot",
    ):
        assert pivot.start() is True

    assert any(expected_keyword in r.message for r in caplog.records), (
        f"expected capability warning for {language}, got: "
        f"{[r.message for r in caplog.records]}"
    )


@pytest.mark.parametrize("language", ["powershell", "python"])
def test_start_does_not_warn_for_powershell_or_python(
    started_listener, main_menu_mock, caplog, language
):
    """PowerShell and Python agents have always supported the relevant
    backgrounded-job tasking primitives, so no capability warning should fire
    for them."""
    pivot, _ = started_listener
    _set_language(main_menu_mock, language)
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    with caplog.at_level(
        logging.WARNING,
        logger="empire.server.listeners.port_forward_pivot",
    ):
        assert pivot.start() is True

    assert not any(
        ("Sharpire" in r.message or "Gopire" in r.message) for r in caplog.records
    ), (
        f"unexpected capability warning for {language}: {[r.message for r in caplog.records]}"
    )


def test_shutdown_kills_persisted_relay_task(started_listener, main_menu_mock):
    pivot, agent = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_kill_job.assert_called_once()
    args = main_menu_mock.agenttasksv2.create_task_kill_job.call_args.args
    assert args[1] is agent
    assert args[2] == str(FAKE_TASK_ID)
    assert pivot._relay_task_id is None


def test_shutdown_warns_when_relay_task_id_missing(started_listener, main_menu_mock):
    pivot, _ = started_listener
    pivot._relay_task_id = None

    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_kill_job.assert_not_called()


def test_start_returns_false_when_agent_not_found(started_listener, main_menu_mock):
    pivot, _ = started_listener
    main_menu_mock.agentsv2.get_by_id.return_value = None

    assert pivot.start() is False
    main_menu_mock.agenttasksv2.add_task.assert_not_called()


def test_shutdown_swallows_create_task_kill_job_exception(
    started_listener, main_menu_mock
):
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    main_menu_mock.agenttasksv2.create_task_kill_job.side_effect = RuntimeError(
        "db gone"
    )

    pivot.shutdown()

    assert pivot._relay_task_id == FAKE_TASK_ID


def test_shutdown_is_idempotent(started_listener, main_menu_mock):
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    pivot.shutdown()
    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_kill_job.assert_called_once()
    assert pivot._relay_task_id is None


def test_start_respects_explicit_internal_ip(started_listener, main_menu_mock):
    pivot, _ = started_listener
    pivot.options["internalIP"] = {"Value": "127.0.0.1"}
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True
    relay_payload = main_menu_mock.agenttasksv2.add_task.call_args.args[3]
    assert "127.0.0.1" in relay_payload
    assert "10.0.0.5" not in relay_payload


@pytest.mark.parametrize("language", ["powershell", "csharp", "go"])
def test_start_adds_firewall_rule_for_windows_agents(
    started_listener, main_menu_mock, language
):
    pivot, agent = started_listener
    _set_language(main_menu_mock, language)
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True

    main_menu_mock.agenttasksv2.create_task_shell.assert_called_once()
    cmd = main_menu_mock.agenttasksv2.create_task_shell.call_args.args[2]
    assert "netsh advfirewall firewall add rule" in cmd
    assert f'name="empire-pivot-{agent.session_id}-8443"' in cmd
    assert "localport=8443" in cmd


def test_start_skips_firewall_rule_for_python_agent(started_listener, main_menu_mock):
    pivot, _ = started_listener
    _set_language(main_menu_mock, "python")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True
    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()


@pytest.mark.parametrize("language", ["powershell", "csharp", "go"])
def test_start_rejects_non_elevated_windows_agent(
    started_listener, main_menu_mock, language
):
    pivot, agent = started_listener
    agent.high_integrity = False
    _set_language(main_menu_mock, language)

    assert pivot.start() is False
    main_menu_mock.agenttasksv2.add_task.assert_not_called()
    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()


def test_start_allows_non_elevated_python_agent(started_listener, main_menu_mock):
    pivot, agent = started_listener
    agent.high_integrity = False
    _set_language(main_menu_mock, "python")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True


@pytest.mark.parametrize("language", ["powershell", "csharp", "go"])
def test_shutdown_removes_firewall_rule_for_windows_agents(
    started_listener, main_menu_mock, language
):
    pivot, agent = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    _set_language(main_menu_mock, language)
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_shell.assert_called_once()
    cmd = main_menu_mock.agenttasksv2.create_task_shell.call_args.args[2]
    assert "netsh advfirewall firewall delete rule" in cmd
    assert f'name="empire-pivot-{agent.session_id}-8443"' in cmd


def test_shutdown_skips_firewall_rule_for_python_agent(
    started_listener, main_menu_mock
):
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    _set_language(main_menu_mock, "python")
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()


def test_start_firewall_rule_precedes_relay_task(started_listener, main_menu_mock):
    """Order matters for stealth: the firewall rule must be queued BEFORE
    the relay job, otherwise the relay's bind hits the firewall before the
    rule is in place and Windows pops the 'Allow access' prompt."""
    pivot, _ = started_listener
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )

    assert pivot.start() is True

    method_calls = main_menu_mock.agenttasksv2.method_calls
    names = [c[0] for c in method_calls]
    assert names.index("create_task_shell") < names.index("add_task")


def test_start_returns_false_when_firewall_add_fails(started_listener, main_menu_mock):
    pivot, _ = started_listener
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.create_task_shell.return_value = (None, "db gone")

    assert pivot.start() is False
    main_menu_mock.agenttasksv2.add_task.assert_not_called()
    assert pivot._relay_task_id is None


def test_shutdown_idempotent_for_windows_does_not_resend_firewall_delete(
    started_listener, main_menu_mock
):
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    pivot.shutdown()
    pivot.shutdown()

    # First call: queues firewall delete + kill job, resets _relay_task_id.
    # Second call: language still windows but _relay_task_id is None — by
    # design we still queue the firewall delete (deterministic rule name,
    # idempotent on agent), so create_task_shell is called twice. The kill
    # job, however, must not be re-sent.
    main_menu_mock.agenttasksv2.create_task_kill_job.assert_called_once()


def test_shutdown_queues_firewall_delete_when_relay_task_id_missing(
    started_listener, main_menu_mock
):
    """Server-restart scenario: in-memory _relay_task_id was lost, but the
    firewall rule name is deterministic from session_id+listen_port, so the
    listener can still clean up the rule on the agent."""
    pivot, _ = started_listener
    pivot._relay_task_id = None
    _set_language(main_menu_mock, "powershell")

    pivot.shutdown()

    main_menu_mock.agenttasksv2.create_task_shell.assert_called_once()
    cmd = main_menu_mock.agenttasksv2.create_task_shell.call_args.args[2]
    assert "netsh advfirewall firewall delete rule" in cmd
    main_menu_mock.agenttasksv2.create_task_kill_job.assert_not_called()


@pytest.mark.parametrize(
    ("session_id", "port", "expected"),
    [
        ("AGENTID1", 8443, "empire-pivot-AGENTID1-8443"),
        ("X", 80, "empire-pivot-X-80"),
        ("AGENTID1", "9000", "empire-pivot-AGENTID1-9000"),
    ],
)
def test_firewall_rule_name_format(session_id, port, expected):
    from empire.server.listeners.port_forward_pivot import _firewall_rule_name

    assert _firewall_rule_name(session_id, port) == expected


def test_start_then_shutdown_preserves_listen_port(started_listener, main_menu_mock):
    """Regression: start() copies parent listener options over self.options,
    which previously dropped ListenPort. shutdown() then crashed with KeyError
    when reading self.options['ListenPort'] for the firewall rule name."""
    pivot, _ = started_listener
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )
    main_menu_mock.agenttasksv2.create_task_kill_job.return_value = (MagicMock(), None)

    assert pivot.start() is True
    pivot.shutdown()

    delete_calls = [
        c
        for c in main_menu_mock.agenttasksv2.create_task_shell.call_args_list
        if "delete rule" in c.args[2]
    ]
    assert len(delete_calls) == 1
    assert "empire-pivot-AGENTID1-8443" in delete_calls[0].args[2]


# ---------------------------------------------------------------------------
# C3 — relay-failure visibility (D1 in the review plan).
#
# After tasking the relay, start() polls the agent task output for a bind
# sentinel so it can distinguish a successful bind from a fast-failing
# relay (port already in use, missing agent capability). The poll is
# bounded — we don't block start() forever on slow agents — but we DO
# fail loudly when the agent reports a failure.
# ---------------------------------------------------------------------------


def test_await_relay_sentinel_returns_ok_on_listen_ok(started_listener, main_menu_mock):
    pivot, _ = started_listener
    main_menu_mock.agenttasksv2.get_task_for_agent.return_value = MagicMock(
        output="prefix\n[port_forward_pivot] LISTEN_OK 10.0.0.5:8443\nsuffix",
        status=models.AgentTaskStatus.continuous,
    )

    result = pivot._await_relay_sentinel(
        "AGENTID1", FAKE_TASK_ID, timeout_seconds=0.1, poll_interval=0.01
    )

    assert result == "ok"


def test_await_relay_sentinel_returns_error_on_listen_fail(
    started_listener, main_menu_mock
):
    pivot, _ = started_listener
    main_menu_mock.agenttasksv2.get_task_for_agent.return_value = MagicMock(
        output="[port_forward_pivot] LISTEN_FAIL 10.0.0.5:8443: address in use",
        status=models.AgentTaskStatus.completed,
    )

    result = pivot._await_relay_sentinel(
        "AGENTID1", FAKE_TASK_ID, timeout_seconds=0.1, poll_interval=0.01
    )

    assert result == "error"


def test_await_relay_sentinel_returns_error_on_task_error_status(
    started_listener, main_menu_mock
):
    """Even without an explicit LISTEN_FAIL sentinel, an agent task that ends
    in error state means the relay is dead — surface it as 'error' so
    start() can clean up the firewall rule."""
    pivot, _ = started_listener
    main_menu_mock.agenttasksv2.get_task_for_agent.return_value = MagicMock(
        output="",
        status=models.AgentTaskStatus.error,
    )

    result = pivot._await_relay_sentinel(
        "AGENTID1", FAKE_TASK_ID, timeout_seconds=0.1, poll_interval=0.01
    )

    assert result == "error"


def test_await_relay_sentinel_returns_none_on_timeout(started_listener, main_menu_mock):
    pivot, _ = started_listener
    main_menu_mock.agenttasksv2.get_task_for_agent.return_value = MagicMock(
        output="",
        status=models.AgentTaskStatus.queued,
    )

    result = pivot._await_relay_sentinel(
        "AGENTID1", FAKE_TASK_ID, timeout_seconds=0.05, poll_interval=0.01
    )

    assert result is None


def test_await_relay_sentinel_zero_timeout_skips_polling(
    started_listener, main_menu_mock
):
    """In TEST_MODE the listener passes timeout=0 to skip polling entirely.
    The DB shouldn't be touched at all in that case."""
    pivot, _ = started_listener

    result = pivot._await_relay_sentinel(
        "AGENTID1", FAKE_TASK_ID, timeout_seconds=0.0, poll_interval=0.0
    )

    assert result is None
    main_menu_mock.agenttasksv2.get_task_for_agent.assert_not_called()


def test_verify_relay_started_logs_info_when_sentinel_observed(
    monkeypatch, started_listener, main_menu_mock, caplog
):
    pivot, _ = started_listener
    monkeypatch.setattr(pivot, "_await_relay_sentinel", lambda *a, **kw: "ok")

    with caplog.at_level(
        logging.INFO,
        logger="empire.server.listeners.port_forward_pivot",
    ):
        result = pivot._verify_relay_started(
            task_id=FAKE_TASK_ID,
            agent_session_id="AGENTID1",
            language="powershell",
            listen_address="10.0.0.5",
            listen_port=8443,
            listener_name="pivot1",
        )

    assert result is True
    assert any(
        "confirmed listening on 10.0.0.5:8443" in r.message for r in caplog.records
    )


@pytest.mark.parametrize("language", ["powershell", "csharp", "go"])
def test_verify_relay_started_returns_false_and_cleans_firewall_on_error(
    monkeypatch, started_listener, main_menu_mock, language
):
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    monkeypatch.setattr(pivot, "_await_relay_sentinel", lambda *a, **kw: "error")

    result = pivot._verify_relay_started(
        task_id=FAKE_TASK_ID,
        agent_session_id="AGENTID1",
        language=language,
        listen_address="10.0.0.5",
        listen_port=8443,
        listener_name="pivot1",
    )

    assert result is False
    assert pivot._relay_task_id is None
    delete_calls = [
        c
        for c in main_menu_mock.agenttasksv2.create_task_shell.call_args_list
        if "delete rule" in c.args[2] and "empire-pivot-AGENTID1-8443" in c.args[2]
    ]
    assert len(delete_calls) == 1


def test_verify_relay_started_skips_firewall_cleanup_for_python_on_error(
    monkeypatch, started_listener, main_menu_mock
):
    """Python agents don't get a firewall rule on start(), so they don't
    need one removed on error either."""
    pivot, _ = started_listener
    pivot._relay_task_id = FAKE_TASK_ID
    monkeypatch.setattr(pivot, "_await_relay_sentinel", lambda *a, **kw: "error")

    result = pivot._verify_relay_started(
        task_id=FAKE_TASK_ID,
        agent_session_id="AGENTID1",
        language="python",
        listen_address="0.0.0.0",
        listen_port=8443,
        listener_name="pivot1",
    )

    assert result is False
    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()


def test_verify_relay_started_warns_and_returns_true_on_timeout(
    monkeypatch, started_listener, main_menu_mock, caplog
):
    """Slow agents may not check in within the verification window. We
    don't fail the listener for that — just warn and proceed, since the
    relay may still come up."""
    pivot, _ = started_listener
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.setattr(pivot, "_await_relay_sentinel", lambda *a, **kw: None)

    with caplog.at_level(
        logging.WARNING,
        logger="empire.server.listeners.port_forward_pivot",
    ):
        result = pivot._verify_relay_started(
            task_id=FAKE_TASK_ID,
            agent_session_id="AGENTID1",
            language="powershell",
            listen_address="10.0.0.5",
            listen_port=8443,
            listener_name="pivot1",
        )

    assert result is True
    assert any("not yet confirmed" in r.message for r in caplog.records)


def test_verify_relay_started_in_test_mode_returns_true_silently(
    started_listener, main_menu_mock, caplog
):
    """TEST_MODE is set in pytest.ini, so the verification poll is skipped
    and start() degrades to trust mode. No timeout warning should fire
    because the timeout was zero by design — operators only see warnings
    when the listener actually waited and got nothing back."""
    pivot, _ = started_listener

    with caplog.at_level(
        logging.WARNING,
        logger="empire.server.listeners.port_forward_pivot",
    ):
        result = pivot._verify_relay_started(
            task_id=FAKE_TASK_ID,
            agent_session_id="AGENTID1",
            language="powershell",
            listen_address="10.0.0.5",
            listen_port=8443,
            listener_name="pivot1",
        )

    assert result is True
    assert not any("not yet confirmed" in r.message for r in caplog.records)


def test_start_returns_false_when_sentinel_reports_error(
    monkeypatch, started_listener, main_menu_mock
):
    """End-to-end: start() succeeds in tasking the relay, but the
    verification poll observes LISTEN_FAIL → start() must return False
    and the relay task id must be reset for shutdown's benefit."""
    pivot, _ = started_listener
    _set_language(main_menu_mock, "powershell")
    main_menu_mock.agenttasksv2.add_task.return_value = (
        MagicMock(id=FAKE_TASK_ID),
        None,
    )
    monkeypatch.setattr(pivot, "_await_relay_sentinel", lambda *a, **kw: "error")

    assert pivot.start() is False
    assert pivot._relay_task_id is None


# ---------------------------------------------------------------------------
# C4 — host/port input validation.
#
# The relay templates render listen_host / connect_host / *_port into
# agent-side source code. Without strict validation, an operator (or
# compromised agent reporting a malicious internal_ip) could break the
# script or inject code on the agent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "10.0.0.5",
        "127.0.0.1",
        "192.168.1.1",
        "::1",
        "[::1]",
        "2001:db8::1",
        "example.com",
        "host-1.example.co.uk",
        "a",
        "a.b",
        "x" * 63 + ".com",  # max-length label
    ],
)
def test_validate_host_accepts_valid_ip_or_hostname(value):
    from empire.server.listeners.port_forward_pivot import _validate_host

    assert _validate_host(value, "field") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        '10.0.0.5"; pwned; "',
        "10.0.0.5; rm -rf /",
        "10.0.0.5\nWrite-Output evil",
        "10.0.0.5`Get-Process`",
        "10.0.0.5$($env:USERNAME)",
        "host name with spaces",
        "host_with_underscore",
        "-leading-hyphen.com",
        "trailing-hyphen-.com",
        "label-too-long-" + "x" * 60 + ".com",  # >63 chars in one label
        "a." * 130,  # overall >253 chars
        "..",
    ],
)
def test_validate_host_rejects_injection_or_malformed(value):
    from empire.server.listeners.port_forward_pivot import _validate_host

    with pytest.raises(ValueError, match="field"):
        _validate_host(value, "field")


@pytest.mark.parametrize(
    "value",
    [
        1,
        80,
        "80",
        65535,
        "65535",
        "8443",
    ],
)
def test_validate_port_accepts_in_range_int_or_intstring(value):
    from empire.server.listeners.port_forward_pivot import _validate_port

    assert _validate_port(value, "field") == int(value)


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        65536,
        100000,
        "abc",
        "8443; pwned",
        None,
        "",
    ],
)
def test_validate_port_rejects_out_of_range_or_non_int(value):
    from empire.server.listeners.port_forward_pivot import _validate_port

    with pytest.raises(ValueError, match="field"):
        _validate_port(value, "field")


def test_start_rejects_injection_in_internal_ip(
    started_listener, main_menu_mock, caplog
):
    """A compromised agent reporting internal_ip='10.0.0.5"; do_evil; "'
    must not get that string templated into the relay script."""
    pivot, agent = started_listener
    agent.internal_ip = '10.0.0.5"; do_evil; "'
    pivot.options["internalIP"] = {
        "Value": ""
    }  # force fall-through to agent.internal_ip
    _set_language(main_menu_mock, "powershell")

    with caplog.at_level(
        logging.ERROR, logger="empire.server.listeners.port_forward_pivot"
    ):
        assert pivot.start() is False

    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()
    main_menu_mock.agenttasksv2.add_task.assert_not_called()
    assert any("invalid listener config" in r.message for r in caplog.records)


def test_start_rejects_injection_in_parent_host(
    started_listener, main_menu_mock, caplog
):
    """Operator-controlled parent listener Host must also be validated —
    even though they could already task arbitrary code, the relay should
    not be the path to do it accidentally via a typo."""
    pivot, _ = started_listener
    # start() overwrites self.options from the parent listener's options,
    # so the malicious Host has to be planted on the parent (not the pivot)
    # to survive the merge.
    parent_listener_obj = main_menu_mock.listenersv2.get_by_name.return_value
    parent_listener_obj.options["Host"] = {"Value": 'https://example.com"; pwned; "'}
    _set_language(main_menu_mock, "powershell")

    with caplog.at_level(
        logging.ERROR, logger="empire.server.listeners.port_forward_pivot"
    ):
        assert pivot.start() is False

    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()
    main_menu_mock.agenttasksv2.add_task.assert_not_called()
    assert any("invalid listener config" in r.message for r in caplog.records)


def test_start_rejects_invalid_listen_port(started_listener, main_menu_mock):
    pivot, _ = started_listener
    pivot.options["ListenPort"] = {"Value": "70000"}  # > 65535
    _set_language(main_menu_mock, "powershell")

    assert pivot.start() is False
    main_menu_mock.agenttasksv2.create_task_shell.assert_not_called()
    main_menu_mock.agenttasksv2.add_task.assert_not_called()


def test_render_relay_rejects_injection_defense_in_depth(listener, main_menu_mock):
    """Even if a future caller bypasses start()'s validation,
    _render_relay must still reject hostile inputs."""
    main_menu_mock.install_path = Path(__file__).resolve().parents[1] / "server"

    with pytest.raises(ValueError, match="connect_host"):
        listener._render_relay(
            "port_forward_pivot/relay.py",
            listen_host="10.0.0.5",
            listen_port=8443,
            connect_host='evil"; do_evil; "',
            connect_port=443,
        )
