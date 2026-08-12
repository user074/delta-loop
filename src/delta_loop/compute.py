from __future__ import annotations

import base64
import os
import platform
import re
import shlex
import socket
import subprocess
from pathlib import Path

from .models import (
    ComputeCheckResult,
    ComputeConfig,
    ComputeInspection,
    RemoteProjectInspection,
)


class ComputeFailure(ValueError):
    pass


SSH_OPTIONS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
]


def validate_compute(config: ComputeConfig) -> None:
    for label, value in {
        "name": config.name,
        "SSH host": config.ssh_host,
        "project path": config.project_path,
        "run path": config.run_path,
        "setup command": config.setup_command,
        "GPU devices": config.gpu_devices,
    }.items():
        if any(character in value for character in ("\0", "\n", "\r")):
            raise ComputeFailure(f"{label.capitalize()} cannot contain a line break.")
    if config.kind == "ssh":
        if not config.ssh_host.strip():
            raise ComputeFailure("Write the SSH host or alias first.")
        if config.ssh_host.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.:@%+\-]+", config.ssh_host):
            raise ComputeFailure("The SSH host must be a host name, SSH alias, or user@host without spaces.")
        if not config.project_path.strip():
            raise ComputeFailure("Write the project path on the remote server first.")
        if not config.run_path.strip():
            raise ComputeFailure("Write the run-record path on the remote server first.")


def ssh_command(host: str, remote_command: str) -> list[str]:
    executable = shlex.split(os.environ.get("DELTA_LOOP_SSH_COMMAND", "ssh"))
    return [*executable, *SSH_OPTIONS, host, remote_command]


def run_ssh(
    host: str,
    remote_command: str,
    *,
    input_text: str | None = None,
    timeout: float = 15,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ssh_command(host, remote_command),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ComputeFailure(f"Could not reach {host}: {exc}") from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"SSH exited with {completed.returncode}."
        raise ComputeFailure(f"Could not use {host}: {detail[-600:]}")
    return completed


def _remote_command(script: str, *arguments: str) -> str:
    return "sh -c " + shlex.quote(script) + " sh " + " ".join(shlex.quote(item) for item in arguments)


def check_compute(config: ComputeConfig, local_root: str) -> ComputeCheckResult:
    validate_compute(config)
    if config.kind == "local":
        root = Path(local_root).expanduser().resolve()
        return ComputeCheckResult(
            status="ready" if root.is_dir() else "needs-setup",
            message="This computer is ready to run work." if root.is_dir() else "The local project folder is missing.",
            project_path=str(root),
            run_path="Managed inside Delta Loop's local data folder.",
            project_exists=root.is_dir(),
            run_path_exists=True,
            python=str(Path(os.sys.executable).resolve()),
            git=_local_command_path("git"),
            gpus=_local_gpus(),
        )

    script = r'''
project=$1
runs=$2
setup=$3
case "$project" in '~/'*) project="$HOME/${project#'~/'}" ;; esac
case "$runs" in '~/'*) runs="$HOME/${runs#'~/'}" ;; esac
printf 'project_path\t%s\n' "$project"
printf 'run_path\t%s\n' "$runs"
if [ -d "$project" ]; then printf 'project_exists\t1\n'; else printf 'project_exists\t0\n'; fi
if [ -d "$runs" ]; then printf 'run_path_exists\t1\n'; else printf 'run_path_exists\t0\n'; fi
runner_shell=$(command -v bash 2>/dev/null || command -v sh 2>/dev/null || true)
if [ -n "$setup" ]; then
  python_path=$("$runner_shell" -c 'cd "$1" && eval "$2" >/dev/null 2>&1 && (command -v python3 2>/dev/null || command -v python 2>/dev/null)' runner "$project" "$setup")
  if [ $? -ne 0 ]; then printf 'setup_failed\t1\n'; fi
else
  python_path=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
fi
printf 'python\t%s\n' "$python_path"
printf 'git\t%s\n' "$(command -v git 2>/dev/null || true)"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/gpu\t/' || true
fi
'''
    try:
        completed = run_ssh(
            config.ssh_host,
            _remote_command(
                script,
                config.project_path,
                config.run_path,
                config.setup_command,
            ),
            timeout=12,
        )
    except ComputeFailure as exc:
        return ComputeCheckResult(
            status="unreachable",
            message=str(exc),
            host=config.ssh_host,
            project_path=config.project_path,
            run_path=config.run_path,
        )
    values: dict[str, list[str]] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            values.setdefault(key, []).append(value)
    project_exists = values.get("project_exists", ["0"])[0] == "1"
    python = values.get("python", [""])[0]
    setup_failed = values.get("setup_failed", ["0"])[0] == "1"
    status = "ready" if project_exists and python and not setup_failed else "needs-setup"
    missing = []
    if not project_exists:
        missing.append("the remote project folder")
    if not python:
        missing.append("Python")
    if setup_failed:
        missing.append("the saved environment setup command")
    return ComputeCheckResult(
        status=status,
        message=(
            f"Connected to {config.ssh_host}; the remote project is ready."
            if status == "ready"
            else f"Connected to {config.ssh_host}, but could not find {' and '.join(missing)}."
        ),
        host=config.ssh_host,
        project_path=values.get("project_path", [config.project_path])[0],
        run_path=values.get("run_path", [config.run_path])[0],
        project_exists=project_exists,
        run_path_exists=values.get("run_path_exists", ["0"])[0] == "1",
        python=python,
        git=values.get("git", [""])[0],
        gpus=values.get("gpu", []),
    )


def inspect_remote_compute(
    host: str,
    project_path: str,
    run_path: str = "~/.delta-loop/runs",
) -> ComputeInspection:
    transient = ComputeConfig(
        kind="ssh",
        name=host,
        ssh_host=host,
        project_path=project_path,
        run_path=run_path,
    )
    validate_compute(transient)
    script = r'''
project=$1
runs=$2
case "$project" in '~/'*) project="$HOME/${project#'~/'}" ;; esac
case "$runs" in '~/'*) runs="$HOME/${runs#'~/'}" ;; esac
emit() { printf '%s\t%s\n' "$1" "$2"; }
emit hostname "$(hostname 2>/dev/null || true)"
emit os "$(uname -srm 2>/dev/null || true)"
emit shell "${SHELL:-}"
emit home "$HOME"
emit project_path "$project"
emit run_path "$runs"
if [ -d "$project" ]; then
  emit project_exists 1
  [ -w "$project" ] && emit project_writable 1 || emit project_writable 0
  for item in "$project"/* "$project"/.[!.]*; do
    [ -e "$item" ] || continue
    emit top_file "$(basename "$item")"
  done | head -80
else
  emit project_exists 0
  emit project_writable 0
fi
parent=$runs
while [ ! -d "$parent" ] && [ "$parent" != / ]; do parent=$(dirname "$parent"); done
[ -w "$parent" ] && emit run_parent_writable 1 || emit run_parent_writable 0
for file in pyproject.toml uv.lock poetry.lock pixi.toml pixi.lock environment.yml environment.yaml requirements.txt conda-lock.yml; do
  [ -f "$project/$file" ] && emit dependency_file "$file"
done
[ -f "$project/README.md" ] && emit has_readme 1 || emit has_readme 0
[ -f "$project/STATE.md" ] && emit has_state 1 || emit has_state 0
[ -f "$project/INFRA.md" ] && emit has_infra 1 || emit has_infra 0
python_path=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
emit python_path "$python_path"
if [ -n "$python_path" ]; then emit python_version "$($python_path --version 2>&1 | head -1)"; fi
for tool in conda mamba uv pixi poetry; do
  path=$(command -v "$tool" 2>/dev/null || true)
  [ -n "$path" ] && emit environment_tool "$tool: $path"
done
[ -n "${CONDA_PREFIX:-}" ] && emit environment_candidate "active conda environment: $CONDA_PREFIX"
[ -n "${VIRTUAL_ENV:-}" ] && emit environment_candidate "active virtual environment: $VIRTUAL_ENV"
[ -f "$project/.venv/bin/activate" ] && emit environment_candidate "project venv: $project/.venv/bin/activate"
[ -f "$project/venv/bin/activate" ] && emit environment_candidate "project venv: $project/venv/bin/activate"
[ -f "$project/pixi.toml" ] && emit environment_candidate "pixi project: $project/pixi.toml"
[ -f "$project/uv.lock" ] && emit environment_candidate "uv project: $project/uv.lock"
scheduler=none
for tool in squeue sbatch sinfo qsub bsub; do
  path=$(command -v "$tool" 2>/dev/null || true)
  if [ -n "$path" ]; then
    emit scheduler_tool "$tool: $path"
    case "$tool" in squeue|sbatch|sinfo) scheduler=slurm ;; qsub) [ "$scheduler" = none ] && scheduler=pbs ;; bsub) [ "$scheduler" = none ] && scheduler=lsf ;; esac
  fi
done
emit scheduler "$scheduler"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader 2>/dev/null | sed 's/^/gpu\t/' || true
fi
if command -v nproc >/dev/null 2>&1; then
  emit cpu "$(nproc) logical cores"
elif command -v sysctl >/dev/null 2>&1; then
  emit cpu "$(sysctl -n hw.ncpu 2>/dev/null || true) logical cores"
fi
if command -v free >/dev/null 2>&1; then
  emit memory "$(free -h 2>/dev/null | awk '/^Mem:/ {print $2 " total, " $7 " available"}')"
fi
[ -d "$project" ] && emit project_storage "$(df -hP "$project" 2>/dev/null | tail -1 | tr -s ' ')"
emit home_storage "$(df -hP "$HOME" 2>/dev/null | tail -1 | tr -s ' ')"
if [ -d "$project/.git" ] || git -C "$project" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  emit git_branch "$(git -C "$project" branch --show-current 2>/dev/null || true)"
  emit git_remote "$(git -C "$project" remote get-url origin 2>/dev/null || true)"
  changes=$(git -C "$project" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$changes" = 0 ] && emit git_status clean || emit git_status "$changes changed paths"
fi
'''
    completed = run_ssh(
        host,
        _remote_command(script, project_path, run_path),
        timeout=20,
    )
    values: dict[str, list[str]] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            values.setdefault(key, []).append(value)

    def one(key: str, default: str = "") -> str:
        return values.get(key, [default])[0]

    has_infra = one("has_infra") == "1"
    scheduler = one("scheduler", "none")
    notes = []
    if has_infra:
        notes.append("An existing INFRA.md was found. Review it before proposing different settings.")
    else:
        notes.append("No INFRA.md was found. Detected facts still need the researcher's rules and preferences.")
    if scheduler == "none":
        notes.append("No scheduler commands were found. Direct SSH execution is the likely mode.")
    else:
        notes.append(
            f"A {scheduler.upper()} scheduler appears to be present. Do not run heavy work on the login node."
        )
    if not values.get("gpu"):
        notes.append("No GPU was visible from this SSH session; this may be normal on a login node.")
    return ComputeInspection(
        host=host,
        hostname=one("hostname"),
        operating_system=one("os"),
        shell=one("shell"),
        home_path=one("home"),
        project_path=one("project_path", project_path),
        project_exists=one("project_exists") == "1",
        project_writable=one("project_writable") == "1",
        run_path=one("run_path", run_path),
        run_parent_writable=one("run_parent_writable") == "1",
        top_level_files=values.get("top_file", []),
        has_readme=one("has_readme") == "1",
        has_state=one("has_state") == "1",
        has_infra=has_infra,
        dependency_files=values.get("dependency_file", []),
        python_path=one("python_path"),
        python_version=one("python_version"),
        environment_tools=values.get("environment_tool", []),
        environment_candidates=values.get("environment_candidate", []),
        scheduler=scheduler,
        scheduler_tools=values.get("scheduler_tool", []),
        gpus=values.get("gpu", []),
        cpu=one("cpu"),
        memory=one("memory"),
        project_storage=one("project_storage"),
        home_storage=one("home_storage"),
        git_branch=one("git_branch"),
        git_remote=one("git_remote"),
        git_status=one("git_status"),
        notes=notes,
    )


def inspect_remote_project(host: str, project_path: str) -> RemoteProjectInspection:
    """Read a small, explicit set of files needed to understand a remote project."""
    transient = ComputeConfig(
        kind="ssh",
        name=host,
        ssh_host=host,
        project_path=project_path,
    )
    validate_compute(transient)
    script = r'''
project=$1
case "$project" in '~/'*) project="$HOME/${project#'~/'}" ;; esac
emit() { printf '%s\t%s\n' "$1" "$2"; }
emit project_path "$project"
if [ ! -d "$project" ]; then
  emit project_exists 0
  exit 0
fi
emit project_exists 1
find "$project" -maxdepth 2 -type f \
  ! -path '*/.git/*' ! -path '*/.venv/*' ! -path '*/venv/*' \
  ! -path '*/node_modules/*' ! -path '*/.cache/*' ! -path '*/__pycache__/*' \
  ! -name '.env' ! -name '*.key' ! -name '*.pem' \
  -print 2>/dev/null | sed "s#^$project/##" | head -80 | while IFS= read -r file; do
    emit top_file "$file"
  done
for file in README.md AGENTS.md CLAUDE.md INFRA.md pyproject.toml package.json requirements.txt environment.yml environment.yaml Makefile; do
  [ -f "$project/$file" ] || continue
  content=$(head -c 4000 "$project/$file" 2>/dev/null | base64 | tr -d '\n' | cut -c1-5336)
  printf 'document\t%s\t%s\n' "$file" "$content"
done
if git -C "$project" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  emit git_branch "$(git -C "$project" branch --show-current 2>/dev/null || true)"
  emit git_remote "$(git -C "$project" remote get-url origin 2>/dev/null || true)"
  git -C "$project" status --short 2>/dev/null | head -60 | while IFS= read -r line; do emit git_status "$line"; done
  git -C "$project" log -5 --pretty=format:'%h %s' 2>/dev/null | while IFS= read -r line; do emit recent_commit "$line"; done
fi
'''
    completed = run_ssh(
        host,
        _remote_command(script, project_path),
        timeout=20,
    )
    values: dict[str, list[str]] = {}
    documentation: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, rest = line.partition("\t")
        if not separator:
            continue
        if key == "document":
            name, document_separator, encoded = rest.partition("\t")
            if not document_separator:
                continue
            try:
                documentation[name] = base64.b64decode(encoded).decode("utf-8", errors="replace")
            except ValueError:
                documentation[name] = "[The file could not be decoded.]"
            continue
        values.setdefault(key, []).append(rest)

    def one(key: str, default: str = "") -> str:
        return values.get(key, [default])[0]

    return RemoteProjectInspection(
        host=host,
        project_path=one("project_path", project_path),
        project_exists=one("project_exists") == "1",
        top_level_files=values.get("top_file", []),
        documentation=documentation,
        git_branch=one("git_branch"),
        git_remote=one("git_remote"),
        git_status=values.get("git_status", []),
        recent_commits=values.get("recent_commit", []),
    )


def inspect_local_compute(project_path: str, run_path: str) -> ComputeInspection:
    project = Path(project_path).expanduser().resolve()
    runs = Path(run_path).expanduser().resolve()
    dependency_names = [
        "pyproject.toml",
        "uv.lock",
        "poetry.lock",
        "pixi.toml",
        "pixi.lock",
        "environment.yml",
        "environment.yaml",
        "requirements.txt",
        "conda-lock.yml",
    ]
    environment_tools = [
        f"{tool}: {path}"
        for tool in ("conda", "mamba", "uv", "pixi", "poetry")
        if (path := _local_command_path(tool))
    ]
    candidates = []
    if os.environ.get("CONDA_PREFIX"):
        candidates.append(f"active conda environment: {os.environ['CONDA_PREFIX']}")
    if os.environ.get("VIRTUAL_ENV"):
        candidates.append(f"active virtual environment: {os.environ['VIRTUAL_ENV']}")
    for directory in (".venv", "venv"):
        activate = project / directory / "bin" / "activate"
        if activate.is_file():
            candidates.append(f"project venv: {activate}")
    if (project / "pixi.toml").is_file():
        candidates.append(f"pixi project: {project / 'pixi.toml'}")
    if (project / "uv.lock").is_file():
        candidates.append(f"uv project: {project / 'uv.lock'}")

    scheduler_tools = []
    scheduler = "none"
    for tool in ("squeue", "sbatch", "sinfo", "qsub", "bsub"):
        path = _local_command_path(tool)
        if not path:
            continue
        scheduler_tools.append(f"{tool}: {path}")
        if tool in {"squeue", "sbatch", "sinfo"}:
            scheduler = "slurm"
        elif tool == "qsub" and scheduler == "none":
            scheduler = "pbs"
        elif tool == "bsub" and scheduler == "none":
            scheduler = "lsf"

    parent = runs
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    git_branch = _local_output(["git", "-C", str(project), "branch", "--show-current"])
    git_remote = _local_output(["git", "-C", str(project), "remote", "get-url", "origin"])
    git_lines = _local_output(["git", "-C", str(project), "status", "--porcelain"]).splitlines()
    notes = [
        (
            "An existing INFRA.md was found. Review it before proposing different settings."
            if (project / "INFRA.md").is_file()
            else "No INFRA.md was found. Detected facts still need the researcher's rules and preferences."
        )
    ]
    if scheduler == "none":
        notes.append("No scheduler commands were found. Direct local execution is the likely mode.")
    if not _local_gpus():
        notes.append("No NVIDIA GPU was visible from this process.")
    return ComputeInspection(
        host="this-computer",
        hostname=socket.gethostname(),
        operating_system=platform.platform(),
        shell=os.environ.get("SHELL", ""),
        home_path=str(Path.home()),
        project_path=str(project),
        project_exists=project.is_dir(),
        project_writable=os.access(project, os.W_OK),
        run_path=str(runs),
        run_parent_writable=parent.is_dir() and os.access(parent, os.W_OK),
        top_level_files=(
            sorted(item.name for item in project.iterdir())[:80]
            if project.is_dir()
            else []
        ),
        has_readme=(project / "README.md").is_file(),
        has_state=(project / "STATE.md").is_file(),
        has_infra=(project / "INFRA.md").is_file(),
        dependency_files=[
            name for name in dependency_names if (project / name).is_file()
        ],
        python_path=str(Path(os.sys.executable).resolve()),
        python_version=platform.python_version(),
        environment_tools=environment_tools,
        environment_candidates=candidates,
        scheduler=scheduler,
        scheduler_tools=scheduler_tools,
        gpus=_local_gpus(),
        cpu=f"{os.cpu_count() or 0} logical cores",
        memory=_local_memory(),
        project_storage=_local_df(project),
        home_storage=_local_df(Path.home()),
        git_branch=git_branch,
        git_remote=git_remote,
        git_status="clean" if not git_lines else f"{len(git_lines)} changed paths",
        notes=notes,
    )


def remote_shell_command(script: str, *arguments: str) -> str:
    return _remote_command(script, *arguments)


def _local_command_path(command: str) -> str:
    from shutil import which

    return which(command) or ""


def _local_gpus() -> list[str]:
    executable = _local_command_path("nvidia-smi")
    if not executable:
        return []
    completed = subprocess.run(
        [executable, "--query-gpu=index,name,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return completed.stdout.splitlines() if completed.returncode == 0 else []


def _local_output(command: list[str]) -> str:
    if not command or not _local_command_path(command[0]):
        return ""
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _local_memory() -> str:
    if platform.system() == "Darwin":
        raw = _local_output(["sysctl", "-n", "hw.memsize"])
        if raw.isdigit():
            return f"{int(raw) / (1024 ** 3):.0f} GB total"
    raw = _local_output(["free", "-h"])
    for line in raw.splitlines():
        if line.startswith("Mem:"):
            values = line.split()
            if len(values) >= 7:
                return f"{values[1]} total, {values[6]} available"
    return ""


def _local_df(path: Path) -> str:
    output = _local_output(["df", "-hP", str(path)])
    return output.splitlines()[-1] if output else ""
