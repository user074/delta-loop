import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cpu,
  GitBranch,
  MessageSquareText,
  RotateCcw,
  Route,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
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
  project: "Project",
  git: "Git and GitHub",
  hardware: "Hardware",
  data: "Data",
  resources: "Time and resources",
  temporary: "Temporary",
};

const defaultLoopOrder = [
  "start-with-small-test",
  "review-every-result",
  "state-result-limits",
  "choose-next-direction",
  "update-research-map",
];

const ruleDisplayNames: Record<string, string> = {
  "start-with-small-test": "Quick Test",
};

const workPolicyReferences: Record<string, string> = {
  "quick-test": "Uses Quick Test in the loop above.",
  replicate: "Uses “Replicate before expanding” above.",
  "literature-review": "Uses “Check the literature at major milestones” above.",
  "full-study": "Uses “Ask before a full study” above.",
  "compare-explanations": "Uses the default loop plus this idea’s special instructions.",
  ablation: "Uses the default loop plus this idea’s special instructions.",
  "research-engineering": "Uses the default loop plus this idea’s special instructions.",
};

const checkpointReferences: Record<string, string> = {
  "keep-main-question": "Applies to every idea",
  "replicate-promising-result": "Also used when Next work is Replicate",
  "literature-after-milestone": "Also used when Next work is Literature review",
  "ask-before-full-study": "Used when Next work is Full study",
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
  const loopRules = rules
    .filter((rule) => rule.enabled && rule.category === "loop")
    .sort((left, right) => {
      const leftIndex = defaultLoopOrder.indexOf(left.id);
      const rightIndex = defaultLoopOrder.indexOf(right.id);
      return (leftIndex < 0 ? defaultLoopOrder.length : leftIndex)
        - (rightIndex < 0 ? defaultLoopOrder.length : rightIndex);
    });
  const checkpoints = rules.filter((rule) => rule.enabled && rule.category === "checkpoint");
  const projectRules = rules.filter((rule) => ["project", "git", "hardware", "data", "resources"].includes(rule.category));
  const temporaryRules = rules.filter((rule) => rule.category === "temporary");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const ideaExceptions = approaches.filter((node) => node.next_work_kind !== "quick-test" || node.agent_guidance || node.ask_before);

  function discussPolicy(focus: string) {
    onDiscuss(generalPolicyDiscussion(workspace, focus));
  }

  function discussIdea(node: ResearchNode) {
    onSelect(node.id);
    onDiscuss(ideaPolicyDiscussion(node));
  }

  return (
    <section className="policy-control-page">
      <header className="policy-control-head">
        <div>
          <div className="section-kicker"><ShieldCheck size={14} /> Policy</div>
          <h1>Control how the research loop runs</h1>
          <p>These rules decide what the agent does next, when it must perform an extra check, and what limits apply to the work. Names such as Quick Test match the “Next work” names shown for each idea below.</p>
        </div>
        <div className="policy-control-actions">
          <button className="discuss-button" onClick={() => discussPolicy("the whole research loop and project policy")}><MessageSquareText size={15} /> Discuss</button>
          <button onClick={onEditGeneral}><SlidersHorizontal size={15} /> View all rules</button>
        </div>
      </header>

      <div className="active-policy-strip" aria-label="Active policy summary">
        <div><Route size={15} /><span>Loop</span><strong>{loopRules.length} steps</strong></div>
        <div><CheckCircle2 size={15} /><span>Extra checks</span><strong>{checkpoints.length} active</strong></div>
        <div><GitBranch size={15} /><span>Project rules</span><strong>{projectRules.filter((rule) => rule.enabled).length} active</strong></div>
        <div><Clock3 size={15} /><span>Temporary</span><strong>{temporaryRules.filter((rule) => rule.enabled).length} active</strong></div>
        <div><BookOpen size={15} /><span>Special cases</span><strong>{ideaExceptions.length}</strong></div>
      </div>

      <div className={`harness-sync-state ${workspace.harness.status}`}>
        <GitBranch size={18} />
        <div>
          <strong>{workspace.harness.path ? "Using delta-research as the base" : "The base research loop was not found"}</strong>
          <span>{workspace.harness.detail} Delta Loop adds the controls below without editing the base.</span>
        </div>
        <a href={workspace.harness.source_url.replace(/\.git$/, "")} target="_blank" rel="noreferrer">
          {workspace.harness.revision ? workspace.harness.revision.slice(0, 7) : "user074/delta-research"}
        </a>
      </div>

      <div className="policy-sync-state">
        <CheckCircle2 size={18} />
        <div>
          <strong>Delta Loop additions are active</strong>
          <span>The agent reads the base research loop together with your current map and policy before choosing work.</span>
        </div>
        <code>.delta-loop/LOOP.md + POLICY.md</code>
      </div>

      <section className="policy-loop-section">
        <div className="policy-section-head">
          <div><div className="section-kicker"><Route size={14} /> Default research loop</div><h2>What normally happens to an idea</h2></div>
          <button onClick={() => discussPolicy("the default research loop from a new idea through review and the next decision")}><MessageSquareText size={14} /> Discuss</button>
        </div>

        <div className="policy-loop-visual">
          {loopRules.map((rule, index) => (
            <div className="policy-loop-item" key={rule.id}>
              <article className="policy-loop-node">
                <span>{index + 1}</span>
                <small>{rule.when}</small>
                <h3>{ruleDisplayNames[rule.id] ?? rule.title}</h3>
                {rule.id === "start-with-small-test" && <b className="loop-policy-reference">Used when an idea says “Next work: Quick test”</b>}
                <p>{rule.instruction}</p>
                {rule.id === "choose-next-direction" && (
                  <div className="loop-branches"><i>Repeat</i><i>Change</i><i>Go deeper</i><i>Park</i></div>
                )}
              </article>
              {index < loopRules.length - 1 && <div className="loop-arrow"><ChevronRight size={18} /></div>}
            </div>
          ))}
          {!loopRules.length && <div className="policy-empty-rule">No default loop is active. Discuss it before starting autonomous work.</div>}
        </div>
        <div className="loop-return"><RotateCcw size={14} /> The decision feeds the next useful test, so the loop begins again.</div>

        <div className="checkpoint-rail">
          <div className="checkpoint-label">Extra checks can pause the loop</div>
          {checkpoints.map((rule) => (
            <div className="checkpoint-stop" key={rule.id}>
              <span>{rule.when}</span><strong>{rule.title}</strong>{checkpointReferences[rule.id] && <b>{checkpointReferences[rule.id]}</b>}<p>{rule.instruction}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="policy-sections-grid">
        <section className="policy-rules-section">
          <div className="policy-section-head compact">
            <div><div className="section-kicker"><GitBranch size={14} /> Project rules</div><h2>Code, Git, data, and resources</h2></div>
            <button onClick={() => discussPolicy("project rules for code, Git and GitHub, data, hardware, time, and resources")}><MessageSquareText size={14} /> Discuss</button>
          </div>
          <div className="policy-rule-list">
            {projectRules.map((rule) => <RuleRow key={rule.id} rule={rule} />)}
            {!projectRules.length && <div className="policy-empty-rule">No project rules yet.</div>}
          </div>
        </section>

        <section className="policy-rules-section temporary">
          <div className="policy-section-head compact">
            <div><div className="section-kicker"><Cpu size={14} /> Temporary limits</div><h2>Rules that should end later</h2></div>
            <button onClick={() => discussPolicy("temporary hardware, time, budget, or workflow limits and when each one should end")}><MessageSquareText size={14} /> Discuss</button>
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
          <button onClick={() => discussPolicy("which research ideas need replication, literature review, a quick test, or another special treatment")}><MessageSquareText size={14} /> Discuss</button>
        </div>
        <div className="idea-policy-table">
          {approaches.map((approach) => (
            <div className={selectedNode?.id === approach.id ? "idea-policy-row selected" : "idea-policy-row"} key={approach.id}>
              <div><strong>{approach.title}</strong><span>{approach.status === "dormant" ? "Parked" : approach.status}</span></div>
              <div><small>Next work</small><strong>{workKindLabels[approach.next_work_kind] ?? approach.next_work_kind}</strong><span className="work-policy-reference">{workPolicyReferences[approach.next_work_kind] ?? "Uses the default loop."}</span></div>
              <div><small>Special instructions</small><p>{approach.agent_guidance || "Use the default loop."}</p></div>
              <div><small>Must ask before</small><p>{approach.ask_before || "Use the general checkpoints."}</p></div>
              <button onClick={() => discussIdea(approach)}><MessageSquareText size={14} /> Discuss</button>
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
