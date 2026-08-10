from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


NodeKind = Literal["question", "direction", "approach"]
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


class QuestionRevision(BaseModel):
    previous: str
    current: str
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
    status: Literal["active", "exited", "lost"] = "active"
    created_at: str = Field(default_factory=now_iso)
    last_active_at: str = Field(default_factory=now_iso)


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


class ImportRequest(BaseModel):
    path: str


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
