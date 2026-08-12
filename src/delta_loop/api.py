from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .compute import (
    ComputeFailure,
    check_compute,
    inspect_local_compute,
    inspect_remote_compute,
    validate_compute,
)
from .harness import HarnessFailure, inspect_harness, update_harness
from .importer import ImportFailure, import_workspace
from .models import (
    ComputeConfig,
    ComputeConfigRequest,
    ComputeInspectRequest,
    ComputeInspection,
    HarnessInfo,
    ImportRequest,
    NodePatch,
    ProjectSnapshot,
    ProtocolDecision,
    ProtocolDecisionRequest,
    QuestionRevision,
    QuickNote,
    QuickNoteRequest,
    ResearchNode,
    ResultReview,
    ResultReviewRequest,
    RulesDraftRequest,
    RulesVersion,
    TerminalCreateRequest,
    TerminalSessionInfo,
    WorkPackage,
    WorkPackagePatch,
    WorkPackageRequest,
    WorkspacePatch,
    now_iso,
)
from .policy_sync import LOOP_RELATIVE_PATH, POLICY_RELATIVE_PATH, PolicySyncFailure, sync_policy
from .protocols import default_protocols, next_stage
from .rules import (
    POLICY_SCHEMA_VERSION,
    check_rules,
    initial_rules_version,
    upgrade_policy_rules,
)
from .runner import AttemptRunner, RunFailure
from .store import WorkspaceStore
from .terminal import TerminalFailure, TerminalManager


def create_app(store_path: str | Path | None = None) -> FastAPI:
    data_path = Path(
        store_path
        or os.environ.get("DELTA_LOOP_DATA_PATH", ".delta-loop-data/workspaces.json")
    )
    store = WorkspaceStore(data_path)
    protocols = {profile.id: profile for profile in default_protocols()}
    runner = AttemptRunner(store)
    terminals = TerminalManager()
    app = FastAPI(title="Delta Loop", version="0.1.0")
    app.state.store = store
    app.state.runner = runner
    app.state.terminals = terminals
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4317", "http://localhost:4317"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def save_with_policy(workspace: ProjectSnapshot) -> ProjectSnapshot:
        try:
            sync_policy(workspace)
        except PolicySyncFailure as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return store.save(workspace)

    def policy_file_missing(workspace: ProjectSnapshot) -> bool:
        root = Path(workspace.root).expanduser().resolve()
        expected_policy = root / POLICY_RELATIVE_PATH
        expected_loop = root / LOOP_RELATIVE_PATH
        return (
            workspace.policy_file != str(expected_policy)
            or workspace.loop_file != str(expected_loop)
            or not expected_policy.is_file()
            or not expected_loop.is_file()
        )

    def ensure_current_rules(workspace: ProjectSnapshot) -> bool:
        if not workspace.rules_versions:
            first = initial_rules_version()
            workspace.rules_versions = [first]
            workspace.active_rules_version_id = first.id
            workspace.policy_schema_version = POLICY_SCHEMA_VERSION
            return True
        active = next(
            (
                version for version in workspace.rules_versions
                if version.id == workspace.active_rules_version_id
            ),
            None,
        )
        changed = False
        if workspace.policy_schema_version < POLICY_SCHEMA_VERSION and active:
            upgraded_rules, rules_changed = upgrade_policy_rules(active)
            if rules_changed:
                active.status = "retired"
                next_number = max(version.version for version in workspace.rules_versions) + 1
                upgraded = RulesVersion(
                    id=f"rules-v{next_number}",
                    version=next_number,
                    status="active",
                    parent_id=active.id,
                    rules=upgraded_rules,
                    checked_at=now_iso(),
                    activated_at=now_iso(),
                )
                workspace.rules_versions.append(upgraded)
                workspace.active_rules_version_id = upgraded.id
            workspace.policy_schema_version = POLICY_SCHEMA_VERSION
            changed = True
        return changed

    def refresh_harness(workspace: ProjectSnapshot) -> bool:
        harness = inspect_harness(workspace.root)
        if harness == workspace.harness:
            return False
        workspace.harness = harness
        return True

    def workspace_or_404(workspace_id: str) -> ProjectSnapshot:
        workspace = store.get(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Project not found.")
        runner.refresh(workspace_id)
        workspace = store.get(workspace_id) or workspace
        if ensure_current_rules(workspace) or refresh_harness(workspace) or policy_file_missing(workspace):
            save_with_policy(workspace)
        return workspace

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/protocols")
    def list_protocols():
        return list(protocols.values())

    @app.get("/api/workspaces", response_model=list[ProjectSnapshot])
    def list_workspaces() -> list[ProjectSnapshot]:
        workspaces = store.list()
        for workspace in workspaces:
            runner.refresh(workspace.id)
            workspace = store.get(workspace.id) or workspace
            if ensure_current_rules(workspace) or refresh_harness(workspace) or policy_file_missing(workspace):
                save_with_policy(workspace)
        return store.list()

    @app.get("/api/workspaces/{workspace_id}", response_model=ProjectSnapshot)
    def get_workspace(workspace_id: str) -> ProjectSnapshot:
        return workspace_or_404(workspace_id)

    @app.patch("/api/workspaces/{workspace_id}", response_model=ProjectSnapshot)
    def update_workspace(workspace_id: str, patch: WorkspacePatch) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        goal = patch.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="Write the updated research question first.")
        if goal == workspace.goal:
            raise HTTPException(status_code=422, detail="The research question has not changed.")
        workspace.question_history.append(
            QuestionRevision(previous=workspace.goal, current=goal, reason=patch.reason.strip())
        )
        workspace.goal = goal
        workspace.last_updated = now_iso()
        question = next((node for node in workspace.nodes if node.kind == "question"), None)
        if question:
            question.title = goal
        return save_with_policy(workspace)

    @app.put("/api/workspaces/{workspace_id}/compute", response_model=ProjectSnapshot)
    def update_compute(
        workspace_id: str, request: ComputeConfigRequest
    ) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        values = request.model_dump()
        if not values["name"].strip():
            values["name"] = (
                "This computer" if request.kind == "local" else request.ssh_host
            )
        config = ComputeConfig(**values, configured=True)
        try:
            validate_compute(config)
        except ComputeFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if config.kind == "local":
            config.status = "ready"
            config.status_message = "Runs use the local research project."
        else:
            config.status = "unchecked"
            config.status_message = "Save these settings, then check the connection."
        inspection = workspace.compute_inspection
        def same_remote_path(configured: str, resolved: str, home: str) -> bool:
            if configured == resolved:
                return True
            if configured.startswith("~/") and home:
                return f"{home.rstrip('/')}/{configured[2:]}" == resolved
            return False
        if inspection:
            if config.kind == "local":
                if inspection.host != "this-computer":
                    workspace.compute_inspection = None
            elif (
                inspection.host != config.ssh_host
                or not same_remote_path(
                    config.project_path, inspection.project_path, inspection.home_path
                )
                or not same_remote_path(
                    config.run_path, inspection.run_path, inspection.home_path
                )
            ):
                workspace.compute_inspection = None
        workspace.compute = config
        workspace.last_updated = now_iso()
        return save_with_policy(workspace)

    @app.post(
        "/api/workspaces/{workspace_id}/compute/reset",
        response_model=ProjectSnapshot,
    )
    def reset_workspace_compute(workspace_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        workspace.compute = ComputeConfig()
        workspace.compute_inspection = None
        workspace.last_updated = now_iso()
        return save_with_policy(workspace)

    @app.post(
        "/api/workspaces/{workspace_id}/compute/inspect",
        response_model=ComputeInspection,
    )
    def inspect_workspace_compute(
        workspace_id: str, request: ComputeInspectRequest
    ) -> ComputeInspection:
        workspace = workspace_or_404(workspace_id)
        if request.kind == "local":
            inspection = inspect_local_compute(
                workspace.root,
                str(store.path.parent / "runs"),
            )
            workspace.compute_inspection = inspection
            store.save(workspace)
            return inspection
        host = request.ssh_host.strip()
        project_path = request.project_path.strip()
        run_path = request.run_path.strip() or "~/.delta-loop/runs"
        if not host and workspace.compute.kind == "ssh":
            host = workspace.compute.ssh_host
        if not project_path and workspace.compute.kind == "ssh":
            project_path = workspace.compute.project_path
        if request.run_path == "~/.delta-loop/runs" and workspace.compute.kind == "ssh":
            run_path = workspace.compute.run_path
        if not host or not project_path:
            raise HTTPException(
                status_code=422,
                detail="Give Codex the SSH host and remote project folder before inspecting the server.",
            )
        try:
            inspection = inspect_remote_compute(host, project_path, run_path)
        except ComputeFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        workspace.compute_inspection = inspection
        store.save(workspace)
        return inspection

    @app.post(
        "/api/workspaces/{workspace_id}/compute/check",
        response_model=ProjectSnapshot,
    )
    def check_workspace_compute(workspace_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        if not workspace.compute.configured:
            raise HTTPException(
                status_code=422,
                detail="Choose and save this computer or a remote server before checking it.",
            )
        result = check_compute(workspace.compute, workspace.root)
        workspace.compute.status = result.status
        workspace.compute.status_message = result.message
        workspace.compute.last_checked_at = result.checked_at
        workspace.compute.detected_python = result.python
        workspace.compute.detected_git = result.git
        workspace.compute.detected_gpus = result.gpus
        workspace.last_updated = now_iso()
        return save_with_policy(workspace)

    @app.post("/api/workspaces/import", response_model=ProjectSnapshot)
    def import_project(request: ImportRequest) -> ProjectSnapshot:
        try:
            workspace = import_workspace(request.path)
        except ImportFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        workspace = store.put(workspace)
        ensure_current_rules(workspace)
        return save_with_policy(workspace)

    @app.patch("/api/workspaces/{workspace_id}/nodes/{node_id}", response_model=ProjectSnapshot)
    def patch_node(workspace_id: str, node_id: str, patch: NodePatch) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        node = next((item for item in workspace.nodes if item.id == node_id), None)
        if not node:
            raise HTTPException(status_code=404, detail="Idea not found.")
        if patch.title is not None and not patch.title.strip():
            raise HTTPException(status_code=422, detail="The idea needs a short name.")
        if patch.parent_id is not None:
            parent = next((item for item in workspace.nodes if item.id == patch.parent_id), None)
            expected_parent = "question" if node.kind == "direction" else "direction"
            if node.kind == "question" or not parent or parent.kind != expected_parent:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "An idea must sit under the main question."
                        if node.kind == "direction"
                        else "A way to test an idea must sit under an idea."
                    ),
                )
        if patch.protocol_id:
            if node.kind != "approach":
                raise HTTPException(status_code=422, detail="Testing styles apply only to ways of testing an idea.")
            if patch.protocol_id not in protocols:
                raise HTTPException(status_code=422, detail="Testing style not found.")
        changes = patch.model_dump(exclude_none=True)
        if "title" in changes:
            changes["title"] = changes["title"].strip()
        for field, value in changes.items():
            setattr(node, field, value)
        if {"next_work_kind", "agent_guidance", "ask_before"} & changes.keys():
            node.policy_updated_at = now_iso()
        workspace.last_updated = now_iso()
        if patch.protocol_id:
            profile = protocols[patch.protocol_id]
            if node.current_stage not in {stage.id for stage in profile.stages}:
                node.current_stage = profile.stages[0].id
        return save_with_policy(workspace)

    @app.post("/api/workspaces/{workspace_id}/notes", response_model=ProjectSnapshot)
    def add_note(workspace_id: str, request: QuickNoteRequest) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Write a short idea or note first.")
        requested_parent = None
        if request.kind == "way-to-test" and request.parent_id:
            requested_parent = next(
                (
                    node for node in workspace.nodes
                    if node.kind == "direction" and node.id == request.parent_id
                ),
                None,
            )
            if not requested_parent:
                raise HTTPException(status_code=422, detail="Choose an idea for this way of testing it.")
        note = QuickNote(
            id=f"note-{uuid4().hex[:10]}",
            text=text,
            kind=request.kind,
            parent_id=request.parent_id,
        )
        workspace.notes.append(note)
        question = next((node for node in workspace.nodes if node.kind == "question"), None)
        direction = next((node for node in workspace.nodes if node.kind == "direction"), None)
        if request.kind == "idea":
            workspace.nodes.append(
                ResearchNode(
                    id=f"idea-{uuid4().hex[:10]}",
                    kind="direction",
                    title=text,
                    summary=request.summary.strip() or "Added after discussion.",
                    parent_id=question.id if question else None,
                    status="active",
                    promise="unassessed",
                    evidence_strength="none",
                )
            )
        elif request.kind == "way-to-test":
            parent_id = requested_parent.id if requested_parent else (direction.id if direction else None)
            workspace.nodes.append(
                ResearchNode(
                    id=f"test-{uuid4().hex[:10]}",
                    kind="approach",
                    title=text,
                    summary=request.summary.strip() or "Added after discussion.",
                    parent_id=parent_id,
                    status="active",
                    promise="unassessed",
                    evidence_strength="none",
                    current_stage="minimal-probe",
                )
            )
        return save_with_policy(workspace)

    @app.post("/api/workspaces/{workspace_id}/protocol-decisions", response_model=ProjectSnapshot)
    def decide_protocol_stage(
        workspace_id: str, request: ProtocolDecisionRequest
    ) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        node = next((item for item in workspace.nodes if item.id == request.node_id), None)
        if not node or node.kind != "approach":
            raise HTTPException(status_code=404, detail="Way to test this idea not found.")
        profile = protocols[node.protocol_id or workspace.protocol_id]
        current = node.current_stage or profile.stages[0].id
        target = next_stage(profile, current) if request.action == "promote" else current
        if request.action == "promote" and target is None:
            raise HTTPException(status_code=409, detail="This idea is already at the largest testing level.")
        if request.action == "stop":
            node.status = "dormant"
        elif request.action in {"revise", "redirect"}:
            node.status = "active"
        if request.action == "promote" and target:
            node.current_stage = target
        decision = ProtocolDecision(
            id=f"decision-{uuid4().hex[:10]}",
            node_id=node.id,
            package_id=request.package_id,
            from_stage=current,
            action=request.action,
            to_stage=target if request.action == "promote" else None,
            rationale=request.rationale,
        )
        workspace.decisions.append(decision)
        return save_with_policy(workspace)

    @app.post("/api/workspaces/{workspace_id}/plans", response_model=ProjectSnapshot)
    def create_plan(workspace_id: str, request: WorkPackageRequest) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        approach = next(
            (node for node in workspace.nodes if node.id == request.approach_id and node.kind == "approach"),
            None,
        )
        if not approach:
            raise HTTPException(status_code=404, detail="Choose a way to test an idea first.")
        profile = protocols[approach.protocol_id or workspace.protocol_id]
        stage_id = request.stage or approach.current_stage or profile.stages[0].id
        stage = next((item for item in profile.stages if item.id == stage_id), profile.stages[0])
        package = WorkPackage(
            id=f"plan-{uuid4().hex[:10]}",
            approach_id=approach.id,
            title=request.title.strip() or approach.title,
            stage=stage.id,
            goal=approach.title,
            why_now=approach.summary,
            budget=stage.budget,
            work_kind=approach.next_work_kind,
            idea_guidance=approach.agent_guidance,
            ask_before=approach.ask_before,
        )
        workspace.packages.append(package)
        return store.save(workspace)

    @app.patch("/api/workspaces/{workspace_id}/plans/{package_id}", response_model=ProjectSnapshot)
    def update_plan(
        workspace_id: str, package_id: str, patch: WorkPackagePatch
    ) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        package = next((item for item in workspace.packages if item.id == package_id), None)
        if not package:
            raise HTTPException(status_code=404, detail="Plan not found.")
        if package.status != "draft":
            raise HTTPException(status_code=409, detail="Approved plans cannot be edited. Make a new plan instead.")
        for field, value in patch.model_dump(exclude_none=True).items():
            setattr(package, field, value)
        package.updated_at = now_iso()
        return store.save(workspace)

    @app.post("/api/workspaces/{workspace_id}/plans/{package_id}/approve", response_model=ProjectSnapshot)
    def approve_plan(workspace_id: str, package_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        package = next((item for item in workspace.packages if item.id == package_id), None)
        if not package:
            raise HTTPException(status_code=404, detail="Plan not found.")
        if package.status != "draft":
            raise HTTPException(status_code=409, detail="This plan has already been approved.")
        required = {
            "goal": package.goal,
            "steps": package.instructions,
            "what to measure": package.measure,
            "command": package.command,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise HTTPException(status_code=422, detail=f"Complete these fields first: {', '.join(missing)}.")
        package.status = "ready"
        package.sealed_at = now_iso()
        package.rules_version_id = workspace.active_rules_version_id
        return store.save(workspace)

    @app.post("/api/workspaces/{workspace_id}/plans/{package_id}/run", response_model=ProjectSnapshot)
    def run_plan(workspace_id: str, package_id: str) -> ProjectSnapshot:
        try:
            runner.start(workspace_id, package_id)
        except RunFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return workspace_or_404(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/runs/{attempt_id}/cancel", response_model=ProjectSnapshot)
    def cancel_run(workspace_id: str, attempt_id: str) -> ProjectSnapshot:
        try:
            runner.cancel(workspace_id, attempt_id)
        except RunFailure as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return workspace_or_404(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/runs/{attempt_id}/review", response_model=ProjectSnapshot)
    def review_result(
        workspace_id: str, attempt_id: str, request: ResultReviewRequest
    ) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        attempt = next((item for item in workspace.attempts if item.id == attempt_id), None)
        if not attempt:
            raise HTTPException(status_code=404, detail="Run not found.")
        if attempt.status not in {"finished", "failed", "cancelled"}:
            raise HTTPException(status_code=409, detail="Wait until the run ends before reviewing it.")
        if any(review.attempt_id == attempt_id for review in workspace.reviews):
            raise HTTPException(status_code=409, detail="This run has already been reviewed.")
        review = ResultReview(
            id=f"review-{uuid4().hex[:10]}",
            attempt_id=attempt_id,
            **request.model_dump(),
        )
        workspace.reviews.append(review)
        package = next((item for item in workspace.packages if item.id == attempt.package_id), None)
        node = next(
            (item for item in workspace.nodes if package and item.id == package.approach_id),
            None,
        )
        if node and request.next_step == "park":
            node.status = "dormant"
        elif node and request.next_step == "go-deeper":
            profile = protocols[node.protocol_id or workspace.protocol_id]
            target = next_stage(profile, node.current_stage or profile.stages[0].id)
            if target:
                node.current_stage = target
        return save_with_policy(workspace)

    @app.post("/api/workspaces/{workspace_id}/rules/drafts", response_model=ProjectSnapshot)
    def create_rules_draft(workspace_id: str, request: RulesDraftRequest) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        next_version_number = max((version.version for version in workspace.rules_versions), default=0) + 1
        draft = RulesVersion(
            id=f"rules-v{next_version_number}",
            version=next_version_number,
            parent_id=workspace.active_rules_version_id,
            rules=request.rules,
        )
        workspace.rules_versions.append(draft)
        return store.save(workspace)

    @app.post("/api/workspaces/{workspace_id}/rules/{version_id}/check", response_model=ProjectSnapshot)
    def check_rules_version(workspace_id: str, version_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        version = next((item for item in workspace.rules_versions if item.id == version_id), None)
        if not version:
            raise HTTPException(status_code=404, detail="Rules version not found.")
        version.problems = check_rules(version)
        version.checked_at = now_iso()
        version.status = "checked" if not version.problems else "draft"
        return store.save(workspace)

    @app.post("/api/workspaces/{workspace_id}/rules/{version_id}/use", response_model=ProjectSnapshot)
    def activate_rules_version(workspace_id: str, version_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        version = next((item for item in workspace.rules_versions if item.id == version_id), None)
        if not version:
            raise HTTPException(status_code=404, detail="Rules version not found.")
        if version.status not in {"checked", "active", "retired"} or version.problems:
            raise HTTPException(status_code=422, detail="Check these rules and fix any problems before using them.")
        for item in workspace.rules_versions:
            if item.status == "active":
                item.status = "retired"
        version.status = "active"
        version.activated_at = now_iso()
        workspace.active_rules_version_id = version.id
        return save_with_policy(workspace)

    @app.post("/api/workspaces/{workspace_id}/policy/sync", response_model=ProjectSnapshot)
    def sync_workspace_policy(workspace_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        return save_with_policy(workspace)

    @app.get("/api/workspaces/{workspace_id}/harness", response_model=HarnessInfo)
    def get_harness(workspace_id: str) -> HarnessInfo:
        return workspace_or_404(workspace_id).harness

    @app.post("/api/workspaces/{workspace_id}/harness/update", response_model=ProjectSnapshot)
    def update_workspace_harness(workspace_id: str) -> ProjectSnapshot:
        workspace = workspace_or_404(workspace_id)
        try:
            workspace.harness = update_harness(workspace.root)
        except HarnessFailure as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return save_with_policy(workspace)

    @app.get(
        "/api/workspaces/{workspace_id}/terminals",
        response_model=list[TerminalSessionInfo],
    )
    def list_terminal_sessions(workspace_id: str) -> list[TerminalSessionInfo]:
        workspace_or_404(workspace_id)
        return terminals.list(workspace_id)

    @app.post(
        "/api/workspaces/{workspace_id}/terminals",
        response_model=TerminalSessionInfo,
    )
    def create_terminal_session(
        workspace_id: str, request: TerminalCreateRequest
    ) -> TerminalSessionInfo:
        workspace = workspace_or_404(workspace_id)
        if request.node_id and not any(node.id == request.node_id for node in workspace.nodes):
            raise HTTPException(status_code=404, detail="Selected idea not found.")
        if request.kind == "research":
            existing = next(
                (
                    session
                    for session in terminals.list(workspace.id)
                    if session.kind == "research" and session.status == "active"
                ),
                None,
            )
            if existing:
                return existing
        try:
            return terminals.create(
                workspace.id,
                workspace.root,
                request.node_id,
                request.agent_prompt,
                request.kind,
            )
        except TerminalFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/terminals/{session_id}")
    def close_terminal_session(session_id: str) -> dict[str, str]:
        try:
            terminals.close(session_id)
        except TerminalFailure as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "closed"}

    @app.websocket("/api/terminals/{session_id}/ws")
    async def terminal_socket(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if not terminals.get(session_id):
            await websocket.close(code=4404, reason="Terminal not found.")
            return
        if not terminals.acquire_input(session_id):
            await websocket.close(code=4409, reason="This terminal is already open somewhere else.")
            return

        async def send_output() -> None:
            while True:
                data = terminals.read(session_id)
                if data:
                    await websocket.send_bytes(data)
                elif terminals.get(session_id) and terminals.get(session_id).status == "exited":
                    await websocket.send_text("\r\n[terminal ended]\r\n")
                    return
                else:
                    await asyncio.sleep(0.03)

        async def receive_input() -> None:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data is not None:
                    terminals.write(session_id, data)
                    continue
                text = message.get("text") or ""
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    terminals.write(session_id, text.encode())
                    continue
                if payload.get("type") == "resize":
                    terminals.resize(
                        session_id,
                        int(payload.get("columns", 100)),
                        int(payload.get("rows", 28)),
                    )
                elif payload.get("type") == "input":
                    terminals.write(session_id, str(payload.get("data", "")).encode())

        sender = asyncio.create_task(send_output())
        receiver = asyncio.create_task(receive_input())
        try:
            done, pending = await asyncio.wait(
                {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
        except (WebSocketDisconnect, TerminalFailure, RuntimeError):
            pass
        finally:
            terminals.release_input(session_id)

    return app


app = create_app()
