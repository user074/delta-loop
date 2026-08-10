import type {
  AgentRule,
  TerminalSessionInfo,
  Workspace,
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

export function importWorkspace(path: string): Promise<Workspace> {
  return request("/api/workspaces/import", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function updateQuestion(
  workspaceId: string,
  goal: string,
  reason: string,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: JSON.stringify({ goal, reason }),
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
  agentPrompt?: string,
): Promise<TerminalSessionInfo> {
  return request(`/api/workspaces/${workspaceId}/terminals`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId, agent_prompt: agentPrompt ?? null }),
  });
}

export function closeTerminal(sessionId: string): Promise<{ status: string }> {
  return request(`/api/terminals/${sessionId}`, { method: "DELETE" });
}
