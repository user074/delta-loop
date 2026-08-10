import { Activity, CheckCircle2, CircleStop, Clock3, FileText, Play, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { cancelRun, getWorkspace, reviewRun, runPlan } from "./api";
import { runStatusNames } from "./labels";
import type { Attempt, Workspace } from "./types";

export default function RunsPage({
  workspace,
  onWorkspace,
  onError,
}: {
  workspace: Workspace;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(workspace.attempts.at(-1)?.id ?? null);
  const [busy, setBusy] = useState(false);
  const [followedPlan, setFollowedPlan] = useState<"yes" | "no" | "unsure">("unsure");
  const [trustResult, setTrustResult] = useState<"yes" | "no" | "unsure">("unsure");
  const [meaning, setMeaning] = useState("");
  const [nextStep, setNextStep] = useState<"go-deeper" | "run-again" | "change-test" | "try-another" | "park">("change-test");
  const [notes, setNotes] = useState("");
  const [keepCode, setKeepCode] = useState(false);
  const outputRef = useRef<HTMLPreElement>(null);
  const selectedRun = workspace.attempts.find((run) => run.id === selectedRunId) ?? workspace.attempts.at(-1) ?? null;
  const selectedPlan = workspace.packages.find((plan) => plan.id === selectedRun?.package_id) ?? null;
  const review = workspace.reviews.find((item) => item.attempt_id === selectedRun?.id);
  const readyPlans = workspace.packages.filter((plan) => plan.status === "ready");

  useEffect(() => {
    if (!workspace.attempts.some((run) => run.status === "starting" || run.status === "running")) return;
    const timer = window.setInterval(() => {
      getWorkspace(workspace.id).then(onWorkspace).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onWorkspace, workspace.attempts, workspace.id]);

  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [selectedRun?.output]);

  const elapsed = useMemo(() => {
    if (!selectedRun) return "";
    const start = new Date(selectedRun.started_at).getTime();
    const end = selectedRun.finished_at ? new Date(selectedRun.finished_at).getTime() : Date.now();
    const seconds = Math.max(0, Math.round((end - start) / 1000));
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }, [selectedRun]);

  async function start(planId: string) {
    setBusy(true);
    try {
      const updated = await runPlan(workspace.id, planId);
      onWorkspace(updated);
      setSelectedRunId(updated.attempts.at(-1)?.id ?? null);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not start the work.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!selectedRun) return;
    setBusy(true);
    try {
      onWorkspace(await cancelRun(workspace.id, selectedRun.id));
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not stop the work.");
    } finally {
      setBusy(false);
    }
  }

  async function saveReview(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedRun) return;
    setBusy(true);
    try {
      onWorkspace(await reviewRun(workspace.id, selectedRun.id, {
        followed_plan: followedPlan,
        trust_result: trustResult,
        what_it_means: meaning,
        next_step: nextStep,
        notes,
        keep_code: keepCode,
      }));
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not save the review.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="runs-page">
      <aside className="runs-list-panel">
        <div className="section-kicker"><Activity size={14} /> Agent runs</div>
        <h2>What is running and what finished</h2>
        {readyPlans.length > 0 && (
          <div className="ready-plans">
            <strong>Ready to start</strong>
            {readyPlans.map((plan) => (
              <button key={plan.id} onClick={() => start(plan.id)} disabled={busy}>
                <Play size={13} /> {plan.title}
              </button>
            ))}
          </div>
        )}
        <div className="run-list">
          {workspace.attempts.slice().reverse().map((run) => {
            const plan = workspace.packages.find((item) => item.id === run.package_id);
            return (
              <button
                className={run.id === selectedRun?.id ? "run-list-item selected" : "run-list-item"}
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
              >
                <RunIcon run={run} />
                <div><strong>{plan?.title ?? "Unnamed run"}</strong><span>{runStatusNames[run.status] ?? run.status}</span></div>
              </button>
            );
          })}
          {!workspace.attempts.length && <div className="empty-list">Nothing has run yet. Approve a plan first.</div>}
        </div>
      </aside>

      <div className="run-detail-panel">
        {!selectedRun ? (
          <div className="page-empty-state">
            <div className="coming-icon"><Activity size={25} /></div>
            <h2>No runs yet</h2>
            <p>When you start an approved plan, its live output and result will appear here.</p>
          </div>
        ) : (
          <>
            <div className="run-detail-head">
              <div>
                <div className="section-kicker">{runStatusNames[selectedRun.status] ?? selectedRun.status}</div>
                <h2>{selectedPlan?.title ?? "Run"}</h2>
                <p><Clock3 size={13} /> {elapsed} · {selectedRun.command.join(" ")}</p>
              </div>
              {(selectedRun.status === "running" || selectedRun.status === "starting") && (
                <button className="stop-run-button" onClick={cancel} disabled={busy}><CircleStop size={15} /> Stop</button>
              )}
            </div>

            <div className="run-output-wrap">
              <div className="run-output-head"><span>Live output</span><span>{selectedRun.output.length} lines</span></div>
              <pre ref={outputRef}>{selectedRun.output.join("\n") || (selectedRun.status === "starting" ? "Starting…" : "No text output.")}</pre>
            </div>

            {selectedRun.handoff_file && (
              <div className="saved-run-files">
                <div className="card-label"><FileText size={15} /> Saved with this run</div>
                <p><strong>Approved plan</strong><code>{selectedRun.handoff_file}</code></p>
                <p><strong>Output folder</strong><code>{selectedRun.output_directory}</code></p>
              </div>
            )}

            {selectedRun.error && <div className="run-error"><XCircle size={16} /> {selectedRun.error}</div>}

            {review ? (
              <div className="saved-review">
                <div className="card-label"><CheckCircle2 size={15} /> Your review</div>
                <div className="review-summary-grid">
                  <div><span>Followed the plan?</span><strong>{review.followed_plan}</strong></div>
                  <div><span>Trust the result?</span><strong>{review.trust_result}</strong></div>
                  <div><span>Next step</span><strong>{review.next_step.replaceAll("-", " ")}</strong></div>
                </div>
                {review.what_it_means && <p><strong>What it means:</strong> {review.what_it_means}</p>}
                {review.notes && <p><strong>Notes:</strong> {review.notes}</p>}
              </div>
            ) : ["finished", "failed", "cancelled"].includes(selectedRun.status) ? (
              <form className="review-form" onSubmit={saveReview}>
                <div className="card-label"><FileText size={15} /> Review this run</div>
                <h3>Separate what happened from what it means</h3>
                <div className="review-choice-row">
                  <label><span>Did it follow the plan?</span><select value={followedPlan} onChange={(event) => setFollowedPlan(event.target.value as typeof followedPlan)}><option value="yes">Yes</option><option value="no">No</option><option value="unsure">Not sure</option></select></label>
                  <label><span>Do you trust the result?</span><select value={trustResult} onChange={(event) => setTrustResult(event.target.value as typeof trustResult)}><option value="yes">Yes</option><option value="no">No</option><option value="unsure">Not sure</option></select></label>
                </div>
                <label><span>What do you think the result means?</span><textarea rows={3} value={meaning} onChange={(event) => setMeaning(event.target.value)} placeholder="This supports…, goes against…, or leaves open…" /></label>
                <label><span>What should happen next?</span><select value={nextStep} onChange={(event) => setNextStep(event.target.value as typeof nextStep)}><option value="go-deeper">Do a larger test</option><option value="run-again">Run the same test again</option><option value="change-test">Change the test</option><option value="try-another">Try another idea</option><option value="park">Park this idea</option></select></label>
                <label><span>Other notes</span><textarea rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
                <label className="checkbox-line"><input type="checkbox" checked={keepCode} onChange={(event) => setKeepCode(event.target.checked)} /> Keep code changes from this run</label>
                <button className="primary-inline-button" disabled={busy}><CheckCircle2 size={15} /> Save review</button>
              </form>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

function RunIcon({ run }: { run: Attempt }) {
  if (run.status === "finished") return <CheckCircle2 className="run-icon finished" size={18} />;
  if (run.status === "failed" || run.status === "cancelled") return <XCircle className="run-icon failed" size={18} />;
  return <RefreshCw className="run-icon running spin" size={18} />;
}
