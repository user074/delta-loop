from __future__ import annotations

import argparse
import json
import os
import select
import sys
import termios
import threading
import tty

from .importer import ImportFailure, import_workspace


def main() -> None:
    parser = argparse.ArgumentParser(prog="delta", description="Delta Loop local research cockpit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the local Delta Loop API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=4318, type=int)

    import_parser = subparsers.add_parser("import", help="Preview a delta-research workspace import")
    import_parser.add_argument("path")

    terminal_parser = subparsers.add_parser("terminal", help="Use a Delta Loop terminal")
    terminal_subparsers = terminal_parser.add_subparsers(dest="terminal_command", required=True)
    attach_parser = terminal_subparsers.add_parser("attach", help="Attach to a live terminal")
    attach_parser.add_argument("session_id")
    attach_parser.add_argument("--url", default="ws://127.0.0.1:4318")

    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("delta_loop.api:app", host=args.host, port=args.port, reload=False)
        return

    if args.command == "terminal":
        _attach_terminal(args.url, args.session_id)
        return

    try:
        snapshot = import_workspace(args.path)
    except ImportFailure as exc:
        parser.error(str(exc))
    print(json.dumps(snapshot.model_dump(mode="json"), indent=2))


def _attach_terminal(base_url: str, session_id: str) -> None:
    from websockets.sync.client import connect

    url = f"{base_url.rstrip('/')}/api/terminals/{session_id}/ws"
    old_settings = termios.tcgetattr(sys.stdin.fileno())
    finished = threading.Event()
    with connect(url) as websocket:
        print("Attached. Press Ctrl-] to return to your local shell.\r", file=sys.stderr)

        def receive() -> None:
            try:
                for message in websocket:
                    data = message if isinstance(message, bytes) else message.encode()
                    os.write(sys.stdout.fileno(), data)
            finally:
                finished.set()

        receiver = threading.Thread(target=receive, daemon=True)
        receiver.start()
        try:
            tty.setraw(sys.stdin.fileno())
            while not finished.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.2)
                if not ready:
                    continue
                data = os.read(sys.stdin.fileno(), 1024)
                if b"\x1d" in data:
                    break
                websocket.send(data)
        finally:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
