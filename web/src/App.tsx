import { ArrowRight, BookOpen, GitBranch, Import, Play, RefreshCw, RotateCcw, Server, ShieldCheck, SquareTerminal, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { createRemoteWorkspace, getWorkspace, importWorkspace, listWorkspaces } from "./api";
import type { DiscussionRequest } from "./discussions";
import { generalPolicyDiscussion, projectSetupDiscussion, remoteProjectSetupDiscussion } from "./discussions";
import HomePage from "./HomePage";
import ComputePage from "./ComputePage";
import PolicyPage from "./PolicyPage";
import ResearchPage from "./ResearchPage";
import RulesDrawer from "./RulesDrawer";
import type { ResearchLaunchRequest, TerminalSessionInfo, Workspace } from "./types";

type View = "home" | "research" | "policy" | "compute";
type ImportMode = "choose" | "local";

const TerminalDock = lazy(() => import("./TerminalDock"));

const navItems = [
  { id: "home" as const, label: "Home", icon: BookOpen },
  { id: "research" as const, label: "Research", icon: GitBranch },
  { id: "policy" as const, label: "Policy", icon: ShieldCheck },
  { id: "compute" as const, label: "Compute", icon: Server },
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
  const [importMode, setImportMode] = useState<ImportMode>("choose");
  const [importPath, setImportPath] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [discussion, setDiscussion] = useState<DiscussionRequest | null>(null);
  const [researchStartRequest, setResearchStartRequest] = useState<ResearchLaunchRequest | null>(null);
  const [researchSession, setResearchSession] = useState<TerminalSessionInfo | null>(null);
  const [researchStarting, setResearchStarting] = useState(false);

  useEffect(() => {
    listWorkspaces()
      .then((workspaces) => {
        if (workspaces[0]) {
          setWorkspace(workspaces[0]);
          const firstApproach = workspaces[0].nodes.find((node) => node.kind === "approach");
          setSelectedId(firstApproach?.id ?? workspaces[0].nodes[0]?.id ?? null);
        } else {
          setImportMode("choose");
          setImportOpen(true);
        }
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to open Delta Loop."));
  }, []);

  const selectedNode = useMemo(
    () => workspace?.nodes.find((node) => node.id === selectedId) ?? null,
    [selectedId, workspace],
  );
  const projectNeedsSetup = workspace?.setup_status === "needs-setup";

  const openDiscussion = useCallback((request: Omit<DiscussionRequest, "id">) => {
    if (request.nodeId) setSelectedId(request.nodeId);
    setDiscussion({ ...request, id: Date.now() });
  }, []);

  const setupDiscussion = useCallback((project: Workspace) => (
    project.project_source === "remote"
      ? remoteProjectSetupDiscussion(project)
      : projectSetupDiscussion(project)
  ), []);

  const startOrOpenResearch = useCallback(() => {
    if (workspace?.setup_status === "needs-setup") {
      openDiscussion(setupDiscussion(workspace));
      return;
    }
    setResearchStarting(true);
    setResearchStartRequest((current) => ({
      id: (current?.id ?? 0) + 1,
      nodeId: view === "research" ? selectedNode?.id ?? null : null,
      sourcePage: view,
    }));
  }, [openDiscussion, selectedNode?.id, setupDiscussion, view, workspace]);

  const finishResearchStart = useCallback(() => setResearchStarting(false), []);
  const researchActive = researchSession?.status === "active";
  const researchStartedBefore = Boolean(researchSession);
  const hasVisualResearchFocus = view === "research" && Boolean(selectedNode);
  const researchActionLabel = researchStarting
    ? "Opening…"
    : projectNeedsSetup
      ? "Set up project"
    : researchActive
      ? "Open research"
      : researchStartedBefore
        ? hasVisualResearchFocus ? "Continue from selection" : "Continue research"
        : hasVisualResearchFocus ? "Start from selection" : "Start research";

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
      if (imported.setup_status === "needs-setup") {
        openDiscussion(setupDiscussion(imported));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open the project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoteProject() {
    setBusy(true);
    setError("");
    try {
      const created = await createRemoteWorkspace();
      setWorkspace(created);
      setSelectedId(created.nodes[0]?.id ?? null);
      setImportOpen(false);
      setView("home");
      openDiscussion(remoteProjectSetupDiscussion(created));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start remote setup.");
    } finally {
      setBusy(false);
    }
  }

  function openProjectChooser() {
    setImportMode("choose");
    setImportPath("");
    setError("");
    setImportOpen(true);
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
        <div className="sidebar-foot"><div className={!workspace?.compute.configured ? "local-dot unset" : "local-dot"} /><span>{!workspace?.compute.configured ? "Unset" : workspace.compute.kind === "ssh" ? "Remote work" : "Local work"}</span></div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="topbar-project-meta">
            <div className="eyebrow">Delta Loop / {workspace?.name ?? "No project"}</div>
            <div className="topbar-title"><span className="status-dot" />{workspace?.status ?? "Waiting"}<span className="topbar-separator">·</span>Updated {relativeDate(workspace?.last_updated ?? "")}</div>
          </div>
          <div className="topbar-actions">
            {workspace && (
              <button
                className={researchActive ? "topbar-research-button active" : "topbar-research-button"}
                disabled={researchStarting}
                onClick={startOrOpenResearch}
                aria-label={researchActionLabel}
                title={researchActive
                  ? "Watch the running research session"
                  : projectNeedsSetup
                    ? "Use Codex to understand and set up this existing project"
                  : hasVisualResearchFocus
                    ? `Start with the selected ${selectedNode?.kind}: ${selectedNode?.title}`
                    : "Start the agent with the full research map, active loop, and policy"}
              >
                {researchStarting ? <RotateCcw className="spin" size={16} /> : researchActive ? <SquareTerminal size={16} /> : researchStartedBefore ? <RotateCcw size={16} /> : <Play size={16} />}
                <span>{researchActionLabel}</span>
              </button>
            )}
            <button className="ghost-button" onClick={openProjectChooser}><Import size={16} /> Open another project</button>
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={16} /></button></div>}

        {workspace?.setup_status === "needs-setup" && (
          <section className="project-setup-banner">
            <div>
              <strong>Set up this project</strong>
              <p>{workspace.project_source === "remote"
                ? "Codex will inspect the repository on your server, propose the questions and idea map, check compute and Git, then save the agreed research starting point and rules."
                : "Codex will inspect this repository, propose the questions and idea map, check compute and Git, then save the agreed research starting point and rules."}</p>
            </div>
            <button onClick={() => openDiscussion(setupDiscussion(workspace))}><SquareTerminal size={15} /> Chat with Codex</button>
          </section>
        )}

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
            ) : view === "policy" ? (
              <PolicyPage
                workspace={workspace}
                selectedNode={selectedNode}
                onSelect={setSelectedId}
                onEditGeneral={() => setRulesOpen(true)}
                onDiscuss={openDiscussion}
              />
            ) : (
              <ComputePage
                workspace={workspace}
                onWorkspace={setWorkspace}
                onError={setError}
                onDiscuss={openDiscussion}
              />
            )}

            <Suspense fallback={<div className="terminal-loading">Opening terminal…</div>}>
              <TerminalDock
                workspace={workspace}
                selectedNode={selectedNode}
                discussion={discussion}
                researchStartRequest={researchStartRequest}
                onResearchSessionChange={setResearchSession}
                onResearchStartFinished={finishResearchStart}
                onError={setError}
              />
            </Suspense>
          </>
        )}
      </main>

      {importOpen && (
        <div className="modal-backdrop" role="presentation">
          {importMode === "choose" ? (
            <div className="import-card first-run-card">
              {workspace && <button type="button" className="modal-close" aria-label="Close project chooser" onClick={() => setImportOpen(false)}><X size={18} /></button>}
              <div className="import-icon"><Import size={22} /></div>
              <div className="section-kicker">Open an existing project</div>
              <h2>Where is your project?</h2>
              <p>Choose where the research code already lives. Delta Loop will help with the rest.</p>
              <div className="project-location-choices">
                <button type="button" className="project-location-choice" onClick={() => setImportMode("local")} disabled={busy}>
                  <span className="project-location-icon"><Import size={21} /></span>
                  <span><strong>This computer</strong><small>Choose a folder already on this computer.</small></span>
                  <ArrowRight size={18} />
                </button>
                <button type="button" className="project-location-choice" onClick={handleRemoteProject} disabled={busy}>
                  <span className="project-location-icon remote"><Server size={21} /></span>
                  <span><strong>Remote server</strong><small>Tell Codex which SSH connection and project folder to use.</small></span>
                  {busy ? <RefreshCw className="spin" size={18} /> : <ArrowRight size={18} />}
                </button>
              </div>
              {error && <div className="form-error">{error}</div>}
              <p className="first-run-note">During setup, Delta Loop reads only what it needs and does not change your research code.</p>
            </div>
          ) : (
            <form className="import-card" onSubmit={handleImport}>
              {workspace && <button type="button" className="modal-close" aria-label="Close import" onClick={() => setImportOpen(false)}><X size={18} /></button>}
              <button type="button" className="modal-back-button" onClick={() => { setImportMode("choose"); setError(""); }}>← Back</button>
              <div className="import-icon"><Import size={22} /></div>
              <div className="section-kicker">This computer</div>
              <h2>Choose your research folder</h2>
              <p>Any existing research folder works. Codex will help set it up if it has not used Delta Loop before.</p>
              <label htmlFor="project-path">Project folder</label>
              <input id="project-path" autoFocus value={importPath} onChange={(event) => setImportPath(event.target.value)} placeholder="/path/to/research-project" />
              {error && <div className="form-error">{error}</div>}
              <button className="primary-button" disabled={!importPath.trim() || busy}>
                {busy ? <RefreshCw className="spin" size={17} /> : <ArrowRight size={17} />}{busy ? "Reading project…" : "Open project"}
              </button>
            </form>
          )}
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
