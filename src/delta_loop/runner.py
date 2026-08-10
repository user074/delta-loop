from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from .models import Attempt, now_iso
from .rules import render_rules
from .store import WorkspaceStore


class RunFailure(ValueError):
    pass


class AttemptRunner:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.RLock()

    def start(self, workspace_id: str, package_id: str) -> Attempt:
        workspace = self.store.get(workspace_id)
        if not workspace:
            raise RunFailure("Project not found.")
        package = next((item for item in workspace.packages if item.id == package_id), None)
        if not package:
            raise RunFailure("Plan not found.")
        if package.status != "ready":
            raise RunFailure("Approve the plan before running it.")
        active_runs = sum(
            attempt.status in {"starting", "running"} for attempt in workspace.attempts
        )
        if active_runs >= 2:
            raise RunFailure("Two plans are already running. Wait for one to finish or stop it first.")
        try:
            command = shlex.split(package.command)
        except ValueError as exc:
            raise RunFailure(f"The command cannot be read: {exc}") from exc
        if not command:
            raise RunFailure("Add the command that should be run.")

        attempt = Attempt(
            id=f"run-{uuid4().hex[:10]}",
            package_id=package.id,
            command=command,
            working_directory=workspace.root,
        )
        workspace.attempts.append(attempt)
        package.status = "running"
        self.store.save(workspace)
        thread = threading.Thread(
            target=self._run,
            args=(workspace_id, package_id, attempt.id),
            name=f"delta-loop-{attempt.id}",
            daemon=True,
        )
        thread.start()
        return attempt

    def _run(self, workspace_id: str, package_id: str, attempt_id: str) -> None:
        workspace = self.store.get(workspace_id)
        if not workspace:
            return
        attempt = next(item for item in workspace.attempts if item.id == attempt_id)
        package = next(item for item in workspace.packages if item.id == package_id)
        record_directory = self.store.path.parent / "runs" / attempt.id
        output_directory = record_directory / "output"
        output_directory.mkdir(parents=True, exist_ok=True)
        handoff_file = record_directory / "PLAN.md"
        rules_version = next(
            (version for version in workspace.rules_versions if version.id == package.rules_version_id),
            None,
        )
        handoff_file.write_text(
            self._render_handoff(workspace.goal, package, render_rules(rules_version) if rules_version else ""),
            encoding="utf-8",
        )
        attempt.record_directory = str(record_directory)
        attempt.handoff_file = str(handoff_file)
        attempt.output_directory = str(output_directory)
        command = [
            part.replace("{handoff}", str(handoff_file)).replace("{output_dir}", str(output_directory))
            for part in attempt.command
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=Path(attempt.working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
                env={
                    **os.environ,
                    "DELTA_LOOP_RUN_ID": attempt.id,
                    "DELTA_LOOP_PLAN_ID": package.id,
                    "DELTA_LOOP_HANDOFF": str(handoff_file),
                    "DELTA_LOOP_OUTPUT_DIR": str(output_directory),
                },
            )
        except OSError as exc:
            attempt.status = "failed"
            attempt.error = str(exc)
            attempt.finished_at = now_iso()
            package.status = "failed"
            self.store.save(workspace)
            return

        with self._lock:
            self._processes[attempt.id] = process
        attempt.pid = process.pid
        attempt.status = "running"
        self.store.save(workspace)

        assert process.stdout is not None
        pending = 0
        for line in process.stdout:
            attempt.output.append(line.rstrip("\n"))
            if len(attempt.output) > 2000:
                attempt.output = attempt.output[-2000:]
            pending += 1
            if pending >= 10:
                self.store.save(workspace)
                pending = 0

        exit_code = process.wait()
        with self._lock:
            self._processes.pop(attempt.id, None)
        attempt.exit_code = exit_code
        attempt.finished_at = now_iso()
        if attempt.status == "cancelled":
            package.status = "cancelled"
        elif exit_code == 0:
            attempt.status = "finished"
            package.status = "finished"
        else:
            attempt.status = "failed"
            package.status = "failed"
        self.store.save(workspace)

    @staticmethod
    def _render_handoff(main_question: str, package, rules_text: str) -> str:
        sections = [
            "# Approved plan",
            f"## Main question\n{main_question}",
            f"## What this work should learn\n{package.goal}",
            f"## Why now\n{package.why_now or 'Not stated.'}",
            f"## What to do\n{package.instructions}",
            f"## Files, data, models, and code\n{package.inputs or 'Use only what the plan requires.'}",
            f"## Fair comparison\n{package.comparison or 'Not stated.'}",
            f"## What to measure\n{package.measure}",
            f"## Expected results\n{package.expected or 'Not stated.'}",
            f"## What this test cannot show\n{package.limits or 'Not stated.'}",
            f"## Do not change\n{package.do_not_change or 'Do not change the main question or measurement.'}",
            f"## Work limit\n{package.budget}",
        ]
        if rules_text:
            sections.append(f"## Rules for the agent\n{rules_text}")
        sections.append(
            "## Finish by\nSave useful files under the DELTA_LOOP_OUTPUT_DIR folder and print a short summary."
        )
        return "\n\n".join(sections) + "\n"

    def cancel(self, workspace_id: str, attempt_id: str) -> Attempt:
        workspace = self.store.get(workspace_id)
        if not workspace:
            raise RunFailure("Project not found.")
        attempt = next((item for item in workspace.attempts if item.id == attempt_id), None)
        if not attempt:
            raise RunFailure("Run not found.")
        with self._lock:
            process = self._processes.get(attempt.id)
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        attempt.status = "cancelled"
        attempt.finished_at = now_iso()
        package = next((item for item in workspace.packages if item.id == attempt.package_id), None)
        if package:
            package.status = "cancelled"
        self.store.save(workspace)
        return attempt
