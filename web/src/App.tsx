import {
  Activity,
  ArrowRight,
  BookOpen,
  Check,
  CircleDot,
  Clock3,
  FileText,
  FlaskConical,
  GitBranch,
  Import,
  Layers3,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
  StopCircle,
  Target,
  X,
} from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { decideStage, importWorkspace, listProtocols, listWorkspaces, patchNode } from "./api";
import AddNoteModal from "./AddNoteModal";
import PlanPage from "./PlanPage";
import RulesDrawer from "./RulesDrawer";
import RunsPage from "./RunsPage";
import type {
  ProtocolProfile,
  ResearchNode,
  StageAction,
  Workspace,
} from "./types";

type View = "overview" | "ideas" | "plan" | "runs";

const TerminalDock = lazy(() => import("./TerminalDock"));

const navItems: Array<{ id: View; label: string; icon: typeof BookOpen }> = [
  { id: "overview", label: "Overview", icon: BookOpen },
  { id: "ideas", label: "Ideas", icon: GitBranch },
  { id: "plan", label: "Plan", icon: FileText },
  { id: "runs", label: "Runs", icon: Activity },
];

const actionLabels: Record<StageAction, string> = {
  promote: "Go deeper",
  repeat: "Run again",
  revise: "Change the test",
  redirect: "Try another idea",
  stop: "Park it",
};

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "Question",
  direction: "Idea",
  approach: "Way to test it",
};

const statusLabels: Record<ResearchNode["status"], string> = {
  primary: "Main",
  active: "Working on",
  dormant: "Parked",
  closed: "Done",
};

const stageLabels: Record<string, string> = {
  "minimal-probe": "Quick test",
  "signal-confirmation": "Check the result",
  "full-investigation": "Full study",
  replicate: "Repeat the original",
  "controlled-variation": "Change one thing",
};

const runSignalLabels: Record<string, string> = {
  discriminating: "Clear difference",
  partial: "Some difference",
  null: "No useful difference",
  unknown: "Not reviewed",
};

const verdictLabels: Record<string, string> = {
  supports: "Supports the idea",
  contradicts: "Goes against the idea",
  unclear: "Still unclear",
  BLOCKER: "Could not finish",
};

function titleCase(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function relativeDate(value: string) {
  if (!value) return "No update date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

function App() {
  const [view, setView] = useState<View>("ideas");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [protocols, setProtocols] = useState<ProtocolProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importPath, setImportPath] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rationale, setRationale] = useState("");
  const [rulesOpen, setRulesOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);

  useEffect(() => {
    Promise.all([listWorkspaces(), listProtocols()])
      .then(([workspaces, profiles]) => {
        setProtocols(profiles);
        if (workspaces[0]) {
          setWorkspace(workspaces[0]);
          const firstApproach = workspaces[0].nodes.find((node) => node.kind === "approach");
          setSelectedId(firstApproach?.id ?? workspaces[0].nodes[0]?.id ?? null);
        } else {
          setImportOpen(true);
        }
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to load Delta Loop"));
  }, []);

  const selectedNode = useMemo(
    () => workspace?.nodes.find((node) => node.id === selectedId) ?? null,
    [selectedId, workspace],
  );
  const profile = protocols.find(
    (item) => item.id === (selectedNode?.protocol_id ?? workspace?.protocol_id),
  ) ?? protocols[0];
  const activeStage = profile?.stages.find((stage) => stage.id === selectedNode?.current_stage);
  const directionCount = workspace?.nodes.filter((node) => node.kind === "direction").length ?? 0;
  const approachCount = workspace?.nodes.filter((node) => node.kind === "approach").length ?? 0;

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
      setView("ideas");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleNodePatch(node: ResearchNode, field: string, value: string) {
    if (!workspace) return;
    setBusy(true);
    try {
      setWorkspace(await patchNode(workspace.id, node.id, { [field]: value }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDecision(action: StageAction) {
    if (!workspace || !selectedNode || selectedNode.kind !== "approach") return;
    setBusy(true);
    setError("");
    try {
      const updated = await decideStage(
        workspace.id,
        selectedNode.id,
        action,
        rationale.trim() || `${actionLabels[action]} choice recorded from the Ideas page.`,
      );
      setWorkspace(updated);
      setRationale("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  if (!workspace && !importOpen) {
    return <div className="loading-screen">Opening your research project…</div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark" aria-label="Delta Loop">
          <span>Δ</span>
        </div>
        <nav aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={view === item.id ? "nav-item active" : "nav-item"}
                key={item.id}
                onClick={() => setView(item.id)}
                title={item.label}
              >
                <Icon size={19} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <div className="local-dot" />
          <span>Local</span>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div>
            <div className="eyebrow">Delta Loop / {workspace?.name ?? "No project"}</div>
            <div className="topbar-title">
              <span className="status-dot" />
              {workspace?.status ?? "Waiting"}
              <span className="topbar-separator">·</span>
              Updated {relativeDate(workspace?.last_updated ?? "")}
            </div>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" onClick={() => setNoteOpen(true)}>
              <Plus size={16} /> Add idea or note
            </button>
            <button className="ghost-button" onClick={() => setRulesOpen(true)}>
              <ShieldCheck size={16} /> Agent rules
            </button>
            <button className="ghost-button" onClick={() => setImportOpen(true)}>
              <Import size={16} /> Open another project
            </button>
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => setError("")} aria-label="Dismiss error"><X size={16} /></button>
          </div>
        )}

        {workspace && (
          <>
            <section className="briefing-hero">
              <div className="hero-copy">
                <div className="section-kicker"><Sparkles size={14} /> Main question</div>
                <h1>{workspace.goal}</h1>
                <p>
                  {workspace.synthesis ||
                    "Choose an idea below to see why it matters, how strongly the results support it, and how much testing you want to do next."}
                </p>
              </div>
              <div className="hero-metrics">
                <div className="metric">
                  <span>Ideas tracked</span>
                  <strong>{directionCount}</strong>
                  <small>{approachCount} ways to test them</small>
                </div>
                <div className="metric">
                  <span>Tests run</span>
                  <strong>{workspace.runs.length + workspace.attempts.length}</strong>
                  <small>{workspace.attempts.filter((run) => run.status === "running").length} running now</small>
                </div>
                <div className="metric accent">
                  <span>Latest choice</span>
                  <strong>{workspace.decisions.length ? actionLabels[workspace.decisions.at(-1)!.action] : "None yet"}</strong>
                  <small>{workspace.decisions.length ? "saved in the project history" : "waiting for you"}</small>
                </div>
              </div>
            </section>

            {view === "ideas" ? (
              <section className="workspace-grid">
                <ResearchMap
                  workspace={workspace}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
                <DetailPanel
                  node={selectedNode}
                  workspace={workspace}
                  profile={profile}
                  profiles={protocols}
                  activeStage={activeStage}
                  rationale={rationale}
                  busy={busy}
                  onRationale={setRationale}
                  onDecision={handleDecision}
                  onPatch={handleNodePatch}
                />
              </section>
            ) : view === "overview" ? (
              <OverviewPage
                workspace={workspace}
                onOpenIdeas={(nodeId) => {
                  setSelectedId(nodeId);
                  setView("ideas");
                }}
              />
            ) : view === "plan" ? (
              <PlanPage
                workspace={workspace}
                protocols={protocols}
                selectedNode={selectedNode}
                onWorkspace={setWorkspace}
                onError={setError}
                onOpenRuns={() => setView("runs")}
              />
            ) : (
              <RunsPage workspace={workspace} onWorkspace={setWorkspace} onError={setError} />
            )}

            <Suspense fallback={<div className="terminal-loading">Opening terminal tools…</div>}>
              <TerminalDock workspace={workspace} selectedNode={selectedNode} onError={setError} />
            </Suspense>
          </>
        )}
      </main>

      {importOpen && (
        <div className="modal-backdrop" role="presentation">
          <form className="import-card" onSubmit={handleImport}>
            <button
              type="button"
              className="modal-close"
              aria-label="Close import"
              onClick={() => workspace && setImportOpen(false)}
            >
              <X size={18} />
            </button>
            <div className="import-icon"><Import size={22} /></div>
            <div className="section-kicker">Open an existing project</div>
            <h2>Choose your research folder</h2>
            <p>
              Choose a local folder containing <code>STATE.md</code>. Delta Loop reads it but does not change your
              original project files.
            </p>
            <label htmlFor="project-path">Project folder</label>
            <input
              id="project-path"
              autoFocus
              value={importPath}
              onChange={(event) => setImportPath(event.target.value)}
              placeholder="/path/to/research-project"
            />
            {error && <div className="form-error">{error}</div>}
            <button className="primary-button" disabled={!importPath.trim() || busy}>
              {busy ? <RefreshCw className="spin" size={17} /> : <ArrowRight size={17} />}
              {busy ? "Reading project…" : "Open project"}
            </button>
          </form>
        </div>
      )}
      {workspace && (
        <>
          <AddNoteModal
            open={noteOpen}
            workspace={workspace}
            selectedNode={selectedNode}
            onClose={() => setNoteOpen(false)}
            onWorkspace={setWorkspace}
            onSelect={setSelectedId}
            onError={setError}
          />
          <RulesDrawer
            open={rulesOpen}
            workspace={workspace}
            onClose={() => setRulesOpen(false)}
            onWorkspace={setWorkspace}
            onError={setError}
          />
        </>
      )}
    </div>
  );
}

function OverviewPage({
  workspace,
  onOpenIdeas,
}: {
  workspace: Workspace;
  onOpenIdeas: (nodeId: string) => void;
}) {
  const mainIdea =
    workspace.nodes.find((node) => node.kind === "direction" && node.status === "primary") ??
    workspace.nodes.find((node) => node.kind === "direction");
  const mainTest =
    workspace.nodes.find((node) => node.kind === "approach" && node.parent_id === mainIdea?.id && node.status === "primary") ??
    workspace.nodes.find((node) => node.kind === "approach" && node.parent_id === mainIdea?.id);
  const parked = workspace.nodes.filter((node) => node.kind === "approach" && node.status === "dormant");
  const notes = [
    ...workspace.notes.slice().reverse().map((note) => note.text),
    ...workspace.scratch,
  ].slice(0, 4);

  return (
    <section className="overview-page">
      <div className="overview-heading">
        <div className="section-kicker"><BookOpen size={14} /> Project overview</div>
        <h2>What needs your attention</h2>
        <p>Start here when you return to the project and want to know what happened and what to do next.</p>
      </div>

      <div className="overview-grid">
        <article className="overview-card next-card">
          <div className="card-label"><Target size={14} /> Main idea to work on</div>
          {mainIdea ? (
            <>
              <h3>{mainIdea.title}</h3>
              <p>{mainIdea.summary || "No explanation has been added yet."}</p>
              {mainTest && <p className="current-test"><strong>Current way to test it:</strong> {mainTest.title}</p>}
              <div className="plain-summary-row">
                <span>{titleCase(mainIdea.promise)} potential</span>
                <span>{titleCase(mainIdea.evidence_strength)} support</span>
                {mainTest && <span>{stageLabels[mainTest.current_stage ?? ""] ?? "Testing level not chosen"}</span>}
              </div>
              <button className="open-idea-button" onClick={() => onOpenIdeas(mainTest?.id ?? mainIdea.id)}>
                Open this idea <ArrowRight size={15} />
              </button>
            </>
          ) : (
            <p>No ideas have been added yet.</p>
          )}
        </article>

        <article className="overview-card">
          <div className="card-label"><FlaskConical size={14} /> Recent tests</div>
          <div className="simple-list">
            {workspace.runs.length ? workspace.runs.slice(-3).reverse().map((run) => (
              <div className="simple-list-row" key={run.id}>
                <div>
                  <strong>{run.id}</strong>
                  <p>{run.delta}</p>
                </div>
                <span>{runSignalLabels[run.signal] ?? titleCase(run.signal)}</span>
                <small>{verdictLabels[run.verdict] ?? titleCase(run.verdict)}</small>
              </div>
            )) : <p className="empty-copy">No tests have been recorded yet.</p>}
          </div>
        </article>

        <article className="overview-card">
          <div className="card-label"><BookOpen size={14} /> Notes to remember</div>
          <div className="notes-list">
            {notes.length ? notes.map((note, index) => (
              <p key={`${index}-${note}`}>{note}</p>
            )) : <p className="empty-copy">No open notes.</p>}
          </div>
        </article>

        <article className="overview-card small-card">
          <div className="card-label"><Pause size={14} /> Parked ways to test</div>
          <strong>{parked.length}</strong>
          <p>Tests saved for later instead of treated as failures.</p>
        </article>

        <article className="overview-card small-card">
          <div className="card-label"><Clock3 size={14} /> Choices saved</div>
          <strong>{workspace.decisions.length}</strong>
          <p>Your reasons for going deeper, trying again, changing, or stopping.</p>
        </article>
      </div>
    </section>
  );
}

function ResearchMap({
  workspace,
  selectedId,
  onSelect,
}: {
  workspace: Workspace;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const question = workspace.nodes.find((node) => node.kind === "question");
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const directionIds = new Set(directions.map((node) => node.id));
  return (
    <div className="research-panel">
      <div className="panel-header">
        <div>
          <div className="section-kicker"><Route size={14} /> Idea map</div>
          <h2>Ideas and ways to test them</h2>
        </div>
        <span className="map-count">{directions.length} ideas · {approaches.length} ways to test</span>
      </div>

      <div className="research-map">
        {question && (
          <NodeCard node={question} selected={selectedId === question.id} onSelect={onSelect} compact />
        )}
        <div className="map-connector"><span /></div>
        <div className="direction-grid">
          {directions.map((direction, directionIndex) => {
            const children = approaches.filter(
              (approach) => approach.parent_id === direction.id ||
                (directionIndex === 0 && !directionIds.has(approach.parent_id ?? "")),
            );
            return (
              <div className="direction-column" key={direction.id}>
                <NodeCard node={direction} selected={selectedId === direction.id} onSelect={onSelect} direction />
                <div className="direction-child-line" />
                <div className="direction-approaches">
                  {children.length ? children.map((approach) => (
                    <NodeCard
                      key={approach.id}
                      node={approach}
                      selected={selectedId === approach.id}
                      onSelect={onSelect}
                    />
                  )) : <div className="empty-branch">No ways to test this idea yet.</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function NodeCard({
  node,
  selected,
  onSelect,
  compact = false,
  direction = false,
}: {
  node: ResearchNode;
  selected: boolean;
  onSelect: (id: string) => void;
  compact?: boolean;
  direction?: boolean;
}) {
  return (
    <button
      className={`node-card ${selected ? "selected" : ""} ${compact ? "compact" : ""} ${direction ? "direction" : ""}`}
      onClick={() => onSelect(node.id)}
    >
      <div className="node-topline">
        <span className={`node-kind ${node.kind}`}>
          {node.kind === "question" ? <Target size={13} /> : node.kind === "direction" ? <Route size={13} /> : <FlaskConical size={13} />}
          {nodeKindLabels[node.kind]}
        </span>
        <span className={`status-label ${node.status}`}>{statusLabels[node.status]}</span>
      </div>
      <h3>{node.title}</h3>
      {node.summary && <p>{node.summary}</p>}
      {node.kind === "approach" && (
        <div className="node-signals">
          <span><i className={`signal promise-${node.promise}`} /> {titleCase(node.promise)} potential</span>
          <span><i className={`signal evidence-${node.evidence_strength}`} /> {titleCase(node.evidence_strength)} support</span>
        </div>
      )}
      {node.current_stage && (
        <div className="stage-chip"><Layers3 size={12} /> {stageLabels[node.current_stage] ?? titleCase(node.current_stage)}</div>
      )}
    </button>
  );
}

function DetailPanel({
  node,
  workspace,
  profile,
  profiles,
  activeStage,
  rationale,
  busy,
  onRationale,
  onDecision,
  onPatch,
}: {
  node: ResearchNode | null;
  workspace: Workspace;
  profile?: ProtocolProfile;
  profiles: ProtocolProfile[];
  activeStage?: ProtocolProfile["stages"][number];
  rationale: string;
  busy: boolean;
  onRationale: (value: string) => void;
  onDecision: (action: StageAction) => void;
  onPatch: (node: ResearchNode, field: string, value: string) => void;
}) {
  if (!node) return <aside className="detail-panel empty">Choose an idea from the map.</aside>;
  const claim = workspace.claims.find((item) => item.id === node.target_claim_id);
  const stageIndex = profile?.stages.findIndex((stage) => stage.id === node.current_stage) ?? -1;
  return (
    <aside className="detail-panel">
      <div className="detail-scroll">
        <div className="detail-heading">
          <div className="section-kicker">Selected {nodeKindLabels[node.kind].toLowerCase()}</div>
          <h2>{node.title}</h2>
          {node.summary && <p>{node.summary}</p>}
        </div>

        <div className="signal-controls">
          <label>
            <span>Are you working on it?</span>
            <select value={node.status} onChange={(event) => onPatch(node, "status", event.target.value)}>
              <option value="primary">Main focus</option>
              <option value="active">Working on it</option>
              <option value="dormant">Parked for now</option>
              <option value="closed">Done</option>
            </select>
          </label>
          <label>
            <span>How useful could it be?</span>
            <select value={node.promise} onChange={(event) => onPatch(node, "promise", event.target.value)}>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="unassessed">Not rated</option>
            </select>
          </label>
          <label>
            <span>Support from results</span>
            <select value={node.evidence_strength} onChange={(event) => onPatch(node, "evidence_strength", event.target.value)}>
              <option value="strong">Strong</option>
              <option value="mixed">Mixed</option>
              <option value="weak">Weak</option>
              <option value="none">No support yet</option>
            </select>
          </label>
        </div>

        {claim && (
          <div className="claim-card">
            <div className="card-label"><CircleDot size={14} /> Idea this test is checking</div>
            <p>{claim.statement}</p>
            <div className="confidence-row">
              <span>{claim.status === "active" ? "Still being tested" : titleCase(claim.status)}</span>
              <span>{claim.confidence == null ? "Not rated yet" : `${Math.round(claim.confidence * 100)}% sure`}</span>
            </div>
          </div>
        )}

        {node.kind === "approach" && profile && (
          <div className="protocol-card">
            <label className="testing-style-field">
              <span>How should this idea be tested?</span>
              <select
                value={profile.id}
                onChange={(event) => onPatch(node, "protocol_id", event.target.value)}
              >
                {profiles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <small>{profile.description}</small>
            </label>
            <div className="protocol-title">
              <div>
                <div className="card-label"><Layers3 size={14} /> How much testing to do</div>
                <h3>{profile.name}</h3>
              </div>
              <span>version {profile.version}</span>
            </div>
            <div className="stage-list">
              {profile.stages.map((stage, index) => {
                const state = index < stageIndex ? "done" : index === stageIndex ? "current" : "future";
                return (
                  <div className={`protocol-stage ${state}`} key={stage.id}>
                    <div className="stage-marker">{state === "done" ? <Check size={12} /> : index + 1}</div>
                    <div>
                      <strong>{stage.name}</strong>
                      <span>{stage.budget} amount of work</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {activeStage && (
              <div className="stage-detail">
                <p>{activeStage.purpose}</p>
                <div><strong>What to do</strong>{activeStage.scope}</div>
                <div><strong>What it tells you</strong>{activeStage.permitted_evidence}</div>
              </div>
            )}
            <label className="rationale-field">
              <span>Why are you making this choice?</span>
              <textarea
                value={rationale}
                onChange={(event) => onRationale(event.target.value)}
                placeholder="For example: the quick test showed a clear difference, so it is worth checking again."
                rows={3}
              />
            </label>
            <div className="decision-actions">
              <button className="promote" disabled={busy || stageIndex === profile.stages.length - 1} onClick={() => onDecision("promote")}>
                <Play size={14} /> Go deeper
              </button>
              <button disabled={busy} onClick={() => onDecision("repeat")}><RefreshCw size={14} /> Run again</button>
              <button disabled={busy} onClick={() => onDecision("revise")}><GitBranch size={14} /> Change test</button>
              <button className="stop" disabled={busy} onClick={() => onDecision("stop")}><StopCircle size={14} /> Park it</button>
            </div>
          </div>
        )}

        {workspace.decisions.filter((decision) => decision.node_id === node.id).length > 0 && (
          <div className="decision-history">
            <div className="card-label"><Clock3 size={14} /> Past choices</div>
            {workspace.decisions.filter((decision) => decision.node_id === node.id).slice().reverse().map((decision) => (
              <div className="decision-row" key={decision.id}>
                <span>{actionLabels[decision.action]}</span>
                <p>{decision.rationale}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

export default App;
