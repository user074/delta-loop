import os
import signal
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


def test_agent_discussion_receives_only_requested_startup_message(tmp_path: Path, monkeypatch) -> None:
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
        if b"Discuss the selected idea." in output:
            break
        time.sleep(0.05)

    assert output == b"Discuss the selected idea."
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
    assert b"LOOP.md" not in output
    manager.close(session.id)


def test_goal_is_typed_into_the_live_agent_instead_of_passed_as_plain_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DELTA_LOOP_AGENT_COMMAND", "/bin/sh")
    manager = TerminalManager()
    goal = "/goal Keep running research cycles until the saved stop condition applies."
    session = manager.create("workspace", str(tmp_path), None, goal, "research")
    record = manager._sessions[session.id]

    assert record.process.args == ["/bin/sh"]

    output = b""
    for _ in range(80):
        output += manager.read(session.id)
        if goal.encode() in output:
            break
        time.sleep(0.05)

    assert goal.encode() in output
    manager.close(session.id)


def test_running_terminals_with_the_same_context_get_distinct_titles(tmp_path: Path) -> None:
    manager = TerminalManager()
    first = manager.create("workspace", str(tmp_path), "idea-1", title="Terminal · Idea")
    second = manager.create("workspace", str(tmp_path), "idea-1", title="Terminal · Idea")

    assert first.title == "Terminal · Idea"
    assert second.title == "Terminal 2 · Idea"

    manager.close(first.id)
    manager.close(second.id)


def test_close_all_ends_every_owned_terminal(tmp_path: Path) -> None:
    manager = TerminalManager()
    first = manager.create("workspace-one", str(tmp_path), None)
    second = manager.create("workspace-two", str(tmp_path), None)
    first_process = manager._sessions[first.id].process
    second_process = manager._sessions[second.id].process

    assert manager.close_all() == 2
    first_process.wait(timeout=3)
    second_process.wait(timeout=3)

    assert manager.get(first.id).status == "exited"
    assert manager.get(second.id).status == "exited"


def test_terminal_keeps_output_while_no_browser_is_attached(tmp_path: Path) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1")
    manager.write(session.id, b"printf 'message-before-switch\\n'\n")

    transcript = b""
    cursor = 0
    for _ in range(60):
        transcript, cursor = manager.transcript(session.id)
        if b"message-before-switch" in transcript:
            break
        time.sleep(0.05)

    assert b"message-before-switch" in transcript

    manager.write(session.id, b"printf 'message-after-switch\\n'\n")
    later_output = b""
    for _ in range(60):
        data, cursor = manager.output_since(session.id, cursor)
        later_output += data
        if b"message-after-switch" in later_output:
            break
        time.sleep(0.05)

    assert b"message-after-switch" in later_output
    manager.close(session.id)


def test_persistent_connection_replays_one_live_redraw_not_plain_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1")
    record = manager._sessions[session.id]
    record.tmux_session = "delta-loop-test"
    manager._tmux = "/fake/tmux"
    record.append_output(b"old raw output that must not be replayed")

    monkeypatch.setattr(manager, "_tmux_alive", lambda _name: True)
    monkeypatch.setattr(manager, "_get_size", lambda _fd: (100, 28))
    monkeypatch.setattr(os, "killpg", lambda _pid, _signal: None)

    sizes: list[tuple[int, int]] = []

    def resize_with_redraw(_fd: int, columns: int, rows: int) -> None:
        sizes.append((columns, rows))
        if (columns, rows) == (84, 24):
            record.append_output(b"\x1b[2J\x1b[Hclean live screen")

    monkeypatch.setattr(manager, "_set_size", resize_with_redraw)

    output, cursor = manager.connection_output(session.id, 84, 24)

    assert output.startswith(b"\x1bc\x1b[2J\x1b[H")
    assert b"clean live screen" in output
    assert b"old raw output" not in output
    assert sizes[-1] == (84, 24)
    assert cursor == record.next_sequence
    record.tmux_session = None
    manager.close(session.id)


def test_agent_connection_forces_a_clean_redraw_without_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1", kind="discussion")
    record = manager._sessions[session.id]
    record.append_output(b"old frames at a different width")

    monkeypatch.setattr(manager, "_get_size", lambda _fd: (100, 28))
    monkeypatch.setattr(os, "killpg", lambda _pid, _signal: None)

    def resize_with_redraw(_fd: int, columns: int, rows: int) -> None:
        if (columns, rows) == (96, 22):
            record.append_output(b"\x1b[2J\x1b[Hagent redraw at browser width")

    monkeypatch.setattr(manager, "_set_size", resize_with_redraw)

    output, cursor = manager.connection_output(session.id, 96, 22)

    assert output.startswith(b"\x1bc\x1b[2J\x1b[H")
    assert b"agent redraw at browser width" in output
    assert b"old frames" not in output
    assert cursor == record.next_sequence
    manager.close(session.id)


def test_persistent_resize_sets_tmux_window_to_browser_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1")
    record = manager._sessions[session.id]
    record.tmux_session = "delta-loop-test"
    manager._tmux = "/fake/tmux"
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs):
        commands.append(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("delta_loop.terminal.subprocess.run", run)

    manager.resize(session.id, 164, 51)

    assert manager._get_size(record.master_fd) == (164, 51)
    assert commands == [[
        "/fake/tmux",
        "resize-window",
        "-x",
        "164",
        "-y",
        "51",
        "-t",
        "delta-loop-test:0",
    ]]
    record.tmux_session = None
    manager.close(session.id)


def test_default_agent_can_manage_git_and_paths_outside_the_project() -> None:
    assert "--dangerously-bypass-approvals-and-sandbox" in DEFAULT_AGENT_COMMAND
    assert "--enable goals" in DEFAULT_AGENT_COMMAND
    assert "--sandbox workspace-write" not in DEFAULT_AGENT_COMMAND
    assert "--ask-for-approval" not in DEFAULT_AGENT_COMMAND


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


def test_tmux_terminal_is_restored_after_manager_restart(tmp_path: Path, monkeypatch) -> None:
    fake_state = tmp_path / "fake-tmux"
    fake_state.mkdir()
    fake_tmux = tmp_path / "tmux"
    fake_tmux.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import sys

root = pathlib.Path(os.environ["FAKE_TMUX_DIR"])
args = sys.argv[1:]
with (root / "commands.log").open("a") as log:
    log.write(" ".join(args) + "\\n")
command = args[0]
flag = "-s" if command == "new-session" else "-t"
name = args[args.index(flag) + 1]
marker = root / f"{name}.session"
history = root / f"{name}.history"

if command == "new-session":
    marker.write_text("active")
elif command == "has-session":
    raise SystemExit(0 if marker.exists() else 1)
elif command == "capture-pane":
    if history.exists():
        sys.stdout.buffer.write(history.read_bytes())
elif command == "display-message":
    print("1")
elif command == "kill-session":
    marker.unlink(missing_ok=True)
elif command == "attach-session":
    while marker.exists():
        data = os.read(0, 4096)
        if not data:
            break
        with history.open("ab") as output:
            output.write(data)
        os.write(1, data)
""",
        encoding="utf-8",
    )
    fake_tmux.chmod(0o755)
    monkeypatch.setenv("FAKE_TMUX_DIR", str(fake_state))
    monkeypatch.setattr("delta_loop.terminal.shutil.which", lambda _name: str(fake_tmux))
    registry = tmp_path / "terminals.json"

    first_manager = TerminalManager(state_path=registry)
    first = first_manager.create("workspace", str(tmp_path), "idea-1")
    assert first.persistent
    first_manager.write(first.id, b"conversation-before-restart\n")
    time.sleep(0.1)
    first_record = first_manager._sessions[first.id]
    os.killpg(first_record.process.pid, signal.SIGTERM)
    first_record.process.wait(timeout=3)

    second_manager = TerminalManager(state_path=registry)
    restored = second_manager.list("workspace")

    assert [item.id for item in restored] == [first.id]
    assert restored[0].status == "active"
    assert restored[0].persistent
    assert b"conversation-before-restart" in second_manager.read(first.id)
    captured, _ = second_manager.transcript(first.id)
    assert b"conversation-before-restart\r\n" in captured
    second_manager.latest(first.id)
    second_manager.scroll(first.id, -12)
    commands = (fake_state / "commands.log").read_text(encoding="utf-8")
    assert "history-limit 50000" in commands
    assert "mouse on" in commands
    assert "status off" in commands
    assert "send-keys -X" in commands
    assert "copy-mode -t" in commands
    assert "-N 12" in commands
    assert "scroll-up" in commands
    second_manager.close(first.id)
