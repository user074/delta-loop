import signal

from delta_loop import cli


def test_open_when_ready_opens_the_browser(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(cli, "_app_is_running", lambda _url: True)
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)

    cli._open_when_ready("http://127.0.0.1:4317")

    assert opened == ["http://127.0.0.1:4317"]


def test_installed_cli_defaults_to_single_app_address(monkeypatch) -> None:
    monkeypatch.delenv("DELTA_LOOP_API_URL", raising=False)

    assert cli._default_api_url() == "http://127.0.0.1:4317"
    assert cli._default_ws_url() == "ws://127.0.0.1:4317"


def test_remote_connection_avoids_a_stale_forwarded_port(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_app_is_running", lambda _url: False)
    monkeypatch.setattr(cli, "_port_is_available", lambda port: port == 4319)

    assert cli._connection_port(4318) == (4319, False)


def test_remote_connection_reuses_a_working_forward(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_app_is_running", lambda url: url.endswith(":4318"))

    assert cli._connection_port(4318) == (4318, True)


def test_serve_records_process_so_delta_loop_can_stop_it(
    tmp_path, monkeypatch
) -> None:
    import delta_loop.api as api
    import uvicorn

    registry = tmp_path / "server-4317.json"
    application = object()
    events: list[tuple] = []
    monkeypatch.setattr(cli, "_server_registry_path", lambda _port: registry)
    monkeypatch.setattr(
        cli,
        "_write_server_registry",
        lambda path, host, port: events.append(("write", path, host, port)),
    )
    monkeypatch.setattr(
        cli,
        "_remove_server_registry",
        lambda path, pid: events.append(("remove", path, pid)),
    )
    monkeypatch.setattr(api, "create_app", lambda **_kwargs: application)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: events.append(("run", app, kwargs)),
    )

    cli.main(["serve", "--host", "127.0.0.1", "--port", "4317"])

    assert events[0] == ("write", registry, "127.0.0.1", 4317)
    assert events[1] == (
        "run",
        application,
        {"host": "127.0.0.1", "port": 4317, "reload": False},
    )
    assert events[2][0:2] == ("remove", registry)


def test_status_distinguishes_live_terminals_from_saved_chats(
    tmp_path, monkeypatch, capsys
) -> None:
    registry = tmp_path / "server-4317.json"
    registry.write_text('{"pid": 1234}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "_app_is_running", lambda _url: True)
    monkeypatch.setattr(cli, "_server_registry_path", lambda _port, _data: registry)
    monkeypatch.setattr(
        cli,
        "_active_terminal_sessions",
        lambda _url: [
            {
                "id": "terminal-one",
                "workspace_id": "workspace",
                "kind": "discussion",
                "title": "Chat · Research",
                "persistent": True,
                "status": "active",
            }
        ],
    )

    cli._show_ui_status("127.0.0.1", 4317, None)

    output = capsys.readouterr().out
    assert "Server process: 1234" in output
    assert "terminal-one · chat · Chat · Research · persistent" in output
    assert "Saved Codex chats are not active processes" in output


def test_stop_ends_terminals_before_stopping_the_server(
    tmp_path, monkeypatch, capsys
) -> None:
    registry = tmp_path / "server-4317.json"
    registry.write_text('{"pid": 1234}\n', encoding="utf-8")
    checks = iter([True, False])
    monkeypatch.setattr(cli, "_app_is_running", lambda _url: next(checks))
    monkeypatch.setattr(cli, "_server_registry_path", lambda _port, _data: registry)
    monkeypatch.setattr(
        cli,
        "_active_terminal_sessions",
        lambda _url: [
            {
                "id": "terminal-one",
                "workspace_id": "workspace one",
                "status": "active",
            }
        ],
    )
    requests: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cli,
        "_api_json",
        lambda _url, path, method="GET", payload=None: requests.append((method, path)) or {},
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    cli._stop_ui("127.0.0.1", 4317, None)

    assert requests == [("DELETE", "/api/workspaces/workspace%20one/terminals")]
    assert signals == [(1234, signal.SIGTERM)]
    assert not registry.exists()
    assert "Stopped Delta Loop and 1 active terminal(s)." in capsys.readouterr().out
