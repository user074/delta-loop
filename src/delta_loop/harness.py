from __future__ import annotations

import os
from pathlib import Path
import subprocess

from .models import HarnessInfo


OFFICIAL_REPOSITORY = "https://github.com/user074/delta-research.git"
REQUIRED_FILES = (
    Path("templates") / "SUPERVISOR.md",
    Path("templates") / "INIT.md",
    Path("templates") / "PLAN.template.md",
    Path("templates") / "STATE.template.md",
)


class HarnessFailure(ValueError):
    pass


def _git(path: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed."
        raise HarnessFailure(message)
    return result.stdout.strip()


def _is_harness(path: Path) -> bool:
    return path.is_dir() and all((path / relative).is_file() for relative in REQUIRED_FILES)


def _candidates(project_root: Path) -> list[Path]:
    candidates = [project_root / "delta-research"]
    for parent in (project_root, *project_root.parents):
        candidates.append(parent)
    configured = os.environ.get("DELTA_RESEARCH_HOME", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    development_checkout = Path(__file__).resolve().parents[2].parent / "delta-research"
    candidates.append(development_checkout)

    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result


def find_harness(project_root: str | Path) -> Path | None:
    root = Path(project_root).expanduser().resolve()
    return next((candidate for candidate in _candidates(root) if _is_harness(candidate)), None)


def _official_source(source: str) -> bool:
    normalized = source.removesuffix(".git").removesuffix("/")
    return normalized in {
        "https://github.com/user074/delta-research",
        "git@github.com:user074/delta-research",
        "ssh://git@github.com/user074/delta-research",
    }


def inspect_harness(project_root: str | Path) -> HarnessInfo:
    path = find_harness(project_root)
    if not path:
        return HarnessInfo(
            source_url=OFFICIAL_REPOSITORY,
            status="missing",
            detail=(
                "No delta-research harness was found. Put the official checkout inside the research project "
                "or set DELTA_RESEARCH_HOME."
            ),
        )

    if not (path / ".git").exists():
        return HarnessInfo(
            source_url=OFFICIAL_REPOSITORY,
            path=str(path),
            status="unversioned",
            detail="The harness files are available, but this copy is not a Git checkout.",
        )

    source = _git(path, "remote", "get-url", "origin", check=False) or OFFICIAL_REPOSITORY
    revision = _git(path, "rev-parse", "HEAD", check=False)
    branch = _git(path, "branch", "--show-current", check=False)
    upstream_ref = _git(path, "symbolic-ref", "refs/remotes/origin/HEAD", check=False)
    if not upstream_ref:
        upstream_ref = "refs/remotes/origin/main"
    upstream_revision = _git(path, "rev-parse", upstream_ref, check=False)
    dirty = bool(_git(path, "status", "--porcelain", "--untracked-files=no", check=False))
    ahead = 0
    behind = 0
    if revision and upstream_revision:
        counts = _git(path, "rev-list", "--left-right", "--count", f"{revision}...{upstream_revision}", check=False)
        try:
            ahead, behind = (int(value) for value in counts.split())
        except (TypeError, ValueError):
            ahead = behind = 0

    if dirty:
        status = "modified"
        detail = (
            "Current upstream revision with local integration changes."
            if not ahead and not behind
            else "The harness has local integration changes; update it only after reviewing them."
        )
    elif behind and ahead:
        status = "diverged"
        detail = "The local harness and its upstream branch have diverged."
    elif behind:
        status = "behind"
        detail = f"The local harness is {behind} commit{'s' if behind != 1 else ''} behind upstream."
    elif ahead:
        status = "ahead"
        detail = f"The local harness is {ahead} commit{'s' if ahead != 1 else ''} ahead of upstream."
    else:
        status = "current"
        detail = "The local harness matches the latest fetched upstream revision."

    if not _official_source(source):
        detail = f"This checkout uses a different Git remote: {source}"

    return HarnessInfo(
        source_url=source,
        path=str(path),
        revision=revision,
        upstream_revision=upstream_revision,
        branch=branch,
        status=status,
        detail=detail,
        local_changes=dirty,
        commits_ahead=ahead,
        commits_behind=behind,
        official_source=_official_source(source),
    )


def update_harness(project_root: str | Path) -> HarnessInfo:
    current = inspect_harness(project_root)
    if not current.path:
        raise HarnessFailure(current.detail)
    if current.status == "unversioned":
        raise HarnessFailure("The delta-research files are not a Git checkout, so they cannot be updated safely.")
    if not current.official_source:
        raise HarnessFailure("Refusing to update: this harness is not connected to user074/delta-research.")
    if current.local_changes:
        raise HarnessFailure(
            "The delta-research checkout has tracked local changes. Review or commit them before updating."
        )

    path = Path(current.path)
    _git(path, "fetch", "--prune", "origin")
    upstream_ref = _git(path, "symbolic-ref", "refs/remotes/origin/HEAD", check=False)
    if not upstream_ref:
        upstream_ref = "refs/remotes/origin/main"
    _git(path, "merge", "--ff-only", upstream_ref)
    return inspect_harness(project_root)
