from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from .compute import ComputeFailure, remote_shell_command, run_ssh
from .models import Attempt, ComputeConfig, now_iso
from .rules import render_rules
from .store import WorkspaceStore


class RunFailure(ValueError):
    pass


TERMINAL_STATUSES = {"finished", "failed", "cancelled"}


class AttemptRunner:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._last_refresh: dict[str, float] = {}
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
        compute = workspace.compute
        if not compute.configured:
            raise RunFailure("Set up where research work runs on the Compute page first.")
        if compute.kind == "ssh" and compute.status != "ready":
            raise RunFailure("Check the remote connection on the Compute page before starting work.")
        active_runs = sum(
            attempt.status in {"starting", "running"} for attempt in workspace.attempts
        )
        if active_runs >= compute.max_parallel:
            noun = "plan is" if compute.max_parallel == 1 else "plans are"
            raise RunFailure(
                f"{compute.max_parallel} {noun} already running. Wait for one to finish or stop it first."
            )
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
            working_directory=workspace.root if compute.kind == "local" else compute.project_path,
            executor=compute.kind,
            compute_name=compute.name
            or ("This computer" if compute.kind == "local" else compute.ssh_host),
            remote_host=compute.ssh_host if compute.kind == "ssh" else "",
        )
        workspace.attempts.append(attempt)
        package.status = "running"
        self.store.save(workspace)
        target = self._run_local if compute.kind == "local" else self._run_remote
        threading.Thread(
            target=target,
            args=(workspace_id, package_id, attempt.id, compute.model_copy(deep=True)),
            name=f"delta-loop-{attempt.id}",
            daemon=True,
        ).start()
        return attempt

    def refresh(self, workspace_id: str, *, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_refresh.get(workspace_id, 0) < 4:
                return
            self._last_refresh[workspace_id] = now
        workspace = self.store.get(workspace_id)
        if not workspace:
            return
        changed = False
        for attempt in workspace.attempts:
            if attempt.executor == "ssh" and attempt.status in {"starting", "running"}:
                changed = self._refresh_remote_attempt(workspace, attempt) or changed
        if changed:
            self.store.save(workspace)

    def _prepare_record(self, workspace, package, attempt: Attempt) -> tuple[Path, Path, Path]:
        record_directory = self.store.path.parent / "runs" / attempt.id
        output_directory = record_directory / "output"
        output_directory.mkdir(parents=True, exist_ok=True)
        handoff_file = record_directory / "PLAN.md"
        rules_version = next(
            (
                version
                for version in workspace.rules_versions
                if version.id == package.rules_version_id
            ),
            None,
        )
        handoff_file.write_text(
            self._render_handoff(
                workspace.goal,
                package,
                render_rules(rules_version) if rules_version else "",
            ),
            encoding="utf-8",
        )
        attempt.record_directory = str(record_directory)
        attempt.handoff_file = str(handoff_file)
        attempt.output_directory = str(output_directory)
        self.store.save(workspace)
        return record_directory, output_directory, handoff_file

    def _run_local(
        self,
        workspace_id: str,
        package_id: str,
        attempt_id: str,
        compute: ComputeConfig,
    ) -> None:
        workspace = self.store.get(workspace_id)
        if not workspace:
            return
        attempt = next(item for item in workspace.attempts if item.id == attempt_id)
        package = next(item for item in workspace.packages if item.id == package_id)
        _, output_directory, handoff_file = self._prepare_record(workspace, package, attempt)
        command = [
            part.replace("{handoff}", str(handoff_file)).replace(
                "{output_dir}", str(output_directory)
            )
            for part in attempt.command
        ]
        environment = {
            **os.environ,
            "DELTA_LOOP_RUN_ID": attempt.id,
            "DELTA_LOOP_PLAN_ID": package.id,
            "DELTA_LOOP_HANDOFF": str(handoff_file),
            "DELTA_LOOP_OUTPUT_DIR": str(output_directory),
        }
        if compute.gpu_devices.strip():
            environment["CUDA_VISIBLE_DEVICES"] = compute.gpu_devices.strip()
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
                env=environment,
            )
        except OSError as exc:
            self._finish_failed(workspace, package, attempt, str(exc))
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

    def _run_remote(
        self,
        workspace_id: str,
        package_id: str,
        attempt_id: str,
        compute: ComputeConfig,
    ) -> None:
        workspace = self.store.get(workspace_id)
        if not workspace:
            return
        attempt = next(item for item in workspace.attempts if item.id == attempt_id)
        package = next(item for item in workspace.packages if item.id == package_id)
        _, _, handoff_file = self._prepare_record(workspace, package, attempt)
        remote_record = f"{compute.run_path.rstrip('/')}/{attempt.id}"
        remote_output = f"{remote_record}/output"
        attempt.remote_record_directory = remote_record
        attempt.remote_output_directory = remote_output
        self.store.save(workspace)
        remote_handoff = f"{remote_record}/PLAN.md"
        remote_script = f"{remote_record}/run.sh"
        command_line = " ".join(
            self._quote_remote_argument(part) for part in attempt.command
        )
        try:
            self._write_remote_file(
                compute.ssh_host,
                remote_record,
                remote_handoff,
                handoff_file.read_text(encoding="utf-8"),
            )
            self._write_remote_file(
                compute.ssh_host,
                remote_record,
                remote_script,
                self._remote_run_script(),
                executable=True,
            )
            launch_script = r'''
run_dir=$1
project=$2
setup=$3
gpus=$4
command=$5
plan_id=$6
case "$run_dir" in '~/'*) run_dir="$HOME/${run_dir#'~/'}" ;; esac
case "$project" in '~/'*) project="$HOME/${project#'~/'}" ;; esac
mkdir -p "$run_dir/output"
if command -v setsid >/dev/null 2>&1; then
  runner_shell=$(command -v bash 2>/dev/null || command -v sh)
  nohup setsid "$runner_shell" "$run_dir/run.sh" "$run_dir" "$project" "$setup" "$gpus" "$command" "$plan_id" </dev/null >"$run_dir/run.log" 2>&1 &
else
  runner_shell=$(command -v bash 2>/dev/null || command -v sh)
  nohup "$runner_shell" "$run_dir/run.sh" "$run_dir" "$project" "$setup" "$gpus" "$command" "$plan_id" </dev/null >"$run_dir/run.log" 2>&1 &
fi
pid=$!
printf '%s\n' "$pid" >"$run_dir/pid"
printf '%s\n' "$pid"
'''
            completed = run_ssh(
                compute.ssh_host,
                remote_shell_command(
                    launch_script,
                    remote_record,
                    compute.project_path,
                    compute.setup_command,
                    compute.gpu_devices,
                    command_line,
                    package.id,
                ),
                timeout=20,
            )
            attempt.pid = int(completed.stdout.strip().splitlines()[-1])
            attempt.status = "running"
            attempt.last_checked_at = now_iso()
            self.store.save(workspace)
        except (ComputeFailure, OSError, ValueError) as exc:
            self._finish_failed(workspace, package, attempt, str(exc))
            return
        while attempt.status not in TERMINAL_STATUSES:
            time.sleep(2)
            current = self.store.get(workspace_id)
            if not current:
                return
            attempt = next(
                (item for item in current.attempts if item.id == attempt_id), attempt
            )
            if attempt.status in TERMINAL_STATUSES:
                return
            self._refresh_remote_attempt(current, attempt)
            self.store.save(current)

    @staticmethod
    def _write_remote_file(
        host: str,
        remote_record: str,
        remote_file: str,
        contents: str,
        *,
        executable: bool = False,
    ) -> None:
        script = r'''
run_dir=$1
target=$2
case "$run_dir" in '~/'*) run_dir="$HOME/${run_dir#'~/'}" ;; esac
case "$target" in '~/'*) target="$HOME/${target#'~/'}" ;; esac
mkdir -p "$run_dir/output"
cat >"$target"
if [ "$3" = 1 ]; then chmod 700 "$target"; fi
'''
        run_ssh(
            host,
            remote_shell_command(
                script, remote_record, remote_file, "1" if executable else "0"
            ),
            input_text=contents,
            timeout=20,
        )

    @staticmethod
    def _remote_run_script() -> str:
        return r'''#!/bin/sh
run_dir=$1
project=$2
setup=$3
gpus=$4
command=$5
plan_id=$6
case "$run_dir" in '~/'*) run_dir="$HOME/${run_dir#'~/'}" ;; esac
case "$project" in '~/'*) project="$HOME/${project#'~/'}" ;; esac
status_file="$run_dir/status"
printf 'running\n' >"$status_file"
printf '%s\n' "$$" >"$run_dir/worker-pid"
finish() {
  code=$?
  printf '%s\n' "$code" >"$run_dir/exit-code"
  date -u '+%Y-%m-%dT%H:%M:%SZ' >"$run_dir/finished-at"
  if [ -f "$run_dir/cancelled" ]; then
    printf 'cancelled\n' >"$status_file"
  elif [ "$code" -eq 0 ]; then
    printf 'finished\n' >"$status_file"
  else
    printf 'failed\n' >"$status_file"
  fi
}
trap finish EXIT
trap 'exit 143' TERM INT
cd "$project"
export DELTA_LOOP_RUN_ID="$(basename "$run_dir")"
export DELTA_LOOP_PLAN_ID="$plan_id"
export DELTA_LOOP_HANDOFF="$run_dir/PLAN.md"
export DELTA_LOOP_OUTPUT_DIR="$run_dir/output"
if [ -n "$gpus" ]; then export CUDA_VISIBLE_DEVICES="$gpus"; fi
if [ -n "$setup" ]; then eval "$setup"; fi
eval "$command"
'''

    @staticmethod
    def _quote_remote_argument(value: str) -> str:
        handoff_marker = "__DELTA_LOOP_HANDOFF_VALUE__"
        output_marker = "__DELTA_LOOP_OUTPUT_VALUE__"
        marked = value.replace("{handoff}", handoff_marker).replace(
            "{output_dir}", output_marker
        )
        escaped = (
            marked.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
            .replace("`", "\\`")
        )
        escaped = escaped.replace(
            handoff_marker, "${DELTA_LOOP_HANDOFF}"
        ).replace(output_marker, "${DELTA_LOOP_OUTPUT_DIR}")
        return f'"{escaped}"'

    def _refresh_remote_attempt(self, workspace, attempt: Attempt) -> bool:
        if not attempt.remote_host or not attempt.remote_record_directory:
            return False
        script = r'''
run_dir=$1
case "$run_dir" in '~/'*) run_dir="$HOME/${run_dir#'~/'}" ;; esac
status=$(cat "$run_dir/status" 2>/dev/null || printf 'starting')
pid=$(cat "$run_dir/worker-pid" 2>/dev/null || cat "$run_dir/pid" 2>/dev/null || true)
exit_code=$(cat "$run_dir/exit-code" 2>/dev/null || true)
finished=$(cat "$run_dir/finished-at" 2>/dev/null || true)
printf '@status\t%s\n' "$status"
printf '@pid\t%s\n' "$pid"
printf '@exit\t%s\n' "$exit_code"
printf '@finished\t%s\n' "$finished"
printf '@log\n'
tail -n 2000 "$run_dir/run.log" 2>/dev/null || true
'''
        try:
            completed = run_ssh(
                attempt.remote_host,
                remote_shell_command(script, attempt.remote_record_directory),
                timeout=12,
            )
        except ComputeFailure as exc:
            message = str(exc)
            changed = attempt.error != message
            attempt.error = message
            attempt.last_checked_at = now_iso()
            return changed
        metadata: dict[str, str] = {}
        log: list[str] = []
        reading_log = False
        for line in completed.stdout.splitlines():
            if line == "@log":
                reading_log = True
            elif reading_log:
                log.append(line)
            elif line.startswith("@"):
                key, _, value = line[1:].partition("\t")
                metadata[key] = value
        previous = (
            attempt.status,
            attempt.pid,
            attempt.exit_code,
            attempt.finished_at,
            attempt.output,
            attempt.error,
        )
        status = metadata.get("status", "starting")
        if status in {"starting", "running"} | TERMINAL_STATUSES:
            attempt.status = status
        if metadata.get("pid", "").isdigit():
            attempt.pid = int(metadata["pid"])
        if metadata.get("exit", "").lstrip("-").isdigit():
            attempt.exit_code = int(metadata["exit"])
        if metadata.get("finished"):
            attempt.finished_at = metadata["finished"]
        attempt.output = log
        attempt.error = ""
        attempt.last_checked_at = now_iso()
        package = next(
            (item for item in workspace.packages if item.id == attempt.package_id), None
        )
        if package and attempt.status in TERMINAL_STATUSES:
            package.status = attempt.status
        current = (
            attempt.status,
            attempt.pid,
            attempt.exit_code,
            attempt.finished_at,
            attempt.output,
            attempt.error,
        )
        return current != previous

    def _finish_failed(self, workspace, package, attempt: Attempt, message: str) -> None:
        attempt.status = "failed"
        attempt.error = message
        attempt.finished_at = now_iso()
        package.status = "failed"
        self.store.save(workspace)

    @staticmethod
    def _render_handoff(main_question: str, package, rules_text: str) -> str:
        sections = [
            "# Approved plan",
            f"## Main question\n{main_question}",
            f"## What this work should learn\n{package.goal}",
            f"## Type of work\n{package.work_kind.replace('-', ' ')}",
            f"## Why now\n{package.why_now or 'Not stated.'}",
            f"## Guidance for this idea\n{package.idea_guidance or 'Follow the approved steps below.'}",
            f"## Stop and ask before\n{package.ask_before or 'Ask before changing the question, data, main comparison, or measurement.'}",
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
        if attempt.executor == "ssh":
            self._cancel_remote(attempt)
        else:
            with self._lock:
                process = self._processes.get(attempt.id)
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        attempt.status = "cancelled"
        attempt.finished_at = now_iso()
        package = next(
            (item for item in workspace.packages if item.id == attempt.package_id), None
        )
        if package:
            package.status = "cancelled"
        self.store.save(workspace)
        return attempt

    @staticmethod
    def _cancel_remote(attempt: Attempt) -> None:
        if not attempt.remote_host or not attempt.remote_record_directory:
            raise RunFailure("This run does not have enough remote connection information.")
        script = r'''
run_dir=$1
case "$run_dir" in '~/'*) run_dir="$HOME/${run_dir#'~/'}" ;; esac
touch "$run_dir/cancelled"
pid=$(cat "$run_dir/worker-pid" 2>/dev/null || cat "$run_dir/pid" 2>/dev/null || true)
if [ -n "$pid" ]; then
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
fi
printf 'cancelled\n' >"$run_dir/status"
date -u '+%Y-%m-%dT%H:%M:%SZ' >"$run_dir/finished-at"
'''
        try:
            run_ssh(
                attempt.remote_host,
                remote_shell_command(script, attempt.remote_record_directory),
                timeout=12,
            )
        except ComputeFailure as exc:
            raise RunFailure(str(exc)) from exc
