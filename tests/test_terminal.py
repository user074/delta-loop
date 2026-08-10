import time
from pathlib import Path

from delta_loop.terminal import TerminalManager


def test_terminal_survives_detach_and_accepts_input(tmp_path: Path) -> None:
    manager = TerminalManager()
    session = manager.create("workspace", str(tmp_path), "idea-1")
    assert manager.acquire_input(session.id)
    manager.write(session.id, b"printf 'terminal-ok\\n'\n")

    output = b""
    for _ in range(60):
        output += manager.read(session.id)
        if b"terminal-ok" in output:
            break
        time.sleep(0.05)

    manager.release_input(session.id)
    assert manager.acquire_input(session.id)
    assert b"terminal-ok" in output
    manager.release_input(session.id)
    manager.close(session.id)
