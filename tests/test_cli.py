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
