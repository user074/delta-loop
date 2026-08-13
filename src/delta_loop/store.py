from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import ProjectSnapshot, ProtocolDecision
from .research_map import ensure_research_links


class WorkspaceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._workspaces: dict[str, ProjectSnapshot] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._workspaces = {
            item["id"]: ProjectSnapshot.model_validate(item) for item in data.get("workspaces", [])
        }
        links_changed = False
        for workspace in self._workspaces.values():
            links_changed = ensure_research_links(workspace) or links_changed
        if links_changed:
            self._save()

    def _save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            payload = {"workspaces": [workspace.model_dump(mode="json") for workspace in self.list()]}
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.path)

    def list(self) -> list[ProjectSnapshot]:
        with self._lock:
            return sorted(self._workspaces.values(), key=lambda item: item.imported_at, reverse=True)

    def get(self, workspace_id: str) -> ProjectSnapshot | None:
        with self._lock:
            return self._workspaces.get(workspace_id)

    def put(self, workspace: ProjectSnapshot) -> ProjectSnapshot:
        with self._lock:
            previous = self._workspaces.get(workspace.id)
            if previous:
                workspace.decisions = previous.decisions
                workspace.notes = previous.notes
                workspace.packages = previous.packages
                workspace.attempts = previous.attempts
                workspace.reviews = previous.reviews
                workspace.rules_versions = previous.rules_versions or workspace.rules_versions
                workspace.active_rules_version_id = (
                    previous.active_rules_version_id or workspace.active_rules_version_id
                )
                workspace.policy_schema_version = previous.policy_schema_version
                workspace.policy_file = previous.policy_file
                workspace.loop_file = previous.loop_file
                workspace.policy_synced_at = previous.policy_synced_at
                workspace.question_history = previous.question_history
                workspace.node_history = previous.node_history
                workspace.research_links = previous.research_links
                workspace.compute = previous.compute
                workspace.compute_inspection = previous.compute_inspection
                workspace.git_repository = previous.git_repository
                workspace.setup_status = previous.setup_status
                workspace.setup_summary = previous.setup_summary
                workspace.reference_repos = previous.reference_repos
                workspace.setup_constraints = previous.setup_constraints
                workspace.initialization = previous.initialization
                if previous.setup_summary:
                    workspace.nodes = previous.nodes
                if previous.question_history:
                    workspace.goal = previous.goal
                    question = next((node for node in workspace.nodes if node.kind == "question"), None)
                    if question:
                        question.title = previous.goal
                prior_nodes = {node.id: node for node in previous.nodes}
                imported_node_ids = {node.id for node in workspace.nodes}
                for node in workspace.nodes:
                    old = prior_nodes.get(node.id)
                    if old:
                        if node.kind != "question":
                            node.title = old.title
                            node.summary = old.summary
                            node.parent_id = old.parent_id
                        node.status = old.status
                        node.promise = old.promise
                        node.evidence_strength = old.evidence_strength
                        node.protocol_id = old.protocol_id
                        node.current_stage = old.current_stage
                        node.next_work_kind = old.next_work_kind
                        node.agent_guidance = old.agent_guidance
                        node.ask_before = old.ask_before
                        node.policy_updated_at = old.policy_updated_at
                workspace.nodes.extend(
                    node for node in previous.nodes if node.id not in imported_node_ids
                )
            ensure_research_links(workspace)
            self._workspaces[workspace.id] = workspace
            self._save()
            return workspace

    def save(self, workspace: ProjectSnapshot) -> ProjectSnapshot:
        with self._lock:
            ensure_research_links(workspace)
            self._workspaces[workspace.id] = workspace
            self._save()
            return workspace

    def add_decision(self, workspace_id: str, decision: ProtocolDecision) -> ProjectSnapshot:
        workspace = self._workspaces[workspace_id]
        workspace.decisions.append(decision)
        return self.save(workspace)
