import type {
  AgentRule,
  ProtocolProfile,
  StageAction,
  TerminalSessionInfo,
  Workspace,
  WorkPackage,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function listWorkspaces(): Promise<Workspace[]> {
  return request("/api/workspaces");
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}`);
}

export function listProtocols(): Promise<ProtocolProfile[]> {
  return request("/api/protocols");
}

export function importWorkspace(path: string): Promise<Workspace> {
  return request("/api/workspaces/import", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function patchNode(
  workspaceId: string,
  nodeId: string,
  patch: Record<string, string>,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/nodes/${nodeId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function decideStage(
  workspaceId: string,
  nodeId: string,
  action: StageAction,
  rationale: string,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/protocol-decisions`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId, action, rationale }),
  });
}

export function addNote(
  workspaceId: string,
  text: string,
  kind: "idea" | "way-to-test" | "note" | "question",
  parentId?: string | null,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/notes`, {
    method: "POST",
    body: JSON.stringify({ text, kind, parent_id: parentId ?? null }),
  });
}

export function createPlan(
  workspaceId: string,
  approachId: string,
  title: string,
  stage: string,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/plans`, {
    method: "POST",
    body: JSON.stringify({ approach_id: approachId, title, stage }),
  });
}

export function updatePlan(
  workspaceId: string,
  planId: string,
  patch: Partial<WorkPackage>,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/plans/${planId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function approvePlan(workspaceId: string, planId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/plans/${planId}/approve`, { method: "POST" });
}

export function runPlan(workspaceId: string, planId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/plans/${planId}/run`, { method: "POST" });
}

export function cancelRun(workspaceId: string, runId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/runs/${runId}/cancel`, { method: "POST" });
}

export function reviewRun(
  workspaceId: string,
  runId: string,
  review: {
    followed_plan: "yes" | "no" | "unsure";
    trust_result: "yes" | "no" | "unsure";
    what_it_means: string;
    next_step: "go-deeper" | "run-again" | "change-test" | "try-another" | "park";
    notes: string;
    keep_code: boolean;
  },
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/runs/${runId}/review`, {
    method: "POST",
    body: JSON.stringify(review),
  });
}

export function createRulesDraft(workspaceId: string, rules: AgentRule[]): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/rules/drafts`, {
    method: "POST",
    body: JSON.stringify({ rules }),
  });
}

export function checkRules(workspaceId: string, versionId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/rules/${versionId}/check`, { method: "POST" });
}

export function useRules(workspaceId: string, versionId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/rules/${versionId}/use`, { method: "POST" });
}

export function listTerminals(workspaceId: string): Promise<TerminalSessionInfo[]> {
  return request(`/api/workspaces/${workspaceId}/terminals`);
}

export function createTerminal(
  workspaceId: string,
  nodeId: string | null,
): Promise<TerminalSessionInfo> {
  return request(`/api/workspaces/${workspaceId}/terminals`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId }),
  });
}

export function closeTerminal(sessionId: string): Promise<{ status: string }> {
  return request(`/api/terminals/${sessionId}`, { method: "DELETE" });
}
