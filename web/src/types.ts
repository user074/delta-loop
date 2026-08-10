export type NodeKind = "question" | "direction" | "approach";
export type NodeStatus = "primary" | "active" | "dormant" | "closed";
export type StageAction = "promote" | "repeat" | "revise" | "redirect" | "stop";
export type WorkKind =
  | "quick-test"
  | "replicate"
  | "literature-review"
  | "compare-explanations"
  | "ablation"
  | "full-study"
  | "research-engineering";

export interface Claim {
  id: string;
  statement: string;
  status: string;
  confidence: number | null;
  evidence: string;
  updated_at: string;
}

export interface RunRecord {
  id: string;
  delta: string;
  signal: string;
  verdict: string;
  claim_id: string | null;
  link: string | null;
}

export interface ResearchNode {
  id: string;
  kind: NodeKind;
  title: string;
  summary: string;
  parent_id: string | null;
  status: NodeStatus;
  promise: "high" | "medium" | "low" | "unassessed";
  evidence_strength: "strong" | "mixed" | "weak" | "none";
  target_claim_id: string | null;
  protocol_id: string | null;
  current_stage: string | null;
  outcome_counts: Record<string, number>;
  next_work_kind: WorkKind;
  agent_guidance: string;
  ask_before: string;
  policy_updated_at: string;
}

export interface QuestionRevision {
  previous: string;
  current: string;
  reason: string;
  created_at: string;
}

export interface ProtocolStage {
  id: string;
  name: string;
  purpose: string;
  scope: string;
  permitted_evidence: string;
  gate: string;
  recommended_template: string;
  budget: string;
}

export interface ProtocolProfile {
  id: string;
  version: number;
  name: string;
  description: string;
  stages: ProtocolStage[];
}

export interface ProtocolDecision {
  id: string;
  node_id: string;
  package_id: string | null;
  from_stage: string;
  action: StageAction;
  to_stage: string | null;
  rationale: string;
  created_at: string;
}

export interface QuickNote {
  id: string;
  text: string;
  kind: "idea" | "way-to-test" | "note" | "question";
  parent_id: string | null;
  created_at: string;
}

export interface WorkPackage {
  id: string;
  approach_id: string;
  title: string;
  stage: string;
  goal: string;
  why_now: string;
  instructions: string;
  inputs: string;
  comparison: string;
  measure: string;
  expected: string;
  limits: string;
  do_not_change: string;
  command: string;
  budget: string;
  status: "draft" | "ready" | "running" | "finished" | "failed" | "cancelled";
  version: number;
  created_at: string;
  updated_at: string;
  sealed_at: string | null;
  rules_version_id: string | null;
  work_kind: WorkKind;
  idea_guidance: string;
  ask_before: string;
}

export interface Attempt {
  id: string;
  package_id: string;
  command: string[];
  working_directory: string;
  record_directory: string;
  handoff_file: string;
  output_directory: string;
  status: "starting" | "running" | "finished" | "failed" | "cancelled";
  pid: number | null;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  output: string[];
  error: string | null;
}

export interface ResultReview {
  id: string;
  attempt_id: string;
  followed_plan: "yes" | "no" | "unsure";
  trust_result: "yes" | "no" | "unsure";
  what_it_means: string;
  next_step: "go-deeper" | "run-again" | "change-test" | "try-another" | "park";
  notes: string;
  keep_code: boolean;
  created_at: string;
}

export interface AgentRule {
  id: string;
  title: string;
  instruction: string;
  category: "loop" | "checkpoint" | "project" | "git" | "hardware" | "data" | "resources" | "temporary";
  when: string;
  scope: string;
  expires_when: string;
  loop_level: "stage" | "step";
  loop_parent_id: string;
  loop_step_ids: string[];
  source_label: string;
  enabled: boolean;
  cannot_override: boolean;
}

export interface RulesVersion {
  id: string;
  version: number;
  status: "draft" | "checked" | "active" | "retired";
  parent_id: string | null;
  rules: AgentRule[];
  problems: string[];
  created_at: string;
  checked_at: string | null;
  activated_at: string | null;
}

export interface TerminalSessionInfo {
  id: string;
  workspace_id: string;
  node_id: string | null;
  working_directory: string;
  status: "active" | "exited" | "lost";
  created_at: string;
  last_active_at: string;
}

export interface HarnessInfo {
  source_url: string;
  path: string;
  revision: string;
  upstream_revision: string;
  branch: string;
  status: "missing" | "current" | "modified" | "behind" | "ahead" | "diverged" | "unversioned" | "unknown";
  detail: string;
  local_changes: boolean;
  commits_ahead: number;
  commits_behind: number;
  official_source: boolean;
}

export interface Workspace {
  id: string;
  root: string;
  name: string;
  goal: string;
  status: string;
  last_updated: string;
  imported_at: string;
  source_files: string[];
  synthesis: string;
  claims: Claim[];
  runs: RunRecord[];
  nodes: ResearchNode[];
  scratch: string[];
  protocol_id: string;
  protocol_version: number;
  decisions: ProtocolDecision[];
  notes: QuickNote[];
  packages: WorkPackage[];
  attempts: Attempt[];
  reviews: ResultReview[];
  rules_versions: RulesVersion[];
  active_rules_version_id: string | null;
  policy_schema_version: number;
  policy_file: string;
  loop_file: string;
  policy_synced_at: string;
  harness: HarnessInfo;
  question_history: QuestionRevision[];
}
