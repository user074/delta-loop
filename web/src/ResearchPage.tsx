import { Activity, ArrowRight, CheckCircle2, CircleDot, Clock3, FileText, FlaskConical, GitBranch, Link2, MessageSquareText, Pencil, Plus, Route, ShieldCheck, Target, XCircle } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { addExperimentFromIdeaDiscussion, addIdeaFromQuestionDiscussion, addResearchQuestionDiscussion, connectResearchNodeDiscussion, researchMapDiscussion, reviseResearchNodeDiscussion, type DiscussionRequest } from "./discussions";
import type { Attempt, ResearchNode, Workspace, WorkPackage } from "./types";

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "Question",
  direction: "Idea",
  approach: "Experiment",
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

const relationshipLabels: Record<Workspace["research_links"][number]["relationship"], string> = {
  explores: "explores",
  tests: "tests",
  supports: "supports",
  challenges: "challenges",
  informs: "informs",
  "depends-on": "depends on",
  related: "related",
};

function titleCase(value: string) {
  return value.replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
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
  return (
    <section className="workspace-grid">
      <ResearchMap
        workspace={workspace}
        selectedId={selectedId}
        onSelect={onSelect}
        onDiscuss={() => onDiscuss(researchMapDiscussion(selected))}
        onAddQuestion={() => onDiscuss(addResearchQuestionDiscussion())}
      />
      <ResearchDetail
        node={selected}
        workspace={workspace}
        onOpenPolicy={onOpenPolicy}
        onSelect={onSelect}
        onDiscuss={onDiscuss}
      />
    </section>
  );
}

function ResearchMap({ workspace, selectedId, onSelect, onDiscuss, onAddQuestion }: { workspace: Workspace; selectedId: string | null; onSelect: (id: string) => void; onDiscuss: () => void; onAddQuestion: () => void }) {
  const questions = workspace.nodes.filter((node) => node.kind === "question");
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const canvasRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef(new Map<string, HTMLButtonElement>());
  const [lines, setLines] = useState<Array<{ id: string; path: string; x: number; y: number; label: string; relationship: string; connected: boolean }>>([]);

  useLayoutEffect(() => {
    const measure = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const bounds = canvas.getBoundingClientRect();
      setLines(workspace.research_links.flatMap((link) => {
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
          label: relationshipLabels[link.relationship],
          relationship: link.relationship,
          connected: !selectedId || link.source_id === selectedId || link.target_id === selectedId,
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
  }, [selectedId, workspace.nodes, workspace.research_links]);

  const setCardRef = (id: string) => (element: HTMLButtonElement | null) => {
    if (element) cardRefs.current.set(id, element);
    else cardRefs.current.delete(id);
  };
  const columns = [
    { kind: "question", label: "Questions", empty: "No research question yet", nodes: questions },
    { kind: "direction", label: "Ideas", empty: "No research ideas yet", nodes: directions },
    { kind: "approach", label: "Experiments", empty: "No experiments yet", nodes: approaches },
  ];
  return (
    <div className="research-panel">
      <div className="panel-header">
        <div><div className="section-kicker"><Route size={14} /> Research</div><h2>Questions, ideas, and experiments</h2></div>
        <div className="research-header-actions">
          <span className="map-count">{questions.length} {questions.length === 1 ? "question" : "questions"} · {directions.length} {directions.length === 1 ? "idea" : "ideas"} · {approaches.length} {approaches.length === 1 ? "experiment" : "experiments"}</span>
          <button className="map-add-button" onClick={onAddQuestion}><Plus size={14} /> Add question</button>
          <button className="discuss-button" onClick={onDiscuss}><MessageSquareText size={14} /> Chat about map</button>
        </div>
      </div>
      <div className="research-map" ref={canvasRef}>
        <div className="graph-legend"><span><i className="graph-line hierarchy" /> Main path</span><span><i className="graph-line evidence" /> Other relationship</span><small>Select an item to highlight its connections.</small></div>
        <svg className="research-links" aria-label="Research relationships">
          <defs><marker id="graph-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" /></marker></defs>
          {lines.map((line) => {
            const labelWidth = Math.max(38, line.label.length * 5.5 + 12);
            return <g key={line.id} className={`research-link ${line.relationship} ${line.connected ? "connected" : "muted"}`}>
              <path d={line.path} markerEnd="url(#graph-arrow)" />
              <rect x={line.x - labelWidth / 2} y={line.y - 8} width={labelWidth} height={16} rx={8} />
              <text x={line.x} y={line.y + 3}>{line.label}</text>
            </g>;
          })}
        </svg>
        <div className="research-columns">
          {columns.map((column) => (
            <section className={`research-column ${column.kind}`} key={column.kind}>
              <div className="research-column-title"><span>{column.label}</span><small>{column.nodes.length}</small></div>
              <div className="research-column-cards">
                {column.nodes.map((node) => (
                  <ResearchNodeCard
                    key={node.id}
                    node={node}
                    workspace={workspace}
                    selected={selectedId === node.id}
                    onSelect={onSelect}
                    cardRef={setCardRef(node.id)}
                  />
                ))}
                {!column.nodes.length && <div className="empty-branch">{column.empty}</div>}
              </div>
            </section>
          ))}
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
  onSelect,
  cardRef,
  compact = false,
  direction = false,
}: {
  node: ResearchNode;
  workspace: Workspace;
  selected: boolean;
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
  const failed = attempts.filter((attempt) => attempt.status === "failed" || attempt.status === "cancelled").length;
  const reviewed = attempts.filter((attempt) => workspace.reviews.some((review) => review.attempt_id === attempt.id)).length;
  const claimIds = new Set(contextApproaches.map((item) => item.target_claim_id).filter(Boolean));
  const historical = workspace.runs.filter((run) => run.claim_id && claimIds.has(run.claim_id)).length;
  return (
    <button ref={cardRef} className={`node-card ${selected ? "selected" : ""} ${compact ? "compact" : ""} ${direction ? "direction" : ""}`} onClick={() => onSelect(node.id)}>
      <div className="node-topline">
        <span className={`node-kind ${node.kind}`}>{node.kind === "question" ? <Target size={13} /> : node.kind === "direction" ? <Route size={13} /> : <FlaskConical size={13} />}{nodeKindLabels[node.kind]}</span>
        <span className={`status-label ${node.status}`}>{statusLabels[node.status]}</span>
      </div>
      <h3>{node.title}</h3>
      {node.summary && <p>{node.summary}</p>}
      {node.kind === "approach" && (
        <>
          <div className="node-signals"><span><i className={`signal promise-${node.promise}`} /> {titleCase(node.promise)} potential</span><span><i className={`signal evidence-${node.evidence_strength}`} /> {titleCase(node.evidence_strength)} support</span></div>
        </>
      )}
      {node.kind !== "question" && (
        <div className="node-run-strip">
          {running > 0 && <span className="running">{running} running</span>}
          {reviewed > 0 && <span className="worked">{reviewed} reviewed</span>}
          {failed > 0 && <span className="failed">{failed} failed</span>}
          {historical > 0 && <span>{historical} imported</span>}
          {!attempts.length && !historical && <span>Not tested</span>}
        </div>
      )}
    </button>
  );
}

function ResearchDetail({ node, workspace, onOpenPolicy, onSelect, onDiscuss }: { node: ResearchNode | null; workspace: Workspace; onOpenPolicy: (nodeId: string) => void; onSelect: (nodeId: string) => void; onDiscuss: (request: Omit<DiscussionRequest, "id">) => void }) {
  if (!node) return <aside className="detail-panel empty">Choose a question, idea, or experiment from the map.</aside>;
  const claim = workspace.claims.find((item) => item.id === node.target_claim_id);
  const plans = node.kind === "approach" ? workspace.packages.filter((plan) => plan.approach_id === node.id) : [];
  const attempts = attemptsFor(node, workspace).slice().reverse();
  const historicalRuns = node.target_claim_id ? workspace.runs.filter((run) => run.claim_id === node.target_claim_id).slice().reverse() : [];
  const nodeHistory = workspace.node_history.filter((change) => change.node_id === node.id).slice().reverse();
  const connections = workspace.research_links.filter((link) => link.source_id === node.id || link.target_id === node.id);
  return (
    <aside className="detail-panel">
      <div className="detail-scroll">
        <div className="detail-heading"><div className="section-kicker">Selected {nodeKindLabels[node.kind].toLowerCase()}</div><h2>{node.title}</h2>{node.summary && <p>{node.summary}</p>}</div>

        <div className="research-item-actions">
          {node.kind === "question" && <button className="primary" onClick={() => onDiscuss(addIdeaFromQuestionDiscussion(node))}><Plus size={14} /><span><strong>Add idea</strong><small>Develop a direction for this question</small></span></button>}
          {node.kind === "direction" && <button className="primary" onClick={() => onDiscuss(addExperimentFromIdeaDiscussion(node))}><Plus size={14} /><span><strong>Add experiment</strong><small>Turn this idea into a concrete test</small></span></button>}
          <div className="research-item-secondary-actions">
            <button onClick={() => onDiscuss(researchMapDiscussion(node))}><MessageSquareText size={13} /> Explore</button>
            <button onClick={() => onDiscuss(reviseResearchNodeDiscussion(node))}><Pencil size={13} /> Revise</button>
            <button onClick={() => onDiscuss(connectResearchNodeDiscussion(node))}><Link2 size={13} /> Connect</button>
          </div>
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
            return <button key={link.id} onClick={() => onSelect(other.id)}><span>{outgoing ? "To" : "From"} {nodeKindLabels[other.kind].toLowerCase()} · {relationshipLabels[link.relationship]}</span><strong>{other.title}</strong>{link.note && <small>{link.note}</small>}</button>;
          })}
          {!connections.length && <p>No relationships have been recorded for this item yet.</p>}
        </div>

        {node.kind === "approach" && (
          <div className="idea-policy-card">
            <div className="card-label"><ShieldCheck size={14} /> Policy for the next work</div>
            <h3>{workKindLabels[node.next_work_kind] ?? titleCase(node.next_work_kind)}</h3>
            <p>{node.agent_guidance || "No experiment-specific guidance has been recorded yet. Chat with the agent about it."}</p>
            {node.ask_before && <small><strong>Stop and ask before:</strong> {node.ask_before}</small>}
            <button onClick={() => onOpenPolicy(node.id)}>Open policy <ArrowRight size={14} /></button>
          </div>
        )}

        {claim && <div className="claim-card"><div className="card-label"><CircleDot size={14} /> Idea this work is checking</div><p>{claim.statement}</p><div className="confidence-row"><span>{claim.status === "active" ? "Still being tested" : titleCase(claim.status)}</span><span>{claim.confidence == null ? "Not rated" : `${Math.round(claim.confidence * 100)}% sure`}</span></div></div>}

        {node.kind === "approach" && (
          <div className="attached-runs">
            <div className="card-label"><Activity size={14} /> Work and results for this experiment</div>
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
            {!attempts.length && !historicalRuns.length && <div className="no-attached-runs">No work has been recorded for this experiment yet.</div>}
          </div>
        )}

        {workspace.decisions.some((decision) => decision.node_id === node.id) && (
          <div className="decision-history"><div className="card-label"><Clock3 size={14} /> Why the direction changed</div>{workspace.decisions.filter((decision) => decision.node_id === node.id).slice().reverse().map((decision) => <div className="decision-row" key={decision.id}><span>{titleCase(decision.action)}</span><p>{decision.rationale}</p></div>)}</div>
        )}

        {nodeHistory.length > 0 && (
          <div className="decision-history">
            <div className="card-label"><GitBranch size={14} /> How this {node.kind === "approach" ? "experiment" : node.kind === "direction" ? "idea" : "question"} evolved</div>
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
  const endedBadly = attempt.status === "failed" || attempt.status === "cancelled";
  return (
    <div className={`run-story ${attempt.status}`}>
      <div className="run-story-head">
        {endedBadly ? <XCircle size={15} /> : attempt.status === "finished" ? <CheckCircle2 size={15} /> : <Activity size={15} />}
        <div><strong>{plan?.title ?? "Research work"}</strong><span>{titleCase(attempt.status)} · {plan ? workKindLabels[plan.work_kind] : ""}</span></div>
        {review && <em>{review.trust_result === "yes" ? "Trusted" : review.trust_result === "no" ? "Not trusted" : "Uncertain"}</em>}
      </div>
      {plan?.goal && <p><strong>Tested:</strong> {plan.goal}</p>}
      {plan?.instructions && <p><strong>Method:</strong> {plan.instructions}</p>}
      {plan?.inputs && <p><strong>Data:</strong> {plan.inputs}</p>}
      <p><strong>Result:</strong> {review?.what_it_means || attempt.output.slice(-3).join(" ") || attempt.error || "Not summarized yet."}</p>
      {review && <div className="run-next-step"><GitBranch size={13} /> {nextStepLabels[review.next_step]}</div>}
    </div>
  );
}
