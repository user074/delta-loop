from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .harness import inspect_harness
from .importer import UNSET_GOAL
from .models import Claim, ProjectInitialization, ProjectSetupRequest, ProjectSnapshot, ResearchNode, now_iso
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
        initialization=ProjectInitialization(status="pending"),
    )


def _line(value: str) -> str:
    return " ".join(value.split()).strip()


def _cell(value: str) -> str:
    return _line(value).replace("|", "\\|")


def _permission_label(value: str) -> str:
    return {
        "manual": "Ask before each command",
        "scoped": "Run commands inside the approved project and limits",
        "full": "Run project commands within the saved safety limits",
    }[value]


def render_initial_state(
    workspace: ProjectSnapshot,
    request: ProjectSetupRequest,
) -> str:
    questions = [node for node in workspace.nodes if node.kind == "question"]
    directions = [node for node in workspace.nodes if node.kind == "direction"]
    approaches = [node for node in workspace.nodes if node.kind == "approach"]
    direction_numbers = {node.id: index for index, node in enumerate(directions, start=1)}
    approaches_by_direction: dict[str, list[ResearchNode]] = {node.id: [] for node in directions}
    for approach in approaches:
        linked = [
            link.source_id
            for link in workspace.research_links
            if link.target_id == approach.id and link.relationship == "tests"
        ]
        parent_ids = linked or ([approach.parent_id] if approach.parent_id else [])
        for direction_id in parent_ids:
            if direction_id in approaches_by_direction:
                approaches_by_direction[direction_id].append(approach)
    today = now_iso()[:10]
    compute = workspace.compute
    inspection = workspace.compute_inspection
    compute_project = compute.project_path if compute.kind == "ssh" else workspace.root
    lines = [
        f"# STATE — {_line(workspace.name)}",
        "",
        "## Meta",
        f"- **project**: {_line(workspace.name)}",
        f"- **goal**: {_line(workspace.goal)}",
        f"- **started**: {today}",
        f"- **last_updated**: {today}",
        "- **total_runs**: 0",
        "- **status**: active",
        "- **paradigm**: v1",
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
            "## Environment",
            f"- **execution**: {'SSH via ' + compute.ssh_host if compute.kind == 'ssh' else 'local'}",
            f"- **env activation**: {_line(compute.setup_command) or 'None required'}",
            f"- **python**: {_line(compute.detected_python) or _line(inspection.python_version if inspection else '') or 'verified by Delta Loop'}",
            f"- **gpu**: {_line(compute.gpu_devices) or 'No explicit restriction'}",
            f"- **cpu**: {_line(inspection.cpu if inspection else '') or 'Not recorded'}",
            f"- **working dir**: {_line(compute_project)}",
            f"- **run records**: {_line(compute.run_path) if compute.kind == 'ssh' else 'Delta Loop local run storage'}",
            f"- **git remote**: {_line(workspace.git_repository.remote_url) or _line(inspection.git_remote if inspection else '') or 'Not configured'}",
            f"- **git research branch**: {_line(workspace.git_repository.branch) or _line(inspection.git_branch if inspection else '') or 'Not chosen'}",
            f"- **git publish policy**: reviewed during initialization; see .delta-loop/POLICY.md",
            "",
            "### Reference repos",
        ]
    )
    lines.extend(
        [f"- {_line(item)}" for item in request.reference_repos if _line(item)]
        or ["- None recorded"]
    )
    lines.extend(["", "### Reusable inputs"])
    lines.extend(
        [f"- {_line(item)}" for item in request.reusable_inputs if _line(item)]
        or ["- None recorded"]
    )
    lines.extend(
        [
            "",
            "## BeliefState",
            "| # | Parent | Belief | Status | Confidence | Literature | Key evidence | Last updated |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for index, direction in enumerate(directions, start=1):
        lines.append(
            f"| {index} | — | {_cell(direction.title)} | active | 0.5 | pending | "
            f"{_cell(direction.summary or 'Seeded during project setup')} | {today} |"
        )
    if not directions:
        lines.append("| 1 | — | No seed hypothesis recorded yet | active | 0.5 | pending | Setup incomplete | " + today + " |")

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
    rank = 1
    for direction in directions:
        target = direction_numbers[direction.id]
        literature_title = f"Literature review for belief #{target}"
        lines.append(
            f"| {rank} | {literature_title} | #{target} | high | high | high | "
            f"Ground this hypothesis and its closest contrary work before empirical testing | — |"
        )
        rank += 1
        for approach in approaches_by_direction[direction.id]:
            promise = approach.promise if approach.promise in {"high", "medium", "low"} else "medium"
            lines.append(
                f"| {rank} | {_cell(approach.title)} | #{target} | high | {promise} | {promise} | "
                f"{_cell(approach.summary or 'Seeded during project setup')} | {literature_title} |"
            )
            rank += 1

    lines.extend(["", "## Policy", "", "### Interrupt boundaries"])
    lines.extend(
        [
            f"- **BUDGET**: {_line(request.budget)}",
            f"- **SUCCESS**: {_line(request.success_condition)}",
            f"- **STOP**: {_line(request.stop_condition)}",
            "- **BLOCKER**: work cannot proceed safely within the approved setup",
            "- **AMBIGUITY**: the next scientific choice needs researcher judgment",
            "- **IRREVERSIBLE**: an action cannot be safely undone or exceeds recorded permission",
            "",
            "### Constraints",
        ]
    )
    lines.extend(
        [f"- {_line(item)}" for item in request.constraints if _line(item)]
        or ["- No additional constraint recorded"]
    )
    lines.extend(
        [
            "- Every new or materially changed hypothesis requires its own literature review before empirical work.",
            "- Workers never update STATE.md; the supervisor updates it only after checking the result.",
            "- Git commit and push behavior follows the reviewed Git rules in .delta-loop/POLICY.md.",
        ]
    )
    lines.extend(
        [
            "",
            "## Scratch",
            f"- Initial project summary: {_line(request.summary)}",
            *[f"- Prior work: {_line(item)}" for item in request.prior_work if _line(item)],
            f"- Agent command permission: {_permission_label(request.permission_mode)}",
            "- Initialization was completed through Delta Loop and confirmed by the researcher.",
            "",
        ]
    )
    return "\n".join(lines)


def render_initialization_record(workspace: ProjectSnapshot, request: ProjectSetupRequest) -> str:
    compute = workspace.compute
    actual_project = (
        f"{compute.ssh_host}:{compute.project_path}"
        if compute.kind == "ssh"
        else workspace.root
    )
    lines = [
        "# Project initialization",
        "",
        "This is the researcher-approved starting setup adapted from `delta-research/templates/INIT.md`.",
        "",
        "## Project understanding",
        request.summary.strip(),
        "",
        "## Research starting point",
        f"- **Question:** {_line(workspace.goal)}",
        f"- **Questions recorded:** {len([node for node in workspace.nodes if node.kind == 'question'])}",
        f"- **Ideas recorded:** {len([node for node in workspace.nodes if node.kind == 'direction'])}",
        f"- **Research work recorded:** {len([node for node in workspace.nodes if node.kind == 'approach'])}",
        "- **Literature gate:** Each new or materially changed hypothesis must be reviewed before empirical work.",
        "",
        "### What was already tried",
    ]
    lines.extend([f"- {_line(item)}" for item in request.prior_work if _line(item)] or ["- Nothing recorded"])
    lines.extend(["", "## Reusable starting material", "", "### Reference repositories"])
    lines.extend([f"- {_line(item)}" for item in request.reference_repos if _line(item)] or ["- None recorded"])
    lines.extend(["", "### Data, checkpoints, models, and evaluation tools"])
    lines.extend([f"- {_line(item)}" for item in request.reusable_inputs if _line(item)] or ["- None recorded"])
    lines.extend(
        [
            "",
            "## Boundaries",
            f"- **Success looks like:** {_line(request.success_condition)}",
            f"- **Stop when:** {_line(request.stop_condition)}",
            f"- **Budget:** {_line(request.budget)}",
            f"- **Agent command permission:** {_permission_label(request.permission_mode)}",
            "",
            "### Project constraints",
        ]
    )
    lines.extend([f"- {_line(item)}" for item in request.constraints if _line(item)] or ["- None recorded"])
    lines.extend(
        [
            "",
            "## Verified execution",
            f"- **Research repository:** {_line(actual_project)}",
            f"- **Compute check:** {'verified' if request.environment_verified else 'not verified'}",
            f"- **Environment setup:** {_line(compute.setup_command) or 'None required'}",
            f"- **Git choices reviewed:** {'yes' if request.git_reviewed else 'no'}",
            "",
            "The actual active commands and limits are in `.delta-loop/POLICY.md`; the complete loop is in `.delta-loop/LOOP.md`.",
            "",
        ]
    )
    return "\n".join(lines)


def render_initial_synthesis(workspace: ProjectSnapshot, request: ProjectSetupRequest) -> str:
    ideas = [node for node in workspace.nodes if node.kind == "direction"]
    lines = [
        f"# SYNTHESIS — {_line(workspace.name)}",
        "",
        "## Main question",
        _line(workspace.goal),
        "",
        "## Starting understanding",
        request.summary.strip(),
        "",
        "## Seed ideas",
    ]
    lines.extend([f"- **{_line(node.title)}:** {_line(node.summary) or 'No summary recorded'}" for node in ideas])
    lines.extend(["", "## What would count as progress", _line(request.success_condition), ""])
    return "\n".join(lines)


def render_literature_index(workspace: ProjectSnapshot) -> str:
    ideas = [node for node in workspace.nodes if node.kind == "direction"]
    lines = [
        "# Literature grounding",
        "",
        "Each idea starts pending. Its focused literature review must be recorded before empirical work targets it.",
        "",
        "| Idea | Status | Latest review | Direction from literature |",
        "|---|---|---|---|",
    ]
    lines.extend(f"| {_cell(node.title)} | pending | — | — |" for node in ideas)
    return "\n".join(lines) + "\n"


def render_initial_infra(workspace: ProjectSnapshot, request: ProjectSetupRequest) -> str:
    compute = workspace.compute
    inspection = workspace.compute_inspection
    project_path = compute.project_path if compute.kind == "ssh" else workspace.root
    lines = [
        f"# INFRA — {_line(workspace.name)}",
        "",
        "Generated from Delta Loop's read-only inspection and researcher-approved choices.",
        "",
        "## Execution",
        f"- **mode**: {'direct SSH' if compute.kind == 'ssh' else 'local'}",
        f"- **host**: {_line(compute.ssh_host) if compute.kind == 'ssh' else 'this computer'}",
        f"- **project root**: {_line(project_path)}",
        f"- **run records**: {_line(compute.run_path) if compute.kind == 'ssh' else 'Delta Loop local run storage'}",
        f"- **validated environment activation**: {_line(compute.setup_command) or 'None required'}",
        f"- **last compute check**: {_line(compute.last_checked_at) or 'Not recorded'}",
        "",
        "## Detected compute",
        f"- **host name**: {_line(inspection.hostname if inspection else '') or _line(compute.name)}",
        f"- **operating system**: {_line(inspection.operating_system if inspection else '') or 'Not recorded'}",
        f"- **Python**: {_line(compute.detected_python) or _line(inspection.python_path if inspection else '') or 'Not recorded'}",
        f"- **CPU**: {_line(inspection.cpu if inspection else '') or 'Not recorded'}",
        f"- **memory**: {_line(inspection.memory if inspection else '') or 'Not recorded'}",
        f"- **scheduler**: {_line(inspection.scheduler if inspection else '') or 'none detected'}",
        "",
        "### GPUs",
    ]
    gpus = compute.detected_gpus or (inspection.gpus if inspection else [])
    lines.extend([f"- {_line(item)}" for item in gpus] or ["- None visible during inspection"])
    lines.extend(
        [
            "",
            "## Resource choices",
            f"- **allowed GPU numbers**: {_line(compute.gpu_devices) or 'No explicit restriction'}",
            f"- **runs at once**: {compute.max_parallel}",
            f"- **budget**: {_line(request.budget)}",
            "",
            "## Storage and project rules",
        ]
    )
    lines.extend([f"- {_line(item)}" for item in request.constraints if _line(item)] or ["- No additional rule recorded"])
    lines.extend(
        [
            "",
            "This compact profile records verified facts and approved limits. Re-run Compute setup when the environment, hardware, scheduler, or storage policy changes.",
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
    if not request.success_condition.strip():
        raise ProjectSetupFailure("Agree on what success looks like before finishing setup.")
    if not request.stop_condition.strip():
        raise ProjectSetupFailure("Agree on when the project should stop or ask before finishing setup.")
    if not request.budget.strip():
        raise ProjectSetupFailure("Agree on a time or compute budget before finishing setup.")
    if not request.environment_verified:
        raise ProjectSetupFailure("Verify the chosen environment before finishing setup.")
    if not request.git_reviewed:
        raise ProjectSetupFailure("Review the Git and GitHub behavior before finishing setup, even if it stays off.")
    if (
        not workspace.compute.configured
        or workspace.compute.status != "ready"
        or not workspace.compute.last_checked_at
    ):
        raise ProjectSetupFailure(
            "Choose and check where research work runs before finishing setup."
        )
    if workspace.project_source == "remote" and workspace.compute.kind != "ssh":
        raise ProjectSetupFailure("A remote project must use its saved SSH compute location during setup.")
    if workspace.git_repository.state == "unchecked":
        raise ProjectSetupFailure(
            "Check the research repository's Git state before reviewing its Git and GitHub behavior."
        )
    directions = [node for node in workspace.nodes if node.kind == "direction"]
    if not directions:
        raise ProjectSetupFailure("Add at least one research idea or hypothesis first.")
    approaches = [node for node in workspace.nodes if node.kind == "approach"]
    if not approaches:
        raise ProjectSetupFailure("Add at least one concrete experiment before finishing setup.")

    state_path = Path(workspace.root) / "STATE.md"
    if state_path.exists():
        raise ProjectSetupFailure(
            "STATE.md appeared during setup. Reopen the project so Delta Loop can import it safely."
        )
    root = Path(workspace.root)
    initialization_path = root / ".delta-loop" / "INITIALIZATION.md"
    synthesis_path = root / "SYNTHESIS.md"
    infra_path = root / "INFRA.md"
    literature_path = root / "LITERATURE" / "INDEX.md"
    try:
        (root / "REPORTS").mkdir(exist_ok=True)
        (root / "RUNS").mkdir(exist_ok=True)
        literature_path.parent.mkdir(exist_ok=True)
        initialization_path.parent.mkdir(exist_ok=True)
        initialization_path.write_text(
            render_initialization_record(workspace, request), encoding="utf-8"
        )
        if not synthesis_path.exists():
            synthesis_path.write_text(
                render_initial_synthesis(workspace, request), encoding="utf-8"
            )
        if not infra_path.exists():
            infra_path.write_text(render_initial_infra(workspace, request), encoding="utf-8")
        if not literature_path.exists():
            literature_path.write_text(render_literature_index(workspace), encoding="utf-8")
        with state_path.open("x", encoding="utf-8") as handle:
            handle.write(render_initial_state(workspace, request))
    except OSError as exc:
        raise ProjectSetupFailure(f"Could not create the initial research files: {exc}") from exc

    workspace.setup_status = "ready"
    workspace.setup_summary = request.summary.strip()
    workspace.reference_repos = [item.strip() for item in request.reference_repos if item.strip()]
    workspace.setup_constraints = [item.strip() for item in request.constraints if item.strip()]
    workspace.initialization = ProjectInitialization(
        status="complete",
        project_understanding=request.summary.strip(),
        prior_work=[item.strip() for item in request.prior_work if item.strip()],
        reusable_inputs=[item.strip() for item in request.reusable_inputs if item.strip()],
        success_condition=request.success_condition.strip(),
        stop_condition=request.stop_condition.strip(),
        budget=request.budget.strip(),
        permission_mode=request.permission_mode,
        environment_verified=True,
        git_reviewed=True,
        literature_gate=True,
        completed_at=now_iso(),
        source_revision=workspace.harness.upstream_revision or workspace.harness.revision,
        initialization_file=str(initialization_path),
        infra_file=str(infra_path),
        synthesis_file=str(synthesis_path),
        literature_index_file=str(literature_path),
    )
    workspace.synthesis = request.summary.strip()
    workspace.status = "active"
    workspace.last_updated = now_iso()
    for name in (
        ".delta-loop/INITIALIZATION.md",
        "LITERATURE/INDEX.md",
        "SYNTHESIS.md",
        "INFRA.md",
        "STATE.md",
    ):
        if name not in workspace.source_files:
            workspace.source_files.insert(0, name)
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
