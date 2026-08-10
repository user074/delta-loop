import { ArrowRight, BookOpen, GitBranch, Import, RefreshCw, ShieldCheck, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { getWorkspace, importWorkspace, listWorkspaces } from "./api";
import type { DiscussionRequest } from "./discussions";
import { generalPolicyDiscussion } from "./discussions";
import HomePage from "./HomePage";
import PolicyPage from "./PolicyPage";
import ResearchPage from "./ResearchPage";
import RulesDrawer from "./RulesDrawer";
import type { Workspace } from "./types";

type View = "home" | "research" | "policy";

const TerminalDock = lazy(() => import("./TerminalDock"));

const navItems = [
  { id: "home" as const, label: "Home", icon: BookOpen },
  { id: "research" as const, label: "Research", icon: GitBranch },
  { id: "policy" as const, label: "Policy", icon: ShieldCheck },
];

function relativeDate(value: string) {
  if (!value) return "No update date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

export default function App() {
  const [view, setView] = useState<View>("home");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importPath, setImportPath] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [discussion, setDiscussion] = useState<DiscussionRequest | null>(null);

  useEffect(() => {
    listWorkspaces()
      .then((workspaces) => {
        if (workspaces[0]) {
          setWorkspace(workspaces[0]);
          const firstApproach = workspaces[0].nodes.find((node) => node.kind === "approach");
          setSelectedId(firstApproach?.id ?? workspaces[0].nodes[0]?.id ?? null);
        } else {
          setImportOpen(true);
        }
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to open Delta Loop."));
  }, []);

  const selectedNode = useMemo(
    () => workspace?.nodes.find((node) => node.id === selectedId) ?? null,
    [selectedId, workspace],
  );

  const openDiscussion = useCallback((request: Omit<DiscussionRequest, "id">) => {
    if (request.nodeId) setSelectedId(request.nodeId);
    setDiscussion({ ...request, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!workspace?.id) return;
    const timer = window.setInterval(() => {
      getWorkspace(workspace.id).then(setWorkspace).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [workspace?.id]);

  async function handleImport(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const imported = await importWorkspace(importPath);
      setWorkspace(imported);
      const firstApproach = imported.nodes.find((node) => node.kind === "approach");
      setSelectedId(firstApproach?.id ?? imported.nodes[0]?.id ?? null);
      setImportOpen(false);
      setView("home");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open the project.");
    } finally {
      setBusy(false);
    }
  }

  if (!workspace && !importOpen) return <div className="loading-screen">Opening your research project…</div>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark" aria-label="Delta Loop"><span>Δ</span></div>
        <nav aria-label="Main pages">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button className={view === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setView(item.id)} title={item.label}>
                <Icon size={19} strokeWidth={1.8} /><span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-foot"><div className="local-dot" /><span>Local</span></div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div>
            <div className="eyebrow">Delta Loop / {workspace?.name ?? "No project"}</div>
            <div className="topbar-title"><span className="status-dot" />{workspace?.status ?? "Waiting"}<span className="topbar-separator">·</span>Updated {relativeDate(workspace?.last_updated ?? "")}</div>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" onClick={() => setImportOpen(true)}><Import size={16} /> Open another project</button>
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={16} /></button></div>}

        {workspace && (
          <>
            {view === "home" ? (
              <HomePage
                workspace={workspace}
                onWorkspace={setWorkspace}
                onError={setError}
                onOpenResearch={(nodeId) => { setSelectedId(nodeId); setView("research"); }}
                onDiscuss={openDiscussion}
              />
            ) : view === "research" ? (
              <ResearchPage
                workspace={workspace}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onOpenPolicy={(nodeId) => { setSelectedId(nodeId); setView("policy"); }}
                onDiscuss={openDiscussion}
              />
            ) : (
              <PolicyPage
                workspace={workspace}
                selectedNode={selectedNode}
                onSelect={setSelectedId}
                onEditGeneral={() => setRulesOpen(true)}
                onDiscuss={openDiscussion}
              />
            )}

            <Suspense fallback={<div className="terminal-loading">Opening terminal…</div>}>
              <TerminalDock workspace={workspace} selectedNode={selectedNode} discussion={discussion} onError={setError} />
            </Suspense>
          </>
        )}
      </main>

      {importOpen && (
        <div className="modal-backdrop" role="presentation">
          <form className="import-card" onSubmit={handleImport}>
            <button type="button" className="modal-close" aria-label="Close import" onClick={() => workspace && setImportOpen(false)}><X size={18} /></button>
            <div className="import-icon"><Import size={22} /></div>
            <div className="section-kicker">Open an existing project</div>
            <h2>Choose your research folder</h2>
            <p>Choose a local folder containing <code>STATE.md</code>. Delta Loop reads the research records and writes its active rules to <code>.delta-loop/POLICY.md</code>.</p>
            <label htmlFor="project-path">Project folder</label>
            <input id="project-path" autoFocus value={importPath} onChange={(event) => setImportPath(event.target.value)} placeholder="/path/to/research-project" />
            {error && <div className="form-error">{error}</div>}
            <button className="primary-button" disabled={!importPath.trim() || busy}>
              {busy ? <RefreshCw className="spin" size={17} /> : <ArrowRight size={17} />}{busy ? "Reading project…" : "Open project"}
            </button>
          </form>
        </div>
      )}

      {workspace && (
        <RulesDrawer
          open={rulesOpen}
          workspace={workspace}
          onClose={() => setRulesOpen(false)}
          onWorkspace={setWorkspace}
          onError={setError}
          onDiscuss={() => {
            setRulesOpen(false);
            openDiscussion(generalPolicyDiscussion(workspace));
          }}
        />
      )}
    </div>
  );
}
