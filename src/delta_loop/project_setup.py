from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .harness import inspect_harness
from .importer import UNSET_GOAL
from .models import Claim, ProjectSetupRequest, ProjectSnapshot, ResearchNode, now_iso
from .rules import initial_rules_version


class ProjectSetupFailure(ValueError):
    """Raised when an initial project setup cannot be safely completed."""


def create_remote_workspace(control_root: Path) -> ProjectSnapshot:
    """Create local Delta Loop notes for a project whose code stays on a server."""
    workspace_id = f"remote-{uuid4().hex[:12]}"
    root = (control_root / workspace_id).resolve()
    root.mkdir(parents=True, exist_ok=False)
    question_id = f"question-{workspace_id}"
    return ProjectSnapshot(
        id=workspace_id,
        root=str(root),
        name="Remote project",
        goal=UNSET_GOAL,
        status="setup",
        nodes=[
            ResearchNode(
                id=question_id,
                kind="question",
                title=UNSET_GOAL,
                summary="Codex will connect to and understand the existing project on your server.",
                status="primary",
                promise="high",
                evidence_strength="none",
            )
        ],
        rules_versions=[initial_rules_version()],
        active_rules_version_id="rules-v1",
        harness=inspect_harness(root),
        setup_status="needs-setup",
        project_source="remote",
    )


def _line(value: str) -> str:
    return " ".join(value.split()).strip()


def _cell(value: str) -> str:
    return _line(value).replace("|", "\\|")


def render_initial_state(
    workspace: ProjectSnapshot,
    request: ProjectSetupRequest,
) -> str:
    questions = [node for node in workspace.nodes if node.kind == "question"]
    directions = [node for node in workspace.nodes if node.kind == "direction"]
    approaches = [node for node in workspace.nodes if node.kind == "approach"]
    direction_numbers = {node.id: index for index, node in enumerate(directions, start=1)}
    today = now_iso()[:10]
    lines = [
        f"# STATE — {_line(workspace.name)}",
        "",
        "## Meta",
        f"- **project**: {_line(workspace.name)}",
        f"- **goal**: {_line(workspace.goal)}",
        f"- **last_updated**: {today}",
        "- **status**: active",
        "",
        "## ResearchQuestions",
        "| Question | Status | Scope |",
        "|---|---|---|",
    ]
    for question in questions:
        lines.append(
            f"| {_cell(question.title)} | {_cell(question.status)} | "
            f"{_cell(question.summary or 'High-level research question')} |"
        )
    lines.extend(
        [
        "",
        "## BeliefState",
        "| # | Parent | Belief | Status | Confidence | Key evidence | Last updated |",
        "|---|---|---|---|---|---|---|",
        ]
    )
    for index, direction in enumerate(directions, start=1):
        lines.append(
            f"| {index} | — | {_cell(direction.title)} | active | 0.5 | "
            f"{_cell(direction.summary or 'Seeded during project setup')} | {today} |"
        )
    if not directions:
        lines.append("| 1 | — | No seed hypothesis recorded yet | active | 0.5 | Setup incomplete | " + today + " |")

    lines.extend(
        [
            "",
            "## Ledger",
            "| Run | Delta | Signal | Verdict | Belief | Link |",
            "|---|---|---|---|---|---|",
            "",
            "## Frontier",
            "| Rank | Delta | Target | Uncertainty | Info gain | Feasibility | Rationale | Blocked by |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for index, approach in enumerate(approaches, start=1):
        target = direction_numbers.get(approach.parent_id or "")
        promise = approach.promise if approach.promise in {"high", "medium", "low"} else "medium"
        lines.append(
            f"| {index} | {_cell(approach.title)} | #{target or 1} | high | {promise} | {promise} | "
            f"{_cell(approach.summary or 'Seeded during project setup')} | — |"
        )

    lines.extend(["", "## Environment", "", "### Reference repos"])
    if request.reference_repos:
        lines.extend(f"- {_line(item)}" for item in request.reference_repos if _line(item))
    else:
        lines.append("- None recorded")
    if workspace.project_source == "remote":
        lines.extend(
            [
                "",
                "### Research code",
                f"- SSH host: {_line(workspace.compute.ssh_host) or 'Not recorded'}",
                f"- Project folder on server: {_line(workspace.compute.project_path) or 'Not recorded'}",
                "- Delta Loop notes are stored locally; the research code remains on the server.",
            ]
        )
    lines.extend(["", "### Initial constraints"])
    if request.constraints:
        lines.extend(f"- {_line(item)}" for item in request.constraints if _line(item))
    else:
        lines.append("- None recorded")
    lines.extend(
        [
            "",
            "## Scratch",
            f"- Initial project summary: {_line(request.summary)}",
            "- Compute location is configured separately in Delta Loop.",
            "",
        ]
    )
    return "\n".join(lines)


def complete_project_setup(
    workspace: ProjectSnapshot,
    request: ProjectSetupRequest,
) -> ProjectSnapshot:
    if workspace.setup_status != "needs-setup":
        raise ProjectSetupFailure("This project setup is already complete.")
    if not request.summary.strip():
        raise ProjectSetupFailure("Add a short project summary before finishing setup.")
    if workspace.goal == "Research question not set up yet" or not workspace.goal.strip():
        raise ProjectSetupFailure("Agree on and save the main research question first.")
    if workspace.project_source == "remote" and (
        not workspace.compute.configured
        or workspace.compute.kind != "ssh"
        or workspace.compute.status != "ready"
    ):
        raise ProjectSetupFailure(
            "Connect and check the remote project before finishing setup."
        )
    directions = [node for node in workspace.nodes if node.kind == "direction"]
    if not directions:
        raise ProjectSetupFailure("Add at least one research idea or hypothesis first.")

    state_path = Path(workspace.root) / "STATE.md"
    if state_path.exists():
        raise ProjectSetupFailure(
            "STATE.md appeared during setup. Reopen the project so Delta Loop can import it safely."
        )
    try:
        with state_path.open("x", encoding="utf-8") as handle:
            handle.write(render_initial_state(workspace, request))
    except OSError as exc:
        raise ProjectSetupFailure(f"Could not create {state_path}: {exc}") from exc

    workspace.setup_status = "ready"
    workspace.setup_summary = request.summary.strip()
    workspace.reference_repos = [item.strip() for item in request.reference_repos if item.strip()]
    workspace.setup_constraints = [item.strip() for item in request.constraints if item.strip()]
    workspace.synthesis = request.summary.strip()
    workspace.status = "active"
    workspace.last_updated = now_iso()
    if "STATE.md" not in workspace.source_files:
        workspace.source_files.insert(0, "STATE.md")
    workspace.claims = [
        Claim(
            id=f"claim-{index}",
            statement=direction.title,
            status="active",
            confidence=0.5,
            evidence=direction.summary,
            updated_at=now_iso()[:10],
        )
        for index, direction in enumerate(directions, start=1)
    ]
    return workspace
