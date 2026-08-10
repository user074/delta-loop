import { Check, ChevronRight, FileText, Play, Plus, Save, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { approvePlan, createPlan, runPlan, updatePlan } from "./api";
import { planStatusNames, stageNames } from "./labels";
import type { ProtocolProfile, ResearchNode, WorkPackage, Workspace } from "./types";

const editableFields: Array<{
  key: keyof WorkPackage;
  label: string;
  help: string;
  rows?: number;
  placeholder: string;
}> = [
  {
    key: "goal",
    label: "What are we trying to learn?",
    help: "Write one clear question this test should answer.",
    placeholder: "Does changing X cause Y to increase?",
  },
  {
    key: "why_now",
    label: "Why run this now?",
    help: "Explain why this is the best next use of time.",
    placeholder: "The earlier result suggests this may separate the two explanations.",
  },
  {
    key: "instructions",
    label: "Exactly what should the agent do?",
    help: "List the steps in the order they should happen.",
    placeholder: "1. Reuse the existing loader…\n2. Run the small setting…\n3. Save the comparison…",
    rows: 5,
  },
  {
    key: "inputs",
    label: "Which files, data, models, or code should it use?",
    help: "Use exact names and paths when possible.",
    placeholder: "data/sample.json, checkpoints/model-1200, src/analyze.py",
    rows: 3,
  },
  {
    key: "comparison",
    label: "What is the fair comparison?",
    help: "Say what should stay the same and what one thing should change.",
    placeholder: "Compare the same checkpoint and examples, changing only…",
    rows: 3,
  },
  {
    key: "measure",
    label: "What result should we look at?",
    help: "Name the number, table, plot, or output that decides what happened.",
    placeholder: "Report the median difference and save a plot by layer.",
    rows: 3,
  },
  {
    key: "expected",
    label: "What do you expect to happen?",
    help: "Write what each possible result would mean before running the test.",
    placeholder: "If the idea is right, A should be larger than B. If not, they should be similar.",
    rows: 3,
  },
  {
    key: "limits",
    label: "What can this test not tell us?",
    help: "This prevents a quick test from being treated like a full study.",
    placeholder: "One setting cannot show whether this works across all models.",
    rows: 3,
  },
  {
    key: "do_not_change",
    label: "What must the agent not change?",
    help: "List important boundaries. The agent must ask before crossing them.",
    placeholder: "Do not change the dataset, main measurement, or model family.",
    rows: 3,
  },
  {
    key: "command",
    label: "What command starts the work?",
    help: "Delta Loop runs this in the project folder. Use {handoff} for the saved plan and {output_dir} for the results folder.",
    placeholder: "codex exec --prompt-file {handoff}",
  },
];

function planPatch(plan: WorkPackage): Partial<WorkPackage> {
  return {
    title: plan.title,
    stage: plan.stage,
    goal: plan.goal,
    why_now: plan.why_now,
    instructions: plan.instructions,
    inputs: plan.inputs,
    comparison: plan.comparison,
    measure: plan.measure,
    expected: plan.expected,
    limits: plan.limits,
    do_not_change: plan.do_not_change,
    command: plan.command,
    budget: plan.budget,
  };
}

export default function PlanPage({
  workspace,
  protocols,
  selectedNode,
  onWorkspace,
  onError,
  onOpenRuns,
}: {
  workspace: Workspace;
  protocols: ProtocolProfile[];
  selectedNode: ResearchNode | null;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
  onOpenRuns: () => void;
}) {
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const initialApproach = selectedNode?.kind === "approach" ? selectedNode : approaches[0];
  const [approachId, setApproachId] = useState(initialApproach?.id ?? "");
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(
    workspace.packages.at(-1)?.id ?? null,
  );
  const selectedSavedPlan = workspace.packages.find((plan) => plan.id === selectedPlanId) ?? null;
  const [draft, setDraft] = useState<WorkPackage | null>(selectedSavedPlan);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const current = workspace.packages.find((plan) => plan.id === selectedPlanId) ?? null;
    setDraft(current);
  }, [selectedPlanId, workspace.packages]);

  useEffect(() => {
    if (selectedNode?.kind === "approach") setApproachId(selectedNode.id);
  }, [selectedNode]);

  const approach = useMemo(
    () => approaches.find((node) => node.id === approachId) ?? approaches[0],
    [approachId, approaches],
  );
  const draftApproach = approaches.find((node) => node.id === draft?.approach_id);
  const draftProfile = protocols.find(
    (profile) => profile.id === (draftApproach?.protocol_id ?? workspace.protocol_id),
  ) ?? protocols[0];

  async function makePlan() {
    if (!approach) return;
    setBusy(true);
    try {
      const updated = await createPlan(
        workspace.id,
        approach.id,
        `${stageNames[approach.current_stage ?? "minimal-probe"] ?? "Test"}: ${approach.title}`,
        approach.current_stage ?? "minimal-probe",
      );
      onWorkspace(updated);
      setSelectedPlanId(updated.packages.at(-1)?.id ?? null);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not make the plan.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return null;
    setBusy(true);
    try {
      const updated = await updatePlan(workspace.id, draft.id, planPatch(draft));
      onWorkspace(updated);
      return updated;
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not save the plan.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!draft) return;
    setBusy(true);
    try {
      await updatePlan(workspace.id, draft.id, planPatch(draft));
      const updated = await approvePlan(workspace.id, draft.id);
      onWorkspace(updated);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not approve the plan.");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!draft) return;
    setBusy(true);
    try {
      onWorkspace(await runPlan(workspace.id, draft.id));
      onOpenRuns();
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not start the work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="plan-page">
      <aside className="plan-list-panel">
        <div className="section-kicker"><FileText size={14} /> Saved plans</div>
        <h2>Plans for agents</h2>
        <p>Each plan says exactly what one agent may do.</p>
        <label className="plain-field">
          <span>Idea to plan for</span>
          <select value={approach?.id ?? ""} onChange={(event) => setApproachId(event.target.value)}>
            {approaches.map((node) => <option value={node.id} key={node.id}>{node.title}</option>)}
          </select>
        </label>
        <button className="primary-inline-button" disabled={!approach || busy} onClick={makePlan}>
          <Plus size={15} /> Make a new plan
        </button>
        <div className="saved-plan-list">
          {workspace.packages.slice().reverse().map((plan) => (
            <button
              key={plan.id}
              className={plan.id === selectedPlanId ? "saved-plan selected" : "saved-plan"}
              onClick={() => setSelectedPlanId(plan.id)}
            >
              <div>
                <strong>{plan.title}</strong>
                <span>{planStatusNames[plan.status] ?? plan.status} · {stageNames[plan.stage] ?? plan.stage}</span>
              </div>
              <ChevronRight size={15} />
            </button>
          ))}
          {!workspace.packages.length && <div className="empty-list">No plans yet.</div>}
        </div>
      </aside>

      <div className="plan-editor">
        {!draft ? (
          <div className="page-empty-state">
            <div className="coming-icon"><FileText size={25} /></div>
            <h2>Make your first plan</h2>
            <p>Choose an idea on the left. Delta Loop will give you a simple form for telling the agent what to do.</p>
          </div>
        ) : (
          <>
            <div className="plan-editor-head">
              <div>
                <div className="section-kicker">{stageNames[draft.stage] ?? draft.stage}</div>
                <input
                  className="plan-title-input"
                  value={draft.title}
                  disabled={draft.status !== "draft"}
                  onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                  aria-label="Plan name"
                />
                <span className={`plan-status ${draft.status}`}>{planStatusNames[draft.status] ?? draft.status}</span>
              </div>
              <div className="plan-head-actions">
                {draft.status === "draft" && (
                  <>
                    <button disabled={busy} onClick={save}><Save size={15} /> Save</button>
                    <button className="approve" disabled={busy} onClick={approve}><ShieldCheck size={15} /> Approve plan</button>
                  </>
                )}
                {draft.status === "ready" && (
                  <button className="run" disabled={busy} onClick={run}><Play size={15} /> Start work</button>
                )}
                {["running", "finished", "failed", "cancelled"].includes(draft.status) && (
                  <button onClick={onOpenRuns}><ChevronRight size={15} /> Open run</button>
                )}
              </div>
            </div>
            <div className="plan-form">
              <div className="plan-row two-column">
                <label className="plain-field">
                  <span>Amount of testing</span>
                  <select
                    value={draft.stage}
                    disabled={draft.status !== "draft"}
                    onChange={(event) => setDraft({ ...draft, stage: event.target.value })}
                  >
                    {draftProfile?.stages.map((stage) => (
                      <option value={stage.id} key={stage.id}>{stage.name}</option>
                    ))}
                  </select>
                </label>
                <label className="plain-field">
                  <span>Work limit</span>
                  <select
                    value={draft.budget}
                    disabled={draft.status !== "draft"}
                    onChange={(event) => setDraft({ ...draft, budget: event.target.value })}
                  >
                    <option>Small</option><option>Medium</option><option>Large</option>
                  </select>
                </label>
              </div>
              {editableFields.map((field) => (
                <label className="plan-field" key={field.key}>
                  <strong>{field.label}</strong>
                  <span>{field.help}</span>
                  {field.rows ? (
                    <textarea
                      rows={field.rows}
                      value={String(draft[field.key] ?? "")}
                      placeholder={field.placeholder}
                      disabled={draft.status !== "draft"}
                      onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })}
                    />
                  ) : (
                    <input
                      value={String(draft[field.key] ?? "")}
                      placeholder={field.placeholder}
                      disabled={draft.status !== "draft"}
                      onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })}
                    />
                  )}
                </label>
              ))}
              {draft.status !== "draft" && (
                <div className="approved-note"><Check size={16} /> This approved plan is locked so the work cannot quietly change underneath you.</div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
