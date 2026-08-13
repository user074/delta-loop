import { Activity, ArrowRight, BookOpen, CheckCircle2, CircleDot, Clock3, FileText, FlaskConical, GitBranch, Lightbulb, Link2, MessageSquareText, Minus, Pencil, Plus, Route, SearchCheck, ShieldCheck, Sparkles, Target, XCircle } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { addExperimentFromIdeaDiscussion, addFindingDiscussion, addFollowUpIdeaDiscussion, addIdeaFromQuestionDiscussion, addLiteratureReviewDiscussion, addResearchQuestionDiscussion, connectResearchNodeDiscussion, continueResearchFromNodeDiscussion, researchMapDiscussion, reviseResearchNodeDiscussion, type DiscussionRequest } from "./discussions";
import type { Attempt, ResearchLink, ResearchNode, Workspace, WorkPackage } from "./types";

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "Question",
  direction: "Idea",
  approach: "Work",
  finding: "Finding",
};

const statusLabels: Record<ResearchNode["status"], string> = {
  primary: "Main",
  active: "Active",
  dormant: "Parked",
  closed: "Done",
};

const workKindLabels: Record<string, string> = {
  "quick-test": "Quick test",
  replicate: "Repeat an earlier result",
  "literature-review": "Literature review",
  "compare-explanations": "Compare explanations",
  ablation: "Ablation",
  "full-study": "Full study",
  "research-engineering": "Research engineering",
};

const nextStepLabels: Record<string, string> = {
  "go-deeper": "Do a larger test",
  "run-again": "Repeat it",
  "change-test": "Change the test",
  "try-another": "Try another idea",
  park: "Park it",
};

const evidenceOutcomeLabels: Record<Workspace["reviews"][number]["evidence_outcome"], string> = {
  supports: "Supports idea",
  challenges: "Evidence against",
  inconclusive: "Inconclusive",
  invalid: "Invalid evidence",
  "not-applicable": "No evidence claim",
};

function isExecutionIssue(attempt: Attempt, review?: Workspace["reviews"][number]) {
  return ["blocked", "failed", "cancelled"].includes(attempt.status) || review?.execution_validity === "invalid";
}

const relationshipLabels: Record<Workspace["research_links"][number]["relationship"], string> = {
  explores: "explores",
  tests: "tests",
  produces: "produces",
  revises: "revises",
  "leads-to": "leads to",
  "alternative-to": "alternative to",
  supports: "supports",
  challenges: "challenges",
  informs: "informs",
  "depends-on": "depends on",
  related: "related",
};

function titleCase(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function countLabel(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

type MapLevel = 0 | 1 | 2;

const mapLevelLabels: Record<MapLevel, string> = {
  0: "Overview",
  1: "Working view",
  2: "Details",
};

function nodeTypeLabel(node: ResearchNode) {
  if (node.kind !== "approach") return nodeKindLabels[node.kind];
  return workKindLabels[node.next_work_kind] ?? "Research work";
}

function NodeTypeIcon({ node, size = 13 }: { node: ResearchNode; size?: number }) {
  if (node.kind === "question") return <Target size={size} />;
  if (node.kind === "direction") return <Lightbulb size={size} />;
  if (node.kind === "finding") return <Sparkles size={size} />;
  if (node.next_work_kind === "literature-review") return <BookOpen size={size} />;
  return <FlaskConical size={size} />;
}

export default function ResearchPage({
  workspace,
  selectedId,
  onSelect,
  onOpenPolicy,
  onDiscuss,
}: {
  workspace: Workspace;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
  onOpenPolicy: (nodeId: string) => void;
  onDiscuss: (request: Omit<DiscussionRequest, "id">) => void;
}) {
  const selected = workspace.nodes.find((node) => node.id === selectedId) ?? null;
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const toggleBranch = (nodeId: string) => setCollapsedIds((current) => {
    const next = new Set(current);
    if (next.has(nodeId)) next.delete(nodeId);
    else next.add(nodeId);
    return next;
  });
  return (
    <section className="workspace-grid">
      <ResearchMap
        workspace={workspace}
        selectedId={selectedId}
        onSelect={onSelect}
        onDiscuss={() => onDiscuss(researchMapDiscussion(selected))}
        onAddQuestion={() => onDiscuss(addResearchQuestionDiscussion())}
        collapsedIds={collapsedIds}
      />
      <ResearchDetail
        node={selected}
        workspace={workspace}
        onOpenPolicy={onOpenPolicy}
        onSelect={onSelect}
        onDiscuss={onDiscuss}
        collapsed={selected ? collapsedIds.has(selected.id) : false}
        hasLaterSteps={selected ? workspace.nodes.some((node) => node.parent_id === selected.id) : false}
        onToggleBranch={toggleBranch}
      />
    </section>
  );
}

function ResearchMap({ workspace, selectedId, onSelect, onDiscuss, onAddQuestion, collapsedIds }: { workspace: Workspace; selectedId: string | null; onSelect: (id: string) => void; onDiscuss: () => void; onAddQuestion: () => void; collapsedIds: Set<string> }) {
  const questions = workspace.nodes.filter((node) => node.kind === "question");
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const findings = workspace.nodes.filter((node) => node.kind === "finding");
  const [mapLevel, setMapLevel] = useState<MapLevel>(1);
  const canvasRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef(new Map<string, HTMLElement>());
  const [lines, setLines] = useState<Array<{ id: string; path: string; x: number; y: number; label: string; relationship: string; primary: boolean; connected: boolean }>>([]);
  const nodesById = useMemo(() => new Map(workspace.nodes.map((node) => [node.id, node])), [workspace.nodes]);

  const visibleNodes = useMemo(() => {
    const allowedByLevel = workspace.nodes.filter((node) => mapLevel > 0 || node.kind === "question" || node.kind === "direction");
    return allowedByLevel.filter((node) => {
      let parent = nodesById.get(node.parent_id ?? "");
      const seen = new Set<string>();
      while (parent && !seen.has(parent.id)) {
        if (collapsedIds.has(parent.id)) return false;
        seen.add(parent.id);
        parent = nodesById.get(parent.parent_id ?? "");
      }
      return true;
    });
  }, [collapsedIds, mapLevel, nodesById, workspace.nodes]);

  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const displayParents = useMemo(() => {
    const parents = new Map<string, { parent: ResearchNode; hiddenSteps: number }>();
    for (const node of visibleNodes) {
      let parent = nodesById.get(node.parent_id ?? "");
      let hiddenSteps = 0;
      const seen = new Set<string>();
      while (parent && !seen.has(parent.id)) {
        seen.add(parent.id);
        if (visibleIds.has(parent.id)) {
          parents.set(node.id, { parent, hiddenSteps });
          break;
        }
        hiddenSteps += 1;
        parent = nodesById.get(parent.parent_id ?? "");
      }
    }
    return parents;
  }, [nodesById, visibleIds, visibleNodes]);

  const columns = useMemo(() => {
    const depthCache = new Map<string, number>();
    const depthFor = (nodeId: string, visiting = new Set<string>()): number => {
      const cached = depthCache.get(nodeId);
      if (cached !== undefined) return cached;
      if (visiting.has(nodeId)) return 0;
      visiting.add(nodeId);
      const parent = displayParents.get(nodeId)?.parent;
      const depth = parent ? Math.min(8, depthFor(parent.id, visiting) + 1) : 0;
      depthCache.set(nodeId, depth);
      return depth;
    };
    const grouped = new Map<number, ResearchNode[]>();
    for (const node of visibleNodes) {
      const depth = depthFor(node.id);
      grouped.set(depth, [...(grouped.get(depth) ?? []), node]);
    }
    return [...grouped.entries()].sort(([a], [b]) => a - b).map(([depth, nodes]) => ({ depth, nodes }));
  }, [displayParents, visibleNodes]);

  const displayEdges = useMemo(() => {
    const primaryLinks = new Set<string>();
    const edges: Array<{ id: string; source_id: string; target_id: string; relationship: ResearchLink["relationship"]; label: string; primary: boolean }> = [];
    for (const node of visibleNodes) {
      const placement = displayParents.get(node.id);
      if (!placement) continue;
      const actual = workspace.research_links.find((link) => link.source_id === placement.parent.id && link.target_id === node.id);
      if (actual) primaryLinks.add(actual.id);
      edges.push({
        id: actual?.id ?? `path-${placement.parent.id}-${node.id}`,
        source_id: placement.parent.id,
        target_id: node.id,
        relationship: actual?.relationship ?? "leads-to",
        label: placement.hiddenSteps ? `${placement.hiddenSteps} hidden step${placement.hiddenSteps === 1 ? "" : "s"}` : relationshipLabels[actual?.relationship ?? "leads-to"],
        primary: true,
      });
    }
    for (const link of workspace.research_links) {
      if (!visibleIds.has(link.source_id) || !visibleIds.has(link.target_id) || primaryLinks.has(link.id)) continue;
      edges.push({ ...link, label: relationshipLabels[link.relationship], primary: false });
    }
    return edges;
  }, [displayParents, visibleIds, visibleNodes, workspace.research_links]);

  const focusedIds = useMemo(() => {
    if (!selectedId) return new Set(visibleIds);
    let visibleFocusId: string | null = selectedId;
    const seen = new Set<string>();
    while (visibleFocusId && !visibleIds.has(visibleFocusId) && !seen.has(visibleFocusId)) {
      seen.add(visibleFocusId);
      visibleFocusId = nodesById.get(visibleFocusId)?.parent_id ?? null;
    }
    if (!visibleFocusId) return new Set(visibleIds);
    const focused = new Set<string>([visibleFocusId]);
    let parent = displayParents.get(visibleFocusId)?.parent;
    while (parent && !focused.has(parent.id)) {
      focused.add(parent.id);
      parent = displayParents.get(parent.id)?.parent;
    }
    let frontier = new Set<string>([visibleFocusId]);
    while (frontier.size) {
      const next = new Set<string>();
      for (const [childId, placement] of displayParents) {
        if (frontier.has(placement.parent.id) && !focused.has(childId)) {
          focused.add(childId);
          next.add(childId);
        }
      }
      frontier = next;
    }
    for (const link of workspace.research_links) {
      if (link.source_id === visibleFocusId && visibleIds.has(link.target_id)) focused.add(link.target_id);
      if (link.target_id === visibleFocusId && visibleIds.has(link.source_id)) focused.add(link.source_id);
    }
    return focused;
  }, [displayParents, nodesById, selectedId, visibleIds, workspace.research_links]);

  useLayoutEffect(() => {
    const measure = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const bounds = canvas.getBoundingClientRect();
      setLines(displayEdges.flatMap((link) => {
        const source = cardRefs.current.get(link.source_id);
        const target = cardRefs.current.get(link.target_id);
        if (!source || !target) return [];
        const from = source.getBoundingClientRect();
        const to = target.getBoundingClientRect();
        const goesRight = to.left >= from.right;
        const goesLeft = from.left >= to.right;
        const x1 = (goesRight ? from.right : goesLeft ? from.left : from.left + from.width / 2) - bounds.left;
        const y1 = (goesRight || goesLeft ? from.top + from.height / 2 : from.bottom) - bounds.top;
        const x2 = (goesRight ? to.left : goesLeft ? to.right : to.left + to.width / 2) - bounds.left;
        const y2 = (goesRight || goesLeft ? to.top + to.height / 2 : to.top) - bounds.top;
        const bend = goesRight || goesLeft ? Math.max(42, Math.abs(x2 - x1) * 0.46) : 48;
        const path = goesRight
          ? `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
          : goesLeft
            ? `M ${x1} ${y1} C ${x1 - bend} ${y1}, ${x2 + bend} ${y2}, ${x2} ${y2}`
            : `M ${x1} ${y1} C ${x1 + bend} ${y1 + bend}, ${x2 + bend} ${y2 - bend}, ${x2} ${y2}`;
        return [{
          id: link.id,
          path,
          x: (x1 + x2) / 2,
          y: (y1 + y2) / 2,
          label: link.label,
          primary: link.primary,
          relationship: link.relationship,
          connected: focusedIds.has(link.source_id) && focusedIds.has(link.target_id),
        }];
      }));
    };
    const frame = window.requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    if (canvasRef.current) observer.observe(canvasRef.current);
    cardRefs.current.forEach((card) => observer.observe(card));
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [displayEdges, focusedIds, mapLevel, visibleNodes]);

  const setCardRef = (id: string) => (element: HTMLButtonElement | null) => {
    if (element) cardRefs.current.set(id, element);
    else cardRefs.current.delete(id);
  };
  return (
    <div className="research-panel">
      <div className="panel-header">
        <div><div className="section-kicker"><Route size={14} /> Research</div><h2>How the research developed</h2></div>
        <div className="research-header-actions">
          <span className="map-count">{countLabel(questions.length, "question")} · {countLabel(directions.length, "idea")} · {approaches.length} work · {countLabel(findings.length, "finding")}</span>
          <button className="map-add-button" onClick={onAddQuestion}><Plus size={14} /> Add question</button>
          <button className="discuss-button" onClick={onDiscuss}><MessageSquareText size={14} /> Chat about map</button>
        </div>
      </div>
      <div className="research-map">
        <div className="map-view-controls">
          <div className="map-zoom" aria-label="Map detail level">
            <button aria-label="Zoom out" title="Show less detail" disabled={mapLevel === 0} onClick={() => setMapLevel((level) => Math.max(0, level - 1) as MapLevel)}><Minus size={13} /></button>
            <span>{mapLevelLabels[mapLevel]}</span>
            <button aria-label="Zoom in" title="Show more detail" disabled={mapLevel === 2} onClick={() => setMapLevel((level) => Math.min(2, level + 1) as MapLevel)}><Plus size={13} /></button>
          </div>
          <small>{selectedId && !visibleIds.has(selectedId) ? "The selected item is hidden here. Zoom in to see it." : mapLevel === 0 ? "Questions and ideas only" : mapLevel === 1 ? "Questions, ideas, work, and findings" : "Full summaries, evidence, and run state"}</small>
        </div>
        <div className="graph-legend"><span><i className="graph-line hierarchy" /> Main path</span><span><i className="graph-line evidence" /> Other relationship</span><small>Select an item to follow its path. Hide later steps from the side panel.</small></div>
        <div className="research-graph-canvas" ref={canvasRef} style={{ minWidth: `${Math.max(columns.length, 1) * 245}px` }}>
          <svg className="research-links" aria-label="Research relationships">
            <defs><marker id="graph-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" /></marker></defs>
            {lines.map((line) => {
              const labelWidth = Math.max(38, line.label.length * 5.5 + 12);
              return <g key={line.id} className={`research-link ${line.primary ? "primary" : "cross-link"} ${line.relationship} ${line.connected ? "connected" : "muted"}`}>
                <path d={line.path} markerEnd="url(#graph-arrow)" />
                <rect x={line.x - labelWidth / 2} y={line.y - 8} width={labelWidth} height={16} rx={8} />
                <text x={line.x} y={line.y + 3}>{line.label}</text>
              </g>;
            })}
          </svg>
          <div className="research-columns research-trace-columns" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(210px, 1fr))` }}>
            {columns.map((column) => (
              <section className="research-column trace-step" key={column.depth}>
                <div className="research-column-title"><span>{column.depth === 0 ? "Starting points" : column.depth === 1 ? "Next step" : `${column.depth} steps later`}</span><small>{column.nodes.length}</small></div>
                <div className="research-column-cards">
                  {column.nodes.map((node) => (
                    <ResearchNodeCard
                      key={node.id}
                      node={node}
                      workspace={workspace}
                      selected={selectedId === node.id}
                      muted={Boolean(selectedId) && !focusedIds.has(node.id)}
                      mapLevel={mapLevel}
                      onSelect={onSelect}
                      cardRef={setCardRef(node.id)}
                    />
                  ))}
                </div>
              </section>
            ))}
            {!visibleNodes.length && <div className="empty-branch">No research-map items are visible at this level.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function attemptsFor(node: ResearchNode, workspace: Workspace) {
  const packageIds = new Set(workspace.packages.filter((plan) => plan.approach_id === node.id).map((plan) => plan.id));
  return workspace.attempts.filter((attempt) => packageIds.has(attempt.package_id));
}

function ResearchNodeCard({
  node,
  workspace,
  selected,
  muted = false,
  mapLevel = 1,
  onSelect,
  cardRef,
  compact = false,
  direction = false,
}: {
  node: ResearchNode;
  workspace: Workspace;
  selected: boolean;
  muted?: boolean;
  mapLevel?: MapLevel;
  onSelect: (id: string) => void;
  cardRef?: (element: HTMLButtonElement | null) => void;
  compact?: boolean;
  direction?: boolean;
}) {
  const contextApproaches = node.kind === "approach"
    ? [node]
    : node.kind === "direction"
      ? workspace.nodes.filter((item) => item.kind === "approach" && workspace.research_links.some((link) => link.source_id === node.id && link.target_id === item.id && link.relationship === "tests"))
      : [];
  const packageIds = new Set(
    workspace.packages.filter((plan) => contextApproaches.some((item) => item.id === plan.approach_id)).map((plan) => plan.id),
  );
  const attempts = workspace.attempts.filter((attempt) => packageIds.has(attempt.package_id));
  const running = attempts.filter((attempt) => attempt.status === "running" || attempt.status === "starting").length;
  const reviews = workspace.reviews.filter((review) => attempts.some((attempt) => attempt.id === review.attempt_id));
  const supports = reviews.filter((review) => review.evidence_outcome === "supports").length;
  const challenges = reviews.filter((review) => review.evidence_outcome === "challenges").length;
  const inconclusive = reviews.filter((review) => review.evidence_outcome === "inconclusive").length;
  const blocked = attempts.filter((attempt) => isExecutionIssue(attempt, reviews.find((review) => review.attempt_id === attempt.id))).length;
  const claimIds = new Set(contextApproaches.map((item) => item.target_claim_id).filter(Boolean));
  const historical = workspace.runs.filter((run) => run.claim_id && claimIds.has(run.claim_id)).length;
  return (
    <button ref={cardRef} className={`node-card kind-${node.kind} ${selected ? "selected" : ""} ${muted ? "muted" : ""} ${compact ? "compact" : ""} ${direction ? "direction" : ""}`} onClick={() => onSelect(node.id)}>
      <div className="node-topline">
        <span className={`node-kind ${node.kind}`}><NodeTypeIcon node={node} />{nodeTypeLabel(node)}</span>
        <span className={`status-label ${node.status}`}>{statusLabels[node.status]}</span>
      </div>
      <h3>{node.title}</h3>
      {mapLevel > 0 && node.summary && <p>{node.summary}</p>}
      {mapLevel === 2 && (node.kind === "approach" || node.kind === "finding") && (
        <>
          <div className="node-signals"><span><i className={`signal promise-${node.promise}`} /> {titleCase(node.promise)} potential</span><span><i className={`signal evidence-${node.evidence_strength}`} /> {titleCase(node.evidence_strength)} support</span></div>
        </>
      )}
      {mapLevel === 2 && node.kind === "approach" && (
        <div className="node-run-strip">
          {running > 0 && <span className="running">{running} running</span>}
          {supports > 0 && <span className="supports">{supports} supports</span>}
          {challenges > 0 && <span className="challenges">{challenges} evidence against</span>}
          {inconclusive > 0 && <span className="inconclusive">{inconclusive} inconclusive</span>}
          {blocked > 0 && <span className="blocked">{blocked} execution issue{blocked === 1 ? "" : "s"}</span>}
          {historical > 0 && <span>{historical} imported</span>}
          {!attempts.length && !historical && <span>Not tested</span>}
        </div>
      )}
    </button>
  );
}

function ResearchDetail({ node, workspace, onOpenPolicy, onSelect, onDiscuss, collapsed, hasLaterSteps, onToggleBranch }: { node: ResearchNode | null; workspace: Workspace; onOpenPolicy: (nodeId: string) => void; onSelect: (nodeId: string) => void; onDiscuss: (request: Omit<DiscussionRequest, "id">) => void; collapsed: boolean; hasLaterSteps: boolean; onToggleBranch: (nodeId: string) => void }) {
  if (!node) return <aside className="detail-panel empty">Choose a question, idea, work item, or finding from the map.</aside>;
  const claim = workspace.claims.find((item) => item.id === node.target_claim_id);
  const plans = node.kind === "approach" ? workspace.packages.filter((plan) => plan.approach_id === node.id) : [];
  const attempts = attemptsFor(node, workspace).slice().reverse();
  const historicalRuns = node.target_claim_id ? workspace.runs.filter((run) => run.claim_id === node.target_claim_id).slice().reverse() : [];
  const nodeHistory = workspace.node_history.filter((change) => change.node_id === node.id).slice().reverse();
  const connections = workspace.research_links.filter((link) => link.source_id === node.id || link.target_id === node.id);
  return (
    <aside className="detail-panel">
      <div className="detail-scroll">
        <div className="detail-heading"><div className="section-kicker">Selected {nodeTypeLabel(node).toLowerCase()}</div><h2>{node.title}</h2>{node.summary && <p>{node.summary}</p>}</div>

        <div className="research-item-actions">
          <button className="primary" onClick={() => onDiscuss(continueResearchFromNodeDiscussion(node))}><ArrowRight size={14} /><span><strong>Continue from here</strong><small>Decide whether the next step is an idea, review, experiment, finding, or another path</small></span></button>
          <div className="research-next-actions">
            {node.kind === "question" && <button onClick={() => onDiscuss(addIdeaFromQuestionDiscussion(node))}><Lightbulb size={13} /> Add idea</button>}
            {node.kind === "direction" && <button onClick={() => onDiscuss(addExperimentFromIdeaDiscussion(node))}><FlaskConical size={13} /> Add experiment</button>}
            {node.kind === "approach" && <button onClick={() => onDiscuss(addFindingDiscussion(node))}><SearchCheck size={13} /> Record finding</button>}
            {(node.kind === "finding" || node.kind === "approach") && <button onClick={() => onDiscuss(addFollowUpIdeaDiscussion(node))}><Lightbulb size={13} /> Follow-up idea</button>}
            <button onClick={() => onDiscuss(addLiteratureReviewDiscussion(node))}><BookOpen size={13} /> Literature review</button>
          </div>
          <div className="research-item-secondary-actions">
            <button onClick={() => onDiscuss(researchMapDiscussion(node))}><MessageSquareText size={13} /> Chat</button>
            <button onClick={() => onDiscuss(reviseResearchNodeDiscussion(node))}><Pencil size={13} /> Revise</button>
            <button onClick={() => onDiscuss(connectResearchNodeDiscussion(node))}><Link2 size={13} /> Connect</button>
          </div>
          {hasLaterSteps && <button className="branch-visibility-button" onClick={() => onToggleBranch(node.id)}><GitBranch size={13} /> {collapsed ? "Show later steps" : "Hide later steps"}</button>}
        </div>

        <div className="research-state-row">
          <span><strong>{statusLabels[node.status]}</strong> status</span>
          <span><strong>{titleCase(node.promise)}</strong> potential</span>
          <span><strong>{titleCase(node.evidence_strength)}</strong> support</span>
        </div>

        <div className="relationship-card">
          <div className="card-label"><Link2 size={14} /> Connected research</div>
          {connections.map((link) => {
            const outgoing = link.source_id === node.id;
            const other = workspace.nodes.find((item) => item.id === (outgoing ? link.target_id : link.source_id));
            if (!other) return null;
            return <button key={link.id} onClick={() => onSelect(other.id)}><span>{outgoing ? "To" : "From"} {nodeTypeLabel(other).toLowerCase()} · {relationshipLabels[link.relationship]}</span><strong>{other.title}</strong>{link.note && <small>{link.note}</small>}</button>;
          })}
          {!connections.length && <p>No relationships have been recorded for this item yet.</p>}
        </div>

        {node.kind === "approach" && (
          <div className="idea-policy-card">
            <div className="card-label"><ShieldCheck size={14} /> Policy for this work</div>
            <h3>{workKindLabels[node.next_work_kind] ?? titleCase(node.next_work_kind)}</h3>
            <p>{node.agent_guidance || "No special guidance has been recorded for this work yet. Chat with the agent about it."}</p>
            {node.ask_before && <small><strong>Stop only if:</strong> {node.ask_before}</small>}
            <button onClick={() => onOpenPolicy(node.id)}>Open policy <ArrowRight size={14} /></button>
          </div>
        )}

        {claim && <div className="claim-card"><div className="card-label"><CircleDot size={14} /> Idea this work is checking</div><p>{claim.statement}</p><div className="confidence-row"><span>{claim.status === "active" ? "Still being tested" : titleCase(claim.status)}</span><span>{claim.confidence == null ? "Not rated" : `${Math.round(claim.confidence * 100)}% sure`}</span></div></div>}

        {node.kind === "approach" && (
          <div className="attached-runs">
            <div className="card-label"><Activity size={14} /> Runs and results for this work</div>
            {attempts.map((attempt) => {
              const plan = plans.find((item) => item.id === attempt.package_id);
              const review = workspace.reviews.find((item) => item.attempt_id === attempt.id);
              return <RunStory key={attempt.id} attempt={attempt} plan={plan} review={review} />;
            })}
            {historicalRuns.map((run) => (
              <div className="run-story imported" key={run.id}>
                <div className="run-story-head"><FileText size={15} /><div><strong>{run.delta}</strong><span>Imported previous test</span></div><em>{titleCase(run.signal)}</em></div>
                <p><strong>Recorded result:</strong> {titleCase(run.verdict)}</p>
              </div>
            ))}
            {!attempts.length && !historicalRuns.length && <div className="no-attached-runs">No run or result review has been recorded for this work yet.</div>}
          </div>
        )}

        {workspace.decisions.some((decision) => decision.node_id === node.id) && (
          <div className="decision-history"><div className="card-label"><Clock3 size={14} /> Why the direction changed</div>{workspace.decisions.filter((decision) => decision.node_id === node.id).slice().reverse().map((decision) => <div className="decision-row" key={decision.id}><span>{titleCase(decision.action)}</span><p>{decision.rationale}</p></div>)}</div>
        )}

        {nodeHistory.length > 0 && (
          <div className="decision-history">
            <div className="card-label"><GitBranch size={14} /> How this {nodeTypeLabel(node).toLowerCase()} evolved</div>
            {nodeHistory.map((change) => (
              <div className="decision-row" key={change.id}>
                <span>{new Date(change.created_at).toLocaleDateString()}</span>
                {Object.entries(change.changes).map(([field, value]) => <p key={field}><strong>{titleCase(field)}:</strong> {value}</p>)}
                {change.reason && <p><strong>Why:</strong> {change.reason}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function RunStory({ attempt, plan, review }: { attempt: Attempt; plan?: WorkPackage; review?: Workspace["reviews"][number] }) {
  const endedBadly = isExecutionIssue(attempt, review);
  const status = attempt.status === "failed" || attempt.status === "blocked"
    ? "Execution blocked"
    : attempt.status === "cancelled"
      ? "Stopped"
      : titleCase(attempt.status);
  return (
    <div className={`run-story ${attempt.status}`}>
      <div className="run-story-head">
        {endedBadly ? <XCircle size={15} /> : attempt.status === "finished" ? <CheckCircle2 size={15} /> : <Activity size={15} />}
        <div><strong>{plan?.title ?? "Research work"}</strong><span>{status} · {plan ? workKindLabels[plan.work_kind] : ""}</span></div>
        {review && <em className={`evidence-${review.evidence_outcome}`}>{evidenceOutcomeLabels[review.evidence_outcome]}</em>}
      </div>
      {plan?.goal && <p><strong>Tested:</strong> {plan.goal}</p>}
      {plan?.instructions && <p><strong>Starting method:</strong> {plan.instructions}</p>}
      {attempt.execution_history.length > 0 && (
        <p><strong>Implementation:</strong> {attempt.execution_history.length + 1} tries inside this one research run. Latest change: {attempt.current_try_reason}</p>
      )}
      {review?.adaptations && <p><strong>How the method changed:</strong> {review.adaptations}</p>}
      {plan?.inputs && <p><strong>Data:</strong> {plan.inputs}</p>}
      {review && <p><strong>Execution:</strong> {titleCase(review.execution_validity)}</p>}
      <p><strong>Result:</strong> {review?.what_it_means || attempt.output.slice(-3).join(" ") || attempt.error || "Not summarized yet."}</p>
      {review && <div className="run-next-step"><GitBranch size={13} /> {nextStepLabels[review.next_step]}</div>}
    </div>
  );
}
