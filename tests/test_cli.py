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
