from __future__ import annotations

from collections import deque
import fcntl
import json
import os
import pty
import select
import signal
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path
from uuid import uuid4

from .models import TerminalKind, TerminalSessionInfo, now_iso


DEFAULT_AGENT_COMMAND = (
    "codex --no-alt-screen --enable goals --dangerously-bypass-approvals-and-sandbox"
)

TRANSCRIPT_LIMIT_BYTES = 16 * 1024 * 1024
TRANSCRIPT_TRIMMED_MESSAGE = b"\x1b[0m\r\n[Older terminal output was trimmed.]\r\n"
TERMINAL_RESET = b"\x1bc"


class TerminalFailure(ValueError):
    pass


class _TerminalRecord:
    def __init__(
        self,
        info: TerminalSessionInfo,
        process: subprocess.Popen[bytes],
        master_fd: int,
        tmux_session: str | None = None,
        replay: bytes = b"",
    ) -> None:
        self.info = info
        self.process = process
        self.master_fd = master_fd
        self.tmux_session = tmux_session
        self.output_chunks: deque[tuple[int, bytes]] = deque()
        self.output_bytes = 0
        self.next_sequence = 0
        self.legacy_cursor = 0
        self.output_truncated = False
        self.lock = threading.RLock()
        if replay:
            self.append_output(replay)
        self.input_attached = False

    def append_output(self, data: bytes) -> None:
        if not data:
            return
        with self.lock:
            self.output_chunks.append((self.next_sequence, data))
            self.next_sequence += 1
            self.output_bytes += len(data)
            while self.output_bytes > TRANSCRIPT_LIMIT_BYTES and len(self.output_chunks) > 1:
                _, removed = self.output_chunks.popleft()
                self.output_bytes -= len(removed)
                self.output_truncated = True

    def snapshot(self) -> tuple[bytes, int]:
        with self.lock:
            prefix = TRANSCRIPT_TRIMMED_MESSAGE if self.output_truncated else b""
            return prefix + b"".join(data for _, data in self.output_chunks), self.next_sequence

    def output_since(self, sequence: int) -> tuple[bytes, int]:
        with self.lock:
            first_sequence = self.output_chunks[0][0] if self.output_chunks else self.next_sequence
            if sequence < first_sequence:
                return self.snapshot()
            data = b"".join(data for item_sequence, data in self.output_chunks if item_sequence >= sequence)
            return data, self.next_sequence


class TerminalManager:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:4318",
        state_path: str | Path | None = None,
    ) -> None:
        self._sessions: dict[str, _TerminalRecord] = {}
        self._lock = threading.RLock()
        self._api_url = api_url.rstrip("/")
        self._state_path = Path(state_path).expanduser().resolve() if state_path else None
        self._tmux = shutil.which("tmux") if self._state_path else None
        self._restore()

    def create(
        self,
        workspace_id: str,
        working_directory: str,
        node_id: str | None,
        agent_prompt: str | None = None,
        kind: TerminalKind = "shell",
        title: str = "",
    ) -> TerminalSessionInfo:
        root = Path(working_directory).expanduser().resolve()
        if not root.is_dir():
            raise TerminalFailure("The project folder no longer exists.")
        shell = os.environ.get("SHELL", "/bin/zsh")
        session_id = f"terminal-{uuid4().hex[:10]}"
        env = {
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
            "TERM": "xterm-256color",
            "DELTA_LOOP_API_URL": self._api_url,
            "DELTA_LOOP_TERMINAL_ID": session_id,
            "DELTA_LOOP_WORKSPACE_ID": workspace_id,
            "DELTA_LOOP_NODE_ID": node_id or "",
            "DELTA_LOOP_INSTRUCTIONS": str(root / ".delta-loop" / "LOOP.md"),
        }
        command = [shell, "-l"]
        initial_input: bytes | None = None
        if agent_prompt:
            agent_command = os.environ.get("DELTA_LOOP_AGENT_COMMAND", DEFAULT_AGENT_COMMAND)
            if agent_prompt.lstrip().startswith("/goal "):
                command = shlex.split(agent_command)
                initial_input = agent_prompt.strip().encode() + b"\r"
            else:
                command = [*shlex.split(agent_command), agent_prompt]
        base_title = title.strip() or ("Agent chat" if kind == "discussion" else "Research" if kind == "research" else "Terminal")
        with self._lock:
            active_titles = {
                record.info.title
                for record in self._sessions.values()
                if record.info.workspace_id == workspace_id and record.info.status == "active"
            }
        available_title = base_title
        suffix = 2
        while available_title in active_titles:
            if " · " in base_title:
                label, context = base_title.split(" · ", 1)
                available_title = f"{label} {suffix} · {context}"
            else:
                available_title = f"{base_title} {suffix}"
            suffix += 1
        info = TerminalSessionInfo(
            id=session_id,
            workspace_id=workspace_id,
            node_id=node_id,
            working_directory=str(root),
            kind=kind,
            title=available_title,
            persistent=bool(self._tmux),
        )
        if self._tmux:
            record = self._start_tmux(info, command, env)
        else:
            process, master_fd = self._spawn(command, root, env)
            record = _TerminalRecord(info, process, master_fd)
        with self._lock:
            self._sessions[session_id] = record
            self._save()
        self._start_reader(record)
        if initial_input:
            self._queue_initial_input(record, initial_input)
        return info

    def list(self, workspace_id: str) -> list[TerminalSessionInfo]:
        self._refresh()
        with self._lock:
            return [record.info for record in self._sessions.values() if record.info.workspace_id == workspace_id]

    @staticmethod
    def _queue_initial_input(record: _TerminalRecord, data: bytes) -> None:
        """Enter a TUI slash command only after the interactive screen is ready.

        Passing `/goal` as Codex's positional PROMPT sends ordinary model text and
        does not activate goal mode. Waiting for the first terminal output and then
        typing into the PTY follows the same path as a researcher entering the slash
        command in the composer.
        """

        def send_when_ready() -> None:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and record.process.poll() is None:
                with record.lock:
                    screen_started = record.next_sequence > 0
                if screen_started:
                    time.sleep(0.6)
                    if record.process.poll() is None:
                        try:
                            os.write(record.master_fd, data)
                        except OSError:
                            pass
                    return
                time.sleep(0.05)

        threading.Thread(target=send_when_ready, daemon=True).start()

    def get(self, session_id: str) -> TerminalSessionInfo | None:
        self._refresh()
        with self._lock:
            record = self._sessions.get(session_id)
            return record.info if record else None

    def acquire_input(self, session_id: str) -> bool:
        record = self._record(session_id)
        with record.lock:
            if record.input_attached:
                return False
            record.input_attached = True
            return True

    def release_input(self, session_id: str) -> None:
        record = self._record(session_id)
        with record.lock:
            record.input_attached = False

    def read(self, session_id: str) -> bytes:
        record = self._record(session_id)
        with record.lock:
            cursor = record.legacy_cursor
        data, next_cursor = record.output_since(cursor)
        with record.lock:
            record.legacy_cursor = next_cursor
        return data

    def transcript(self, session_id: str) -> tuple[bytes, int]:
        record = self._record(session_id)
        if record.tmux_session and self._tmux_alive(record.tmux_session):
            captured = self._capture_tmux(record.tmux_session)
            if captured:
                with record.lock:
                    cursor = record.next_sequence
                return captured, cursor
        return record.snapshot()

    def connection_output(
        self,
        session_id: str,
        columns: int,
        rows: int,
    ) -> tuple[bytes, int]:
        """Return a screen state that matches the browser's terminal size.

        A persistent terminal is backed by tmux. Replaying capture-pane text and
        then appending tmux's ANSI redraw stream corrupts the screen because the
        two representations do not share a cursor position. Instead, resize the
        live tmux client, force one real redraw, and send only that ANSI stream.
        tmux remains the source of scrollback for persistent sessions.
        """
        record = self._record(session_id)
        columns = max(20, min(columns, 500))
        rows = max(4, min(rows, 200))
        persistent = bool(record.tmux_session and self._tmux_alive(record.tmux_session))
        live_screen = persistent or record.info.kind in {"discussion", "research"}
        if not live_screen:
            self._set_size(record.master_fd, columns, rows)
            # Give full-screen programs a brief chance to repaint at the new
            # width before taking the raw replay snapshot.
            time.sleep(0.04)
            return record.snapshot()

        with record.lock:
            cursor = record.next_sequence

        current_columns, current_rows = self._get_size(record.master_fd)
        if (current_columns, current_rows) == (columns, rows):
            # TIOCSWINSZ is not required to signal when the size is unchanged.
            # A one-column nudge guarantees that tmux emits a complete redraw.
            temporary_columns = columns - 1 if columns > 20 else columns + 1
            self._set_size(record.master_fd, temporary_columns, rows)
        self._set_size(record.master_fd, columns, rows)
        try:
            os.killpg(record.process.pid, signal.SIGWINCH)
        except (ProcessLookupError, PermissionError):
            pass

        deadline = time.monotonic() + 0.5
        last_sequence = cursor
        last_change = time.monotonic()
        while time.monotonic() < deadline:
            _, next_sequence = record.output_since(cursor)
            now = time.monotonic()
            if next_sequence != last_sequence:
                last_sequence = next_sequence
                last_change = now
            if last_sequence != cursor and now - last_change >= 0.04:
                break
            time.sleep(0.01)

        redraw, next_cursor = record.output_since(cursor)
        if redraw:
            return TERMINAL_RESET + redraw, next_cursor

        # This should only occur with an unusual tmux build that does not redraw
        # on SIGWINCH. Keep the fallback internally consistent by advancing the
        # cursor after capture, so later ANSI frames cannot race the snapshot.
        captured = (
            self._capture_tmux(record.tmux_session)
            if persistent and record.tmux_session
            else record.snapshot()[0]
        )
        with record.lock:
            next_cursor = record.next_sequence
        return TERMINAL_RESET + captured, next_cursor

    def output_since(self, session_id: str, sequence: int) -> tuple[bytes, int]:
        return self._record(session_id).output_since(sequence)

    def write(self, session_id: str, data: bytes) -> None:
        record = self._record(session_id)
        if record.process.poll() is not None:
            record.info.status = "exited"
            raise TerminalFailure("This terminal has ended.")
        os.write(record.master_fd, data)
        record.info.last_active_at = now_iso()

    def resize(self, session_id: str, columns: int, rows: int) -> None:
        record = self._record(session_id)
        self._set_size(record.master_fd, columns, rows)

    def latest(self, session_id: str) -> None:
        record = self._record(session_id)
        if not record.tmux_session or not self._tmux:
            return
        subprocess.run(
            [self._tmux, "send-keys", "-X", "-t", f"{record.tmux_session}:0.0", "cancel"],
            capture_output=True,
            check=False,
            timeout=3,
        )

    def scroll(self, session_id: str, lines: int) -> None:
        record = self._record(session_id)
        if not lines or not record.tmux_session or not self._tmux:
            return
        amount = max(1, min(abs(lines), 200))
        target = f"{record.tmux_session}:0.0"
        if lines < 0:
            subprocess.run(
                [self._tmux, "copy-mode", "-t", target],
                capture_output=True,
                check=False,
                timeout=3,
            )
            command = "scroll-up"
        else:
            command = "scroll-down"
        subprocess.run(
            [self._tmux, "send-keys", "-X", "-N", str(amount), "-t", target, command],
            capture_output=True,
            check=False,
            timeout=3,
        )

    def close(self, session_id: str) -> None:
        record = self._record(session_id)
        if record.tmux_session and self._tmux:
            subprocess.run(
                [self._tmux, "kill-session", "-t", record.tmux_session],
                capture_output=True,
                check=False,
                timeout=3,
            )
        if record.process.poll() is None:
            try:
                os.killpg(record.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                try:
                    record.process.terminate()
                except (ProcessLookupError, PermissionError):
                    pass
        record.info.status = "exited"
        self._save()

    def close_workspace(self, workspace_id: str) -> int:
        with self._lock:
            session_ids = [
                record.info.id
                for record in self._sessions.values()
                if record.info.workspace_id == workspace_id and record.info.status == "active"
            ]
        for session_id in session_ids:
            self.close(session_id)
        return len(session_ids)

    def detach_all(self) -> None:
        """Detach browser-facing tmux clients without ending their sessions."""
        with self._lock:
            records = list(self._sessions.values())
        for record in records:
            if not record.tmux_session or record.process.poll() is not None:
                continue
            try:
                os.killpg(record.process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    def _record(self, session_id: str) -> _TerminalRecord:
        with self._lock:
            record = self._sessions.get(session_id)
        if not record:
            raise TerminalFailure("Terminal not found.")
        return record

    def _refresh(self) -> None:
        with self._lock:
            records = list(self._sessions.values())
        changed = False
        for record in records:
            if record.tmux_session:
                if not self._tmux_alive(record.tmux_session):
                    if record.info.status != "lost":
                        record.info.status = "lost"
                        changed = True
                elif record.process.poll() is not None:
                    self._reattach(record)
            elif record.process.poll() is not None:
                record.info.status = "exited"
        if changed:
            self._save()

    def _start_reader(self, record: _TerminalRecord) -> None:
        master_fd = record.master_fd
        process = record.process

        def pump() -> None:
            while True:
                with record.lock:
                    if record.master_fd != master_fd:
                        return
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                except (OSError, ValueError):
                    return
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    data = os.read(master_fd, 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if not data:
                    break
                record.append_output(data)
                record.info.last_active_at = now_iso()
            if not record.tmux_session and process.poll() is not None:
                record.info.status = "exited"
                self._save()

        threading.Thread(
            target=pump,
            name=f"delta-loop-output-{record.info.id}",
            daemon=True,
        ).start()

    def _spawn(
        self,
        command: list[str],
        root: Path,
        env: dict[str, str],
    ) -> tuple[subprocess.Popen[bytes], int]:
        master_fd, slave_fd = pty.openpty()
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
                env=env,
            )
        finally:
            os.close(slave_fd)
        os.set_blocking(master_fd, False)
        self._set_size(master_fd, 100, 28)
        return process, master_fd

    def _start_tmux(
        self,
        info: TerminalSessionInfo,
        command: list[str],
        env: dict[str, str],
    ) -> _TerminalRecord:
        if not self._tmux:
            raise TerminalFailure("Persistent terminal support is unavailable.")
        tmux_session = f"delta-loop-{info.id.removeprefix('terminal-')}"
        exported = [
            "env",
            f"PATH={env['PATH']}",
            f"TERM={env['TERM']}",
            f"DELTA_LOOP_API_URL={env['DELTA_LOOP_API_URL']}",
            f"DELTA_LOOP_TERMINAL_ID={env['DELTA_LOOP_TERMINAL_ID']}",
            f"DELTA_LOOP_WORKSPACE_ID={env['DELTA_LOOP_WORKSPACE_ID']}",
            f"DELTA_LOOP_NODE_ID={env['DELTA_LOOP_NODE_ID']}",
            f"DELTA_LOOP_INSTRUCTIONS={env['DELTA_LOOP_INSTRUCTIONS']}",
            *command,
        ]
        started = subprocess.run(
            [
                self._tmux,
                "new-session",
                "-d",
                "-s",
                tmux_session,
                "-c",
                info.working_directory,
                shlex.join(exported),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
            env=env,
        )
        if started.returncode != 0:
            detail = started.stderr.strip() or "tmux could not start the terminal."
            raise TerminalFailure(detail)
        self._configure_tmux(tmux_session)
        try:
            process, master_fd = self._attach_tmux(tmux_session, Path(info.working_directory), env)
            self._wait_tmux_attached(tmux_session, process)
        except (OSError, TerminalFailure):
            subprocess.run(
                [self._tmux, "kill-session", "-t", tmux_session],
                capture_output=True,
                check=False,
                timeout=3,
            )
            raise
        return _TerminalRecord(info, process, master_fd, tmux_session=tmux_session)

    def _attach_tmux(
        self,
        tmux_session: str,
        root: Path,
        env: dict[str, str] | None = None,
    ) -> tuple[subprocess.Popen[bytes], int]:
        if not self._tmux:
            raise TerminalFailure("Persistent terminal support is unavailable.")
        attach_env = dict(env or {**os.environ, "TERM": "xterm-256color"})
        # Delta Loop itself is commonly started inside tmux on a server. The
        # client used for the browser terminal must not think it is nesting
        # inside that controlling session.
        attach_env.pop("TMUX", None)
        return self._spawn(
            [self._tmux, "attach-session", "-t", tmux_session],
            root,
            attach_env,
        )

    def _reattach(self, record: _TerminalRecord) -> None:
        if not record.tmux_session:
            return
        with record.lock:
            if record.process.poll() is None:
                return
            try:
                os.close(record.master_fd)
            except OSError:
                pass
            process, master_fd = self._attach_tmux(
                record.tmux_session,
                Path(record.info.working_directory),
            )
            self._wait_tmux_attached(record.tmux_session, process)
            record.process = process
            record.master_fd = master_fd
            record.input_attached = False
            record.info.status = "active"
        self._start_reader(record)

    def _tmux_alive(self, tmux_session: str) -> bool:
        if not self._tmux:
            return False
        try:
            checked = subprocess.run(
                [self._tmux, "has-session", "-t", tmux_session],
                capture_output=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return checked.returncode == 0

    def _configure_tmux(self, tmux_session: str) -> None:
        if not self._tmux:
            return
        for option, value in (
            ("history-limit", "50000"),
            ("mouse", "on"),
            ("status", "off"),
        ):
            subprocess.run(
                [self._tmux, "set-option", "-t", tmux_session, option, value],
                capture_output=True,
                check=False,
                timeout=3,
            )

    def _wait_tmux_attached(
        self,
        tmux_session: str,
        process: subprocess.Popen[bytes],
    ) -> None:
        if not self._tmux:
            return
        for _ in range(40):
            if process.poll() is not None:
                raise TerminalFailure("The persistent terminal could not be attached.")
            checked = subprocess.run(
                [
                    self._tmux,
                    "display-message",
                    "-p",
                    "-t",
                    tmux_session,
                    "#{session_attached}",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            if checked.returncode == 0 and checked.stdout.strip() not in {"", "0"}:
                return
            time.sleep(0.025)
        raise TerminalFailure("The persistent terminal did not become ready in time.")

    def _capture_tmux(self, tmux_session: str) -> bytes:
        if not self._tmux:
            return b""
        try:
            captured = subprocess.run(
                [self._tmux, "capture-pane", "-p", "-J", "-S", "-50000", "-t", tmux_session],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return b""
        if captured.returncode != 0:
            return b""
        return captured.stdout.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    def _restore(self) -> None:
        if not self._state_path or not self._tmux or not self._state_path.is_file():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in payload.get("sessions", []):
            tmux_session = str(item.get("tmux_session", ""))
            if not tmux_session or not self._tmux_alive(tmux_session):
                continue
            try:
                info = TerminalSessionInfo.model_validate(item["info"])
                root = Path(info.working_directory).expanduser().resolve()
                if not root.is_dir():
                    continue
                self._configure_tmux(tmux_session)
                process, master_fd = self._attach_tmux(tmux_session, root)
                self._wait_tmux_attached(tmux_session, process)
            except (KeyError, OSError, TerminalFailure, ValueError):
                continue
            info.status = "active"
            info.persistent = True
            record = _TerminalRecord(
                info,
                process,
                master_fd,
                tmux_session=tmux_session,
                replay=self._capture_tmux(tmux_session),
            )
            self._sessions[info.id] = record
            self._start_reader(record)

    def _save(self) -> None:
        if not self._state_path:
            return
        with self._lock:
            sessions = [
                {
                    "info": record.info.model_dump(mode="json"),
                    "tmux_session": record.tmux_session,
                }
                for record in self._sessions.values()
                if record.tmux_session and record.info.status == "active"
            ]
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"sessions": sessions}, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self._state_path)

    @staticmethod
    def _set_size(master_fd: int, columns: int, rows: int) -> None:
        size = struct.pack("HHHH", max(1, rows), max(1, columns), 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)

    @staticmethod
    def _get_size(master_fd: int) -> tuple[int, int]:
        packed = fcntl.ioctl(
            master_fd,
            termios.TIOCGWINSZ,
            struct.pack("HHHH", 0, 0, 0, 0),
        )
        rows, columns, _, _ = struct.unpack("HHHH", packed)
        return columns, rows
