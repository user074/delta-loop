import time
from pathlib import Path

from delta_loop.terminal import DEFAULT_AGENT_COMMAND, TerminalManager


def test_terminal_survives_detach_and_accepts_input(tmp_path: Path) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1")
    assert manager.acquire_input(session.id)
    manager.write(
        session.id,
        b"if command -v delta >/dev/null; then printf 'delta-command-ok\\n'; fi; "
        b"printf 'terminal-ok\\n'\n",
    )

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"terminal-ok" in output:
            break
        time.sleep(0.05)

    manager.release_input(session.id)
    assert manager.acquire_input(session.id)
    assert b"terminal-ok" in output
    assert b"delta-command-ok" in output
    manager.release_input(session.id)
    manager.close(session.id)


def test_terminal_can_start_an_agent_discussion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DELTA_LOOP_AGENT_COMMAND", "/usr/bin/printf")
    manager = TerminalManager()
    session = manager.create(
        "workspace",
        str(tmp_path),
        "idea-1",
        "Discuss the selected idea.",
        "discussion",
    )

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"Discuss the selected idea." in output:
            break
        time.sleep(0.05)

    assert b"Discuss the selected idea." in output
    assert session.kind == "discussion"
    manager.close(session.id)


def test_agent_discussion_receives_complete_loop_and_policy_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DELTA_LOOP_AGENT_COMMAND", "/usr/bin/printf")
    manager = TerminalManager()
    session = manager.create(
        "workspace",
        str(tmp_path),
        "idea-1",
        "Discuss the selected idea.",
    )

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"LOOP.md" in output and b"POLICY.md" in output:
            break
        time.sleep(0.05)

    assert str(tmp_path / ".delta-loop" / "LOOP.md").encode() in output
    assert str(tmp_path / ".delta-loop" / "POLICY.md").encode() in output
    assert b"complete active loop" in output
    assert b"another supervisor file" in output
    assert b"SUPERVISOR.md" not in output
    manager.close(session.id)


def test_research_supervisor_session_is_distinct_from_shell_and_chat(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DELTA_LOOP_AGENT_COMMAND", "/usr/bin/printf")
    manager = TerminalManager()
    session = manager.create(
        "workspace",
        str(tmp_path),
        None,
        "Start the real research loop and continue until a stop rule applies.",
        "research",
    )

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"Start the real research loop" in output:
            break
        time.sleep(0.05)

    assert session.kind == "research"
    assert b"Start the real research loop" in output
    assert str(tmp_path / ".delta-loop" / "LOOP.md").encode() in output
    manager.close(session.id)


def test_default_agent_runs_without_prompts_inside_the_project() -> None:
    assert "--ask-for-approval never" in DEFAULT_AGENT_COMMAND
    assert "--sandbox workspace-write" in DEFAULT_AGENT_COMMAND
    assert "sandbox_workspace_write.network_access=true" in DEFAULT_AGENT_COMMAND
    assert "features.network_proxy.enabled=true" in DEFAULT_AGENT_COMMAND
    assert "features.network_proxy.allow_local_binding=true" in DEFAULT_AGENT_COMMAND
    assert 'domains={ "127.0.0.1" = "allow" }' in DEFAULT_AGENT_COMMAND
    assert "danger-full-access" not in DEFAULT_AGENT_COMMAND
    assert "--yolo" not in DEFAULT_AGENT_COMMAND


def test_installed_terminal_uses_the_single_app_address(tmp_path: Path) -> None:
    manager = TerminalManager(api_url="http://127.0.0.1:4321")
    session = manager.create("workspace", str(tmp_path), None)
    manager.write(session.id, b"printf 'api=%s\\n' \"$DELTA_LOOP_API_URL\"\n")

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"api=http://127.0.0.1:4321" in output:
            break
        time.sleep(0.05)

    assert b"api=http://127.0.0.1:4321" in output
    manager.close(session.id)
