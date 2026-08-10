export type NodeKind = "question" | "direction" | "approach";
export type NodeStatus = "primary" | "active" | "dormant" | "closed";
export type StageAction = "promote" | "repeat" | "revise" | "redirect" | "stop";

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
}
