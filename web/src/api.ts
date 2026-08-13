import type {
  AgentRule,
  ComputeConfig,
  TerminalSessionInfo,
  Workspace,
} from "./types";

async function request<T>(path: string, init?: RequestInit, timeoutMs = 60000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(body?.detail ?? `Request failed (${response.status})`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("Delta Loop is not responding. If it runs on a server, reconnect the SSH connection and try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function listWorkspaces(): Promise<Workspace[]> {
  return request("/api/workspaces", undefined, 8000);
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}`, undefined, 8000);
}

export function importWorkspace(path: string): Promise<Workspace> {
  return request("/api/workspaces/import", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function createRemoteWorkspace(): Promise<Workspace> {
  return request("/api/workspaces/remote", { method: "POST" });
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

export function updateCompute(
  workspaceId: string,
  compute: Pick<
    ComputeConfig,
    | "kind"
    | "name"
    | "ssh_host"
    | "project_path"
    | "run_path"
    | "setup_command"
    | "gpu_devices"
    | "max_parallel"
  >,
): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/compute`, {
    method: "PUT",
    body: JSON.stringify(compute),
  });
}

export function checkCompute(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/compute/check`, {
    method: "POST",
  });
}

export function resetCompute(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/compute/reset`, {
    method: "POST",
  });
}

export function checkGit(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}/git/check`, {
    method: "POST",
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
  return request(`/api/workspaces/${workspaceId}/terminals`, undefined, 8000);
}

export function createTerminal(
  workspaceId: string,
  nodeId: string | null,
  agentPrompt?: string,
  kind: TerminalSessionInfo["kind"] = "shell",
  title = "",
): Promise<TerminalSessionInfo> {
  return request(`/api/workspaces/${workspaceId}/terminals`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId, agent_prompt: agentPrompt ?? null, kind, title }),
  });
}

export function closeTerminal(sessionId: string): Promise<{ status: string }> {
  return request(`/api/terminals/${sessionId}`, { method: "DELETE" });
}

export function closeAllTerminals(workspaceId: string): Promise<{ status: string; count: number }> {
  return request(`/api/workspaces/${workspaceId}/terminals`, { method: "DELETE" });
}
