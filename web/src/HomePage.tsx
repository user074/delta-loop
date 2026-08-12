import { ArrowRight, CheckCircle2, Edit3, FlaskConical, GitBranch, History, MessageSquareText, Save, Sparkles, Target, X } from "lucide-react";
import { useMemo, useState } from "react";
import { updateQuestion } from "./api";
import { questionDiscussion, type DiscussionRequest } from "./discussions";
import type { ResearchNode, Workspace } from "./types";

const nextStepLabels: Record<string, string> = {
  "go-deeper": "Do a larger test",
  "run-again": "Repeat the test",
  "change-test": "Change the test",
  "try-another": "Try another idea",
  park: "Park this idea",
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

function readableStatus(status: string) {
  if (status === "primary") return "Main focus";
  if (status === "active") return "Active";
  if (status === "dormant") return "Parked";
  return "Done";
}

export default function HomePage({
  workspace,
  onWorkspace,
  onError,
  onOpenResearch,
  onDiscuss,
}: {
  workspace: Workspace;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
  onOpenResearch: (nodeId: string) => void;
  onDiscuss: (request: Omit<DiscussionRequest, "id">) => void;
}) {
  const [editingQuestion, setEditingQuestion] = useState(false);
  const [question, setQuestion] = useState(workspace.goal);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const approachesForIdea = (directionId: string) => approaches.filter((approach) => (
    workspace.research_links.some((link) => link.source_id === directionId && link.target_id === approach.id && link.relationship === "tests")
  ));
  const latestAttempt = useMemo(
    () => workspace.attempts.slice().sort((a, b) => b.started_at.localeCompare(a.started_at))[0] ?? null,
    [workspace.attempts],
  );
  const latestPlan = workspace.packages.find((plan) => plan.id === latestAttempt?.package_id) ?? null;
  const latestReview = workspace.reviews.find((review) => review.attempt_id === latestAttempt?.id) ?? null;
  const latestApproach = workspace.nodes.find((node) => node.id === latestPlan?.approach_id) ?? null;
  const latestHistorical = workspace.runs.at(-1) ?? null;
  const lastQuestionChange = workspace.question_history.at(-1);

  async function saveQuestion(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const updated = await updateQuestion(workspace.id, question, reason);
      onWorkspace(updated);
      setEditingQuestion(false);
      setReason("");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not update the question.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="home-page">
      <div className="home-question-card">
        <div className="home-section-head">
          <div>
            <div className="section-kicker"><Target size={14} /> Main question</div>
            {!editingQuestion && <h1>{workspace.goal}</h1>}
          </div>
          {!editingQuestion && (
            <div className="question-actions">
              <button className="discuss-button" onClick={() => onDiscuss(questionDiscussion(workspace))}>
                <MessageSquareText size={14} /> Chat
              </button>
              <button onClick={() => { setQuestion(workspace.goal); setEditingQuestion(true); }}>
                <Edit3 size={14} /> Edit directly
              </button>
            </div>
          )}
        </div>
        {editingQuestion ? (
          <form className="question-edit" onSubmit={saveQuestion}>
            <label><span>Updated question</span><textarea rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} /></label>
            <label><span>Why did it change?</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="What did the recent research change?" /></label>
            <p>Chat with the agent about the shift first. Saving keeps the previous wording in the history.</p>
            <div><button type="button" onClick={() => setEditingQuestion(false)}><X size={14} /> Cancel</button><button className="save-question" disabled={busy || !question.trim()}><Save size={14} /> Save question</button></div>
          </form>
        ) : (
          <div className="question-supporting-copy">
            <p>{workspace.synthesis || "The agent should keep the research map and result summaries aligned with this question."}</p>
            {lastQuestionChange && <small><History size={12} /> Last changed because: {lastQuestionChange.reason || "the research direction developed"}</small>}
          </div>
        )}
      </div>

      <div className="home-content-grid">
        <article className="latest-review-card">
          <div className="slide-topline">
            <div className="section-kicker"><Sparkles size={14} /> Latest research update</div>
            <span>{latestAttempt ? latestAttempt.status : latestHistorical ? "Imported result" : "No result yet"}</span>
          </div>
          {latestAttempt && latestPlan ? (
            <>
              <div className="slide-title-row">
                <div><small>{latestApproach?.title ?? "Research work"}</small><h2>{latestPlan.title}</h2></div>
                <strong>{workKindLabels[latestPlan.work_kind] ?? latestPlan.work_kind}</strong>
              </div>
              <div className="slide-summary-grid">
                <div><span>What it tested</span><p>{latestPlan.goal || "Not summarized yet."}</p></div>
                <div><span>Method</span><p>{latestPlan.instructions || latestPlan.comparison || "See the saved run details."}</p></div>
                <div><span>Data and inputs</span><p>{latestPlan.inputs || "Not summarized yet."}</p></div>
                <div className="result-cell"><span>Result and review</span><p>{latestReview?.what_it_means || latestAttempt.output.slice(-4).join(" ") || "The result has not been summarized yet."}</p></div>
              </div>
              <div className="slide-decision-row">
                <div><CheckCircle2 size={16} /><span>{latestReview ? `Result trusted: ${latestReview.trust_result}` : "Needs a research review"}</span></div>
                <strong>{latestReview ? nextStepLabels[latestReview.next_step] : "Chat with the agent about what this means"}</strong>
              </div>
              {latestApproach && <button className="open-research-link" onClick={() => onOpenResearch(latestApproach.id)}>See this idea and its history <ArrowRight size={14} /></button>}
            </>
          ) : latestHistorical ? (
            <>
              <div className="slide-title-row"><div><small>Most recent imported test</small><h2>{latestHistorical.delta}</h2></div><strong>{latestHistorical.signal.replaceAll("-", " ")}</strong></div>
              <div className="historical-result"><span>Recorded conclusion</span><p>{latestHistorical.verdict.replaceAll("-", " ")}</p><small>The imported record does not contain a full method and data summary.</small></div>
            </>
          ) : (
            <div className="empty-slide"><FlaskConical size={28} /><h2>No research result yet</h2><p>When the agent finishes work and records its review, the update will appear here.</p></div>
          )}
        </article>

        <aside className="decision-needed-card">
          <div className="section-kicker"><GitBranch size={14} /> Research picture</div>
          <h2>What is working and what is not</h2>
          <div className="idea-outcome-list">
            {directions.map((direction) => (
              <IdeaOutcome key={direction.id} direction={direction} approaches={approachesForIdea(direction.id)} workspace={workspace} onOpen={onOpenResearch} />
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}

function IdeaOutcome({
  direction,
  approaches,
  workspace,
  onOpen,
}: {
  direction: ResearchNode;
  approaches: ResearchNode[];
  workspace: Workspace;
  onOpen: (nodeId: string) => void;
}) {
  const approachIds = new Set(approaches.map((item) => item.id));
  const packages = workspace.packages.filter((item) => approachIds.has(item.approach_id));
  const packageIds = new Set(packages.map((item) => item.id));
  const attempts = workspace.attempts.filter((item) => packageIds.has(item.package_id));
  const claimIds = new Set(approaches.map((item) => item.target_claim_id).filter(Boolean));
  const historical = workspace.runs.filter((run) => run.claim_id && claimIds.has(run.claim_id));
  const reviewed = attempts.filter((attempt) => workspace.reviews.some((review) => review.attempt_id === attempt.id)).length;
  const failed = attempts.filter((attempt) => attempt.status === "failed" || attempt.status === "cancelled").length;
  const running = attempts.filter((attempt) => attempt.status === "running" || attempt.status === "starting").length;
  const primaryApproach = approaches.find((item) => item.status === "primary") ?? approaches[0];
  return (
    <button className="idea-outcome-row" onClick={() => onOpen(primaryApproach?.id ?? direction.id)}>
      <div><strong>{direction.title}</strong><span>{readableStatus(direction.status)} · {approaches.length} ways tried</span></div>
      <div className="outcome-counts">
        {running > 0 && <span className="running">{running} running</span>}
        {reviewed > 0 && <span className="worked">{reviewed} reviewed</span>}
        {failed > 0 && <span className="failed">{failed} failed</span>}
        {historical.length > 0 && <span>{historical.length} imported</span>}
        {!attempts.length && !historical.length && <span>Not run yet</span>}
      </div>
      <ArrowRight size={14} />
    </button>
  );
}
