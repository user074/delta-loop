import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Cpu,
  Infinity,
  MessageSquareText,
  RotateCcw,
  Route,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useState } from "react";
import { generalPolicyDiscussion, ideaPolicyDiscussion, type DiscussionRequest } from "./discussions";
import type { AgentRule, ResearchNode, Workspace } from "./types";

const workKindLabels: Record<string, string> = {
  "quick-test": "Quick test",
  replicate: "Replicate",
  "literature-review": "Literature review",
  "compare-explanations": "Compare explanations",
  ablation: "Ablation",
  "full-study": "Full study",
  "research-engineering": "Research engineering",
};

const categoryLabels: Record<AgentRule["category"], string> = {
  loop: "Research loop",
  checkpoint: "Extra check",
  project: "Agent and files",
  git: "Git and GitHub",
  hardware: "Hardware",
  data: "Data",
  resources: "Time and resources",
  temporary: "Temporary",
};

const workPolicyReferences: Record<string, string> = {
  "quick-test": "Uses the Quick Test extra check above.",
  replicate: "Uses “Replicate before expanding” above.",
  "literature-review": "Uses “Check the literature at major milestones” above.",
  "full-study": "Uses “Promote useful signals to a full study” above.",
  "compare-explanations": "Uses the research loop plus this idea’s special instructions.",
  ablation: "Uses the research loop plus this idea’s special instructions.",
  "research-engineering": "Uses the research loop plus this idea’s special instructions.",
};

const checkpointReferences: Record<string, string> = {
  "keep-main-question": "Applies to every idea",
  "start-with-small-test": "Used when Next work is Quick test",
  "ground-every-hypothesis": "The imported delta-research default",
  "replicate-promising-result": "Also used when Next work is Replicate",
  "literature-after-milestone": "Also used when Next work is Literature review",
  "ask-before-full-study": "Used when evidence may justify a Full study",
};

function RuleRow({ rule }: { rule: AgentRule }) {
  return (
    <div className={rule.enabled ? "policy-rule-row" : "policy-rule-row disabled"}>
      <div className="policy-rule-topline">
        <span>{categoryLabels[rule.category]}</span>
        <em>{rule.enabled ? "Active" : "Off"}</em>
      </div>
      <strong>{rule.title}</strong>
      <dl>
        <div><dt>When</dt><dd>{rule.when}</dd></div>
        <div><dt>Do</dt><dd>{rule.instruction}</dd></div>
        <div><dt>Where</dt><dd>{rule.scope}</dd></div>
        {rule.expires_when && <div><dt>Ends</dt><dd>{rule.expires_when}</dd></div>}
        {rule.source_label && <div><dt>Source</dt><dd>{rule.source_label}</dd></div>}
      </dl>
    </div>
  );
}

export default function PolicyPage({
  workspace,
  selectedNode,
  onSelect,
  onEditGeneral,
  onDiscuss,
}: {
  workspace: Workspace;
  selectedNode: ResearchNode | null;
  onSelect: (nodeId: string) => void;
  onEditGeneral: () => void;
  onDiscuss: (request: Omit<DiscussionRequest, "id">) => void;
}) {
  const active = workspace.rules_versions.find((version) => version.id === workspace.active_rules_version_id);
  const rules = active?.rules ?? [];
  const loopRules = rules.filter((rule) => rule.enabled && rule.category === "loop");
  const loopStages = loopRules.filter((rule) => rule.loop_level === "stage");
  const loopSteps = loopRules.filter((rule) => rule.loop_level === "step");
  const [openStageId, setOpenStageId] = useState<string | null>(null);
  const [openStepId, setOpenStepId] = useState<string | null>(null);
  const openStage = loopStages.find((stage) => stage.id === openStageId) ?? null;
  const checkpoints = rules.filter((rule) => rule.enabled && rule.category === "checkpoint");
  const detailRules = rules.filter((rule) => ["project", "git", "hardware", "data", "resources"].includes(rule.category));
  const nestedDetailRules = detailRules.filter((rule) => rule.loop_step_ids.length > 0);
  const unassignedDetailRules = detailRules.filter((rule) => rule.loop_step_ids.length === 0);
  const temporaryRules = rules.filter((rule) => rule.category === "temporary");
  const continuousRule = rules.find((rule) => rule.id === "continuous-research");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const ideaExceptions = approaches.filter((node) => node.next_work_kind !== "quick-test" || node.agent_guidance || node.ask_before);

  function discussPolicy(focus: string) {
    onDiscuss(generalPolicyDiscussion(workspace, focus));
  }

  function discussIdea(node: ResearchNode) {
    onSelect(node.id);
    onDiscuss(ideaPolicyDiscussion(node));
  }

  function toggleStage(stageId: string) {
    setOpenStageId((current) => current === stageId ? null : stageId);
    setOpenStepId(null);
  }

  return (
    <section className="policy-control-page">
      <header className="policy-control-head">
        <div>
          <div className="section-kicker"><ShieldCheck size={14} /> Policy</div>
          <h1>Control how the research loop runs</h1>
          <p>This is the actual loop the agent follows. Review the main stages first, then open only the steps and details you need.</p>
        </div>
        <div className="policy-control-actions">
          <button className="discuss-button" onClick={() => discussPolicy("the whole research loop and project policy")}><MessageSquareText size={15} /> Chat</button>
          <button onClick={onEditGeneral}><SlidersHorizontal size={15} /> Edit loop and rules</button>
        </div>
      </header>

      <div className="active-policy-strip" aria-label="Active policy summary">
        <div><Route size={15} /><span>Loop</span><strong>{loopStages.length} stages · {loopSteps.length} steps</strong></div>
        <div><CheckCircle2 size={15} /><span>Extra checks</span><strong>{checkpoints.length} active</strong></div>
        <div><SlidersHorizontal size={15} /><span>Step details</span><strong>{nestedDetailRules.filter((rule) => rule.enabled).length} active</strong></div>
        <div><Clock3 size={15} /><span>Temporary</span><strong>{temporaryRules.filter((rule) => rule.enabled).length} active</strong></div>
        <div><BookOpen size={15} /><span>Special cases</span><strong>{ideaExceptions.length}</strong></div>
      </div>

      <section className={continuousRule?.enabled ? "autonomy-policy-card active" : "autonomy-policy-card"}>
        <Infinity size={24} />
        <div>
          <div className="section-kicker">Approval policy</div>
          <h2>{continuousRule?.enabled ? "Continuous research is on" : "Continuous research is off"}</h2>
          <p>{continuousRule?.enabled
            ? "After you start research, the agent chooses, runs, reviews, records, and begins the next useful test without waiting for you. It stops only at a saved hard limit or when no safe useful work remains."
            : "The agent is not currently instructed to continue from one research cycle to the next while you are away."}</p>
        </div>
        <button onClick={() => discussPolicy("when autonomous research should continue and the few hard conditions that should stop it")}><MessageSquareText size={14} /> Chat</button>
      </section>

      <div className="policy-sync-state">
        <CheckCircle2 size={18} />
        <div>
          <strong>This page is the active research loop</strong>
          <span>Using a policy version rewrites the complete instruction file read by the agent.</span>
        </div>
        <code>.delta-loop/LOOP.md</code>
      </div>

      <section className="policy-loop-section">
        <div className="policy-section-head">
          <div><div className="section-kicker"><Route size={14} /> Research loop</div><h2>Review the loop at the level you need</h2></div>
          <div className="rules-actions">
            <button onClick={() => discussPolicy("the default research loop from reading the current state through saving the result and continuing")}><MessageSquareText size={14} /> Chat</button>
            <button onClick={onEditGeneral}><SlidersHorizontal size={14} /> Edit loop</button>
          </div>
        </div>

        <div className="loop-level-guide" aria-label="Loop detail levels">
          <span className={!openStage ? "active" : ""}>1 · Main stages</span>
          <ChevronRight size={13} />
          <span className={openStage && !openStepId ? "active" : ""}>2 · Steps</span>
          <ChevronRight size={13} />
          <span className={openStepId ? "active" : ""}>3 · Details</span>
        </div>

        <div className="policy-loop-overview">
          {loopStages.map((stage, index) => {
            const childCount = loopSteps.filter((step) => step.loop_parent_id === stage.id).length;
            const isOpen = openStageId === stage.id;
            return (
              <div className="policy-stage-item" key={stage.id}>
                <button className={isOpen ? "policy-stage-card selected" : "policy-stage-card"} onClick={() => toggleStage(stage.id)} aria-expanded={isOpen}>
                  <span>{index + 1}</span>
                  <small>{childCount} {childCount === 1 ? "step" : "steps"}</small>
                  <h3>{stage.title}</h3>
                  <p>{stage.instruction}</p>
                  <em>{isOpen ? "Hide steps" : "Open stage"} {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</em>
                </button>
                {index < loopStages.length - 1 && <div className="loop-arrow"><ChevronRight size={18} /></div>}
              </div>
            );
          })}
          {!loopStages.length && <div className="policy-empty-rule">No main stage is active. Chat with the agent before starting autonomous work.</div>}
        </div>

        {openStage && (
          <div className="policy-stage-panel">
            <div className="policy-stage-panel-head">
              <div><span>Stage {loopStages.findIndex((stage) => stage.id === openStage.id) + 1}</span><h3>{openStage.title}</h3><p>{openStage.instruction}</p></div>
              <button onClick={() => toggleStage(openStage.id)}><ChevronDown size={14} /> Collapse</button>
            </div>
            <div className="policy-step-list">
              {loopSteps.filter((step) => step.loop_parent_id === openStage.id).map((step, index) => {
                const isOpen = openStepId === step.id;
                const stageNumber = loopStages.findIndex((stage) => stage.id === openStage.id) + 1;
                const relatedRules = detailRules.filter((rule) => rule.loop_step_ids.includes(step.id));
                return (
                  <article className={isOpen ? "policy-step-card open" : "policy-step-card"} key={step.id}>
                    <button onClick={() => setOpenStepId(isOpen ? null : step.id)} aria-expanded={isOpen}>
                      <span>{stageNumber}.{index + 1}</span><strong>{step.title}</strong>
                      {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    </button>
                    {isOpen && (
                      <div className="policy-step-details">
                        <div><small>When</small><p>{step.when}</p></div>
                        <div><small>What the agent does</small><p>{step.instruction}</p></div>
                        <div className="policy-step-related">
                          <small>Details used in this step</small>
                          {relatedRules.map((rule) => (
                            <div className={rule.enabled ? "step-detail-rule" : "step-detail-rule disabled"} key={rule.id}>
                              <div><span>{categoryLabels[rule.category]}</span><em>{rule.enabled ? "Used" : "Off"}</em></div>
                              <strong>{rule.title}</strong>
                              <p>{rule.instruction}</p>
                              <footer><b>When</b> {rule.when}</footer>
                              {rule.source_label && <footer><b>Source</b> {rule.source_label}</footer>}
                            </div>
                          ))}
                          {!relatedRules.length && <p className="no-step-detail">No extra instruction is attached to this step.</p>}
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
              {!loopSteps.some((step) => step.loop_parent_id === openStage.id) && <div className="policy-empty-rule">This stage has no smaller steps yet.</div>}
            </div>
          </div>
        )}
        <div className="loop-return"><RotateCcw size={14} /> If no stop rule applies, the agent returns to step 1 with the updated research state.</div>

        <div className="checkpoint-rail">
          <div className="checkpoint-label">Extra rules guide decisions inside the loop</div>
          {checkpoints.map((rule) => (
            <div className="checkpoint-stop" key={rule.id}>
              <span>{rule.when}</span><strong>{rule.title}</strong>{checkpointReferences[rule.id] && <b>{checkpointReferences[rule.id]}</b>}<p>{rule.instruction}</p>{rule.source_label && <small>{rule.source_label}</small>}
            </div>
          ))}
        </div>
      </section>

      <div className={unassignedDetailRules.length ? "policy-sections-grid" : "policy-sections-grid single"}>
        {unassignedDetailRules.length > 0 && <section className="policy-rules-section">
          <div className="policy-section-head compact">
            <div><div className="section-kicker"><SlidersHorizontal size={14} /> Needs a place</div><h2>Details not assigned to a loop step</h2></div>
            <button onClick={onEditGeneral}><SlidersHorizontal size={14} /> Assign</button>
          </div>
          <p className="unassigned-rules-help">These rules came from an older policy or were added without choosing where they belong. Assign each one to the step that should use it.</p>
          <div className="policy-rule-list">
            {unassignedDetailRules.map((rule) => <RuleRow key={rule.id} rule={rule} />)}
          </div>
        </section>}

        <section className="policy-rules-section temporary">
          <div className="policy-section-head compact">
            <div><div className="section-kicker"><Cpu size={14} /> Temporary limits</div><h2>Rules that should end later</h2></div>
            <button onClick={() => discussPolicy("temporary hardware, time, budget, or workflow limits and when each one should end")}><MessageSquareText size={14} /> Chat</button>
          </div>
          <div className="policy-rule-list">
            {temporaryRules.map((rule) => <RuleRow key={rule.id} rule={rule} />)}
            {!temporaryRules.length && (
              <div className="policy-empty-rule">No temporary limit is active. This is where something like “use GPU 0 until this batch finishes” would appear.</div>
            )}
          </div>
        </section>
      </div>

      <section className="idea-rules-section">
        <div className="policy-section-head">
          <div><div className="section-kicker"><BookOpen size={14} /> Rules for particular ideas</div><h2>When an idea should follow a different path</h2></div>
          <button onClick={() => discussPolicy("which research ideas need replication, literature review, a quick test, or another special treatment")}><MessageSquareText size={14} /> Chat</button>
        </div>
        <div className="idea-policy-table">
          {approaches.map((approach) => (
            <div className={selectedNode?.id === approach.id ? "idea-policy-row selected" : "idea-policy-row"} key={approach.id}>
              <div><strong>{approach.title}</strong><span>{approach.status === "dormant" ? "Parked" : approach.status}</span></div>
              <div><small>Next work</small><strong>{workKindLabels[approach.next_work_kind] ?? approach.next_work_kind}</strong><span className="work-policy-reference">{workPolicyReferences[approach.next_work_kind] ?? "Uses the research loop."}</span></div>
              <div><small>Special instructions</small><p>{approach.agent_guidance || "Use the research loop."}</p></div>
              <div><small>Stop only if</small><p>{approach.ask_before || "No additional stop."}</p></div>
              <button onClick={() => discussIdea(approach)}><MessageSquareText size={14} /> Chat</button>
            </div>
          ))}
          {!approaches.length && <div className="policy-empty-rule">No ways to test an idea have been recorded yet.</div>}
        </div>
      </section>

      <footer className="policy-history-row">
        <div><Clock3 size={14} /><span>Using policy version {active?.version ?? "—"}</span><strong>{workspace.rules_versions.length} saved versions</strong></div>
        <button onClick={onEditGeneral}>See previous versions <ChevronRight size={14} /></button>
      </footer>
    </section>
  );
}
