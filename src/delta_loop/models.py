from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


NodeKind = Literal["question", "direction", "approach"]
ResearchRelation = Literal[
    "explores",
    "tests",
    "supports",
    "challenges",
    "informs",
    "depends-on",
    "related",
]
NodeStatus = Literal["primary", "active", "dormant", "closed"]
Promise = Literal["high", "medium", "low", "unassessed"]
EvidenceStrength = Literal["strong", "mixed", "weak", "none"]
StageAction = Literal["promote", "repeat", "revise", "redirect", "stop"]
PackageStatus = Literal["draft", "ready", "running", "finished", "failed", "cancelled"]
AttemptStatus = Literal["starting", "running", "finished", "failed", "cancelled"]
WorkKind = Literal[
    "quick-test",
    "replicate",
    "literature-review",
    "compare-explanations",
    "ablation",
    "full-study",
    "research-engineering",
]
RuleCategory = Literal[
    "loop",
    "checkpoint",
    "project",
    "git",
    "hardware",
    "data",
    "resources",
    "temporary",
]
HarnessStatus = Literal[
    "missing",
    "current",
    "modified",
    "behind",
    "ahead",
    "diverged",
    "unversioned",
    "unknown",
]
TerminalKind = Literal["shell", "discussion", "research"]
ComputeKind = Literal["local", "ssh"]
ComputeStatus = Literal["unchecked", "ready", "unreachable", "needs-setup"]
GitRepositoryState = Literal["unchecked", "ready", "not-repository", "unreachable"]
ProjectSetupStatus = Literal["needs-setup", "ready"]
ProjectSource = Literal["local", "remote"]
InitializationStatus = Literal["pending", "complete", "imported"]
PermissionMode = Literal["manual", "scoped", "full"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Claim(BaseModel):
    id: str
    statement: str
    status: str
    confidence: float | None = None
    evidence: str = ""
    updated_at: str = ""


class RunRecord(BaseModel):
    id: str
    delta: str
    signal: str
    verdict: str
    claim_id: str | None = None
    link: str | None = None


class ResearchNode(BaseModel):
    id: str
    kind: NodeKind
    title: str
    summary: str = ""
    parent_id: str | None = None
    status: NodeStatus = "active"
    promise: Promise = "unassessed"
    evidence_strength: EvidenceStrength = "none"
    target_claim_id: str | None = None
    protocol_id: str | None = None
    current_stage: str | None = None
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    next_work_kind: WorkKind = "quick-test"
    agent_guidance: str = ""
    ask_before: str = ""
    policy_updated_at: str = ""


class ResearchLink(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship: ResearchRelation
    note: str = ""
    created_at: str = Field(default_factory=now_iso)


class QuestionRevision(BaseModel):
    previous: str
    current: str
    reason: str = ""
    created_at: str = Field(default_factory=now_iso)


class ResearchNodeRevision(BaseModel):
    id: str
    node_id: str
    node_kind: NodeKind
    changes: dict[str, str]
    reason: str = ""
    created_at: str = Field(default_factory=now_iso)


class ProtocolStage(BaseModel):
    id: str
    name: str
    purpose: str
    scope: str
    permitted_evidence: str
    gate: str
    recommended_template: str = "ablation"
    budget: str


class ProtocolProfile(BaseModel):
    id: str
    version: int
    name: str
    description: str
    stages: list[ProtocolStage]


class ProtocolDecision(BaseModel):
    id: str
    node_id: str
    package_id: str | None = None
    from_stage: str
    action: StageAction
    to_stage: str | None = None
    rationale: str
    created_at: str = Field(default_factory=now_iso)


class QuickNote(BaseModel):
    id: str
    text: str
    kind: Literal["idea", "way-to-test", "note", "question"] = "idea"
    parent_id: str | None = None
    created_at: str = Field(default_factory=now_iso)


class WorkPackage(BaseModel):
    id: str
    approach_id: str
    title: str
    stage: str = "minimal-probe"
    goal: str = ""
    why_now: str = ""
    instructions: str = ""
    inputs: str = ""
    comparison: str = ""
    measure: str = ""
    expected: str = ""
    limits: str = ""
    do_not_change: str = ""
    command: str = ""
    budget: str = "Small"
    status: PackageStatus = "draft"
    version: int = 1
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    sealed_at: str | None = None
    rules_version_id: str | None = None
    work_kind: WorkKind = "quick-test"
    idea_guidance: str = ""
    ask_before: str = ""


class Attempt(BaseModel):
    id: str
    package_id: str
    command: list[str]
    working_directory: str
    record_directory: str = ""
    handoff_file: str = ""
    output_directory: str = ""
    status: AttemptStatus = "starting"
    pid: int | None = None
    started_at: str = Field(default_factory=now_iso)
    finished_at: str | None = None
    exit_code: int | None = None
    output: list[str] = Field(default_factory=list)
    error: str | None = None
    executor: ComputeKind = "local"
    compute_name: str = "This computer"
    remote_host: str = ""
    remote_record_directory: str = ""
    remote_output_directory: str = ""
    last_checked_at: str = ""


class ResultReview(BaseModel):
    id: str
    attempt_id: str
    followed_plan: Literal["yes", "no", "unsure"]
    trust_result: Literal["yes", "no", "unsure"]
    what_it_means: str = ""
    next_step: Literal["go-deeper", "run-again", "change-test", "try-another", "park"]
    notes: str = ""
    keep_code: bool = False
    created_at: str = Field(default_factory=now_iso)


class AgentRule(BaseModel):
    id: str
    title: str
    instruction: str
    category: RuleCategory = "project"
    when: str = "Always"
    scope: str = "Entire project"
    expires_when: str = ""
    loop_level: Literal["stage", "step"] = "step"
    loop_parent_id: str = ""
    loop_step_ids: list[str] = Field(default_factory=list)
    source_label: str = ""
    enabled: bool = True
    cannot_override: bool = False


class RulesVersion(BaseModel):
    id: str
    version: int
    status: Literal["draft", "checked", "active", "retired"] = "draft"
    parent_id: str | None = None
    rules: list[AgentRule]
    problems: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    checked_at: str | None = None
    activated_at: str | None = None


class HarnessInfo(BaseModel):
    source_url: str = "https://github.com/user074/delta-research.git"
    path: str = ""
    revision: str = ""
    upstream_revision: str = ""
    branch: str = ""
    status: HarnessStatus = "unknown"
    detail: str = "Harness status has not been checked."
    local_changes: bool = False
    commits_ahead: int = 0
    commits_behind: int = 0
    official_source: bool = True


class TerminalSessionInfo(BaseModel):
    id: str
    workspace_id: str
    node_id: str | None = None
    working_directory: str
    kind: TerminalKind = "shell"
    title: str = "Terminal"
    persistent: bool = False
    status: Literal["active", "exited", "lost"] = "active"
    created_at: str = Field(default_factory=now_iso)
    last_active_at: str = Field(default_factory=now_iso)


class ComputeConfig(BaseModel):
    configured: bool = False
    kind: ComputeKind = "local"
    name: str = "This computer"
    ssh_host: str = ""
    project_path: str = ""
    run_path: str = "~/.delta-loop/runs"
    setup_command: str = ""
    gpu_devices: str = ""
    max_parallel: int = Field(default=1, ge=1, le=16)
    status: ComputeStatus = "unchecked"
    status_message: str = "Choose this computer or a remote server before starting work."
    last_checked_at: str = ""
    detected_python: str = ""
    detected_git: str = ""
    detected_gpus: list[str] = Field(default_factory=list)


class ComputeConfigRequest(BaseModel):
    kind: ComputeKind
    name: str = ""
    ssh_host: str = ""
    project_path: str = ""
    run_path: str = "~/.delta-loop/runs"
    setup_command: str = ""
    gpu_devices: str = ""
    max_parallel: int = Field(default=1, ge=1, le=16)


class ComputeCheckResult(BaseModel):
    status: ComputeStatus
    message: str
    host: str = ""
    project_path: str = ""
    run_path: str = ""
    project_exists: bool = False
    run_path_exists: bool = False
    python: str = ""
    git: str = ""
    gpus: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=now_iso)


class ComputeInspectRequest(BaseModel):
    kind: ComputeKind = "ssh"
    ssh_host: str = ""
    project_path: str = ""
    run_path: str = "~/.delta-loop/runs"


class ComputeInspection(BaseModel):
    host: str
    inspected_at: str = Field(default_factory=now_iso)
    hostname: str = ""
    operating_system: str = ""
    shell: str = ""
    home_path: str = ""
    project_path: str = ""
    project_exists: bool = False
    project_writable: bool = False
    run_path: str = ""
    run_parent_writable: bool = False
    top_level_files: list[str] = Field(default_factory=list)
    has_readme: bool = False
    has_state: bool = False
    has_infra: bool = False
    dependency_files: list[str] = Field(default_factory=list)
    python_path: str = ""
    python_version: str = ""
    environment_tools: list[str] = Field(default_factory=list)
    environment_candidates: list[str] = Field(default_factory=list)
    scheduler: str = "none"
    scheduler_tools: list[str] = Field(default_factory=list)
    gpus: list[str] = Field(default_factory=list)
    cpu: str = ""
    memory: str = ""
    project_storage: str = ""
    home_storage: str = ""
    git_branch: str = ""
    git_remote: str = ""
    git_status: str = ""
    notes: list[str] = Field(default_factory=list)


class ComputeProfile(BaseModel):
    id: str
    kind: ComputeKind
    name: str
    ssh_host: str = ""
    gpu_devices: str = ""
    max_parallel: int = Field(default=1, ge=1, le=16)
    last_checked_at: str = ""
    detected_git: str = ""
    hostname: str = ""
    operating_system: str = ""
    scheduler: str = "none"
    gpus: list[str] = Field(default_factory=list)
    cpu: str = ""
    memory: str = ""
    environment_tools: list[str] = Field(default_factory=list)
    source_projects: list[str] = Field(default_factory=list)


class GitRepositoryStatus(BaseModel):
    state: GitRepositoryState = "unchecked"
    message: str = "The research repository has not been checked yet."
    checked_at: str = ""
    location: str = ""
    project_path: str = ""
    repository_found: bool = False
    repository_root: str = ""
    branch: str = ""
    remote_name: str = "origin"
    remote_url: str = ""
    github_url: str = ""
    upstream: str = ""
    changed_files: list[str] = Field(default_factory=list)
    changes_truncated: bool = False
    ahead: int = 0
    behind: int = 0
    last_commit: str = ""


class RemoteProjectInspectRequest(BaseModel):
    ssh_host: str
    project_path: str


class RemoteProjectInspection(BaseModel):
    host: str
    project_path: str
    project_exists: bool = False
    top_level_files: list[str] = Field(default_factory=list)
    total_files: int = 0
    inventory_truncated: bool = False
    entry_points: list[str] = Field(default_factory=list)
    file_types: dict[str, int] = Field(default_factory=dict)
    documentation: dict[str, str] = Field(default_factory=dict)
    git_branch: str = ""
    git_remote: str = ""
    git_status: list[str] = Field(default_factory=list)
    recent_commits: list[str] = Field(default_factory=list)
    inspected_at: str = Field(default_factory=now_iso)


class RemoteProjectReadRequest(BaseModel):
    ssh_host: str
    project_path: str
    paths: list[str] = Field(min_length=1, max_length=12)


class RemoteProjectReading(BaseModel):
    host: str
    project_path: str
    files: dict[str, str] = Field(default_factory=dict)
    problems: dict[str, str] = Field(default_factory=dict)
    read_at: str = Field(default_factory=now_iso)


class ProjectInitialization(BaseModel):
    status: InitializationStatus = "imported"
    project_understanding: str = ""
    prior_work: list[str] = Field(default_factory=list)
    reusable_inputs: list[str] = Field(default_factory=list)
    success_condition: str = ""
    stop_condition: str = ""
    budget: str = ""
    permission_mode: PermissionMode = "scoped"
    environment_verified: bool = False
    git_reviewed: bool = False
    literature_gate: bool = True
    completed_at: str = ""
    source_revision: str = ""
    initialization_file: str = ""
    infra_file: str = ""
    synthesis_file: str = ""
    literature_index_file: str = ""


class ProjectSnapshot(BaseModel):
    id: str
    root: str
    name: str
    goal: str
    status: str = "active"
    last_updated: str = ""
    imported_at: str = Field(default_factory=now_iso)
    source_files: list[str] = Field(default_factory=list)
    synthesis: str = ""
    claims: list[Claim] = Field(default_factory=list)
    runs: list[RunRecord] = Field(default_factory=list)
    nodes: list[ResearchNode] = Field(default_factory=list)
    research_links: list[ResearchLink] = Field(default_factory=list)
    scratch: list[str] = Field(default_factory=list)
    protocol_id: str = "fast-signal-first"
    protocol_version: int = 1
    decisions: list[ProtocolDecision] = Field(default_factory=list)
    notes: list[QuickNote] = Field(default_factory=list)
    packages: list[WorkPackage] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    reviews: list[ResultReview] = Field(default_factory=list)
    rules_versions: list[RulesVersion] = Field(default_factory=list)
    active_rules_version_id: str | None = None
    policy_schema_version: int = 0
    policy_file: str = ""
    loop_file: str = ""
    policy_synced_at: str = ""
    harness: HarnessInfo = Field(default_factory=HarnessInfo)
    question_history: list[QuestionRevision] = Field(default_factory=list)
    node_history: list[ResearchNodeRevision] = Field(default_factory=list)
    compute: ComputeConfig = Field(default_factory=ComputeConfig)
    compute_inspection: ComputeInspection | None = None
    git_repository: GitRepositoryStatus = Field(default_factory=GitRepositoryStatus)
    setup_status: ProjectSetupStatus = "ready"
    setup_summary: str = ""
    reference_repos: list[str] = Field(default_factory=list)
    setup_constraints: list[str] = Field(default_factory=list)
    project_source: ProjectSource = "local"
    initialization: ProjectInitialization = Field(default_factory=ProjectInitialization)


class ImportRequest(BaseModel):
    path: str


class ProjectSetupRequest(BaseModel):
    summary: str
    reference_repos: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    prior_work: list[str] = Field(default_factory=list)
    reusable_inputs: list[str] = Field(default_factory=list)
    success_condition: str = ""
    stop_condition: str = ""
    budget: str = ""
    permission_mode: PermissionMode = "scoped"
    environment_verified: bool = False
    git_reviewed: bool = False


class WorkspacePatch(BaseModel):
    goal: str
    reason: str = ""


class NodePatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    parent_id: str | None = None
    status: NodeStatus | None = None
    promise: Promise | None = None
    evidence_strength: EvidenceStrength | None = None
    protocol_id: str | None = None
    current_stage: str | None = None
    next_work_kind: WorkKind | None = None
    agent_guidance: str | None = None
    ask_before: str | None = None
    reason: str = ""


class ResearchLinkRequest(BaseModel):
    source_id: str
    target_id: str
    relationship: ResearchRelation
    note: str = ""


class ProtocolDecisionRequest(BaseModel):
    node_id: str
    package_id: str | None = None
    action: StageAction
    rationale: str = ""


class QuickNoteRequest(BaseModel):
    text: str
    kind: Literal["idea", "way-to-test", "note", "question"] = "idea"
    parent_id: str | None = None
    summary: str = ""


class WorkPackageRequest(BaseModel):
    approach_id: str
    title: str
    stage: str = "minimal-probe"


class WorkPackagePatch(BaseModel):
    title: str | None = None
    stage: str | None = None
    goal: str | None = None
    why_now: str | None = None
    instructions: str | None = None
    inputs: str | None = None
    comparison: str | None = None
    measure: str | None = None
    expected: str | None = None
    limits: str | None = None
    do_not_change: str | None = None
    command: str | None = None
    budget: str | None = None


class ResultReviewRequest(BaseModel):
    followed_plan: Literal["yes", "no", "unsure"]
    trust_result: Literal["yes", "no", "unsure"]
    what_it_means: str = ""
    next_step: Literal["go-deeper", "run-again", "change-test", "try-another", "park"]
    notes: str = ""
    keep_code: bool = False


class RulesDraftRequest(BaseModel):
    rules: list[AgentRule]


class TerminalCreateRequest(BaseModel):
    node_id: str | None = None
    agent_prompt: str | None = Field(default=None, max_length=8000)
    kind: TerminalKind = "shell"
    title: str = Field(default="", max_length=160)
