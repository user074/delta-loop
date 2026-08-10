import { Activity, ArrowRight, CheckCircle2, CircleDot, Clock3, FileText, FlaskConical, GitBranch, MessageSquareText, Route, ShieldCheck, Target, XCircle } from "lucide-react";
import { researchMapDiscussion, type DiscussionRequest } from "./discussions";
import type { Attempt, ResearchNode, Workspace, WorkPackage } from "./types";

const nodeKindLabels: Record<ResearchNode["kind"], string> = {
  question: "Question",
  direction: "Idea",
  approach: "Way to test it",
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
        onDiscuss={() => onDiscuss(researchMapDiscussion(workspace, selected))}
      />
      <ResearchDetail node={selected} workspace={workspace} onOpenPolicy={onOpenPolicy} />
    </section>
  );
}

function ResearchMap({ workspace, selectedId, onSelect, onDiscuss }: { workspace: Workspace; selectedId: string | null; onSelect: (id: string) => void; onDiscuss: () => void }) {
  const question = workspace.nodes.find((node) => node.kind === "question");
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const directionIds = new Set(directions.map((node) => node.id));
  return (
    <div className="research-panel">
      <div className="panel-header">
        <div><div className="section-kicker"><Route size={14} /> Research</div><h2>Ideas, tests, and results</h2></div>
        <div className="research-header-actions">
          <span className="map-count">{directions.length} ideas · {workspace.runs.length + workspace.attempts.length} tests</span>
          <button className="discuss-button" onClick={onDiscuss}><MessageSquareText size={14} /> Discuss</button>
        </div>
      </div>
      <div className="research-map">
        {question && <ResearchNodeCard node={question} workspace={workspace} selected={selectedId === question.id} onSelect={onSelect} compact />}
        <div className="map-connector"><span /></div>
        <div className="direction-grid">
          {directions.map((direction, index) => {
            const children = approaches.filter((approach) => approach.parent_id === direction.id || (index === 0 && !directionIds.has(approach.parent_id ?? "")));
            return (
              <div className="direction-column" key={direction.id}>
                <ResearchNodeCard node={direction} workspace={workspace} selected={selectedId === direction.id} onSelect={onSelect} direction />
                <div className="direction-child-line" />
                <div className="direction-approaches">
                  {children.length ? children.map((approach) => (
                    <ResearchNodeCard key={approach.id} node={approach} workspace={workspace} selected={selectedId === approach.id} onSelect={onSelect} />
                  )) : <div className="empty-branch">No way to test this idea has been recorded yet.</div>}
                </div>
              </div>
            );
          })}
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
  compact = false,
  direction = false,
}: {
  node: ResearchNode;
  workspace: Workspace;
  selected: boolean;
  onSelect: (id: string) => void;
  compact?: boolean;
  direction?: boolean;
}) {
  const contextApproaches = node.kind === "approach"
    ? [node]
    : node.kind === "direction"
      ? workspace.nodes.filter((item) => item.kind === "approach" && item.parent_id === node.id)
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
    <button className={`node-card ${selected ? "selected" : ""} ${compact ? "compact" : ""} ${direction ? "direction" : ""}`} onClick={() => onSelect(node.id)}>
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

function ResearchDetail({ node, workspace, onOpenPolicy }: { node: ResearchNode | null; workspace: Workspace; onOpenPolicy: (nodeId: string) => void }) {
  if (!node) return <aside className="detail-panel empty">Choose an idea from the map.</aside>;
  const claim = workspace.claims.find((item) => item.id === node.target_claim_id);
  const plans = node.kind === "approach" ? workspace.packages.filter((plan) => plan.approach_id === node.id) : [];
  const attempts = attemptsFor(node, workspace).slice().reverse();
  const historicalRuns = node.target_claim_id ? workspace.runs.filter((run) => run.claim_id === node.target_claim_id).slice().reverse() : [];
  return (
    <aside className="detail-panel">
      <div className="detail-scroll">
        <div className="detail-heading"><div className="section-kicker">Selected {nodeKindLabels[node.kind].toLowerCase()}</div><h2>{node.title}</h2>{node.summary && <p>{node.summary}</p>}</div>

        <div className="research-state-row">
          <span><strong>{statusLabels[node.status]}</strong> status</span>
          <span><strong>{titleCase(node.promise)}</strong> potential</span>
          <span><strong>{titleCase(node.evidence_strength)}</strong> support</span>
        </div>

        {node.kind === "approach" && (
          <div className="idea-policy-card">
            <div className="card-label"><ShieldCheck size={14} /> Policy for the next work</div>
            <h3>{workKindLabels[node.next_work_kind] ?? titleCase(node.next_work_kind)}</h3>
            <p>{node.agent_guidance || "No idea-specific guidance has been recorded yet. Discuss it with the agent."}</p>
            {node.ask_before && <small><strong>Stop and ask before:</strong> {node.ask_before}</small>}
            <button onClick={() => onOpenPolicy(node.id)}>Open policy <ArrowRight size={14} /></button>
          </div>
        )}

        {claim && <div className="claim-card"><div className="card-label"><CircleDot size={14} /> Idea this work is checking</div><p>{claim.statement}</p><div className="confidence-row"><span>{claim.status === "active" ? "Still being tested" : titleCase(claim.status)}</span><span>{claim.confidence == null ? "Not rated" : `${Math.round(claim.confidence * 100)}% sure`}</span></div></div>}

        {node.kind === "approach" && (
          <div className="attached-runs">
            <div className="card-label"><Activity size={14} /> Work and results for this idea</div>
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
            {!attempts.length && !historicalRuns.length && <div className="no-attached-runs">No work has been recorded for this idea yet.</div>}
          </div>
        )}

        {workspace.decisions.some((decision) => decision.node_id === node.id) && (
          <div className="decision-history"><div className="card-label"><Clock3 size={14} /> Why the direction changed</div>{workspace.decisions.filter((decision) => decision.node_id === node.id).slice().reverse().map((decision) => <div className="decision-row" key={decision.id}><span>{titleCase(decision.action)}</span><p>{decision.rationale}</p></div>)}</div>
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
