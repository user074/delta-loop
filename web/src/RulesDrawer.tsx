import { ArrowDown, ArrowUp, Check, ChevronRight, Copy, MessageSquareText, Plus, RotateCcw, Save, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { checkRules, createRulesDraft, useRules } from "./api";
import type { AgentRule, RulesVersion, Workspace } from "./types";

function copyRules(rules: AgentRule[]): AgentRule[] {
  return rules.map((rule) => ({ ...rule, loop_step_ids: [...rule.loop_step_ids] }));
}

const nestedDetailCategories: AgentRule["category"][] = ["project", "git", "hardware", "data", "resources"];

export default function RulesDrawer({
  open,
  workspace,
  onClose,
  onWorkspace,
  onError,
  onDiscuss,
}: {
  open: boolean;
  workspace: Workspace;
  onClose: () => void;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
  onDiscuss: () => void;
}) {
  const active = workspace.rules_versions.find((version) => version.id === workspace.active_rules_version_id);
  const [editing, setEditing] = useState(false);
  const [rules, setRules] = useState<AgentRule[]>(copyRules(active?.rules ?? []));
  const [selectedVersionId, setSelectedVersionId] = useState(active?.id ?? "");
  const [busy, setBusy] = useState(false);
  const selected = workspace.rules_versions.find((version) => version.id === selectedVersionId) ?? active;

  useEffect(() => {
    if (!open) return;
    setSelectedVersionId(workspace.active_rules_version_id ?? "");
    setRules(copyRules(active?.rules ?? []));
    setEditing(false);
  }, [open, workspace.active_rules_version_id]);

  const changed = useMemo(
    () => JSON.stringify(rules) !== JSON.stringify(active?.rules ?? []),
    [active?.rules, rules],
  );

  function updateRule(index: number, patch: Partial<AgentRule>) {
    setRules((current) => current.map((rule, itemIndex) => itemIndex === index ? { ...rule, ...patch } : rule));
  }

  function moveRule(index: number, change: -1 | 1) {
    setRules((current) => {
      const target = index + change;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function addRule() {
    setRules((current) => [...current, {
      id: `custom-${Date.now()}`,
      title: "New rule",
      instruction: "",
      category: "project",
      when: "Always",
      scope: "Entire project",
      expires_when: "",
      loop_level: "step",
      loop_parent_id: "",
      loop_step_ids: [],
      source_label: "Researcher rule",
      enabled: true,
      cannot_override: false,
    }]);
  }

  function addLoopItem(level: "stage" | "step") {
    const firstStage = rules.find((rule) => rule.category === "loop" && rule.loop_level === "stage");
    setRules((current) => [...current, {
      id: `${level}-${Date.now()}`,
      title: level === "stage" ? "New main stage" : "New loop step",
      instruction: "",
      category: "loop",
      when: "After the previous work is complete",
      scope: "Entire project",
      expires_when: "",
      loop_level: level,
      loop_parent_id: level === "step" ? firstStage?.id ?? "" : "",
      loop_step_ids: [],
      source_label: "Researcher loop",
      enabled: true,
      cannot_override: false,
    }]);
  }

  async function saveAndCheck() {
    setBusy(true);
    try {
      const created = await createRulesDraft(workspace.id, rules);
      const version = created.rules_versions.at(-1)!;
      const checked = await checkRules(workspace.id, version.id);
      onWorkspace(checked);
      setSelectedVersionId(version.id);
      setEditing(false);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not check the policy.");
    } finally {
      setBusy(false);
    }
  }

  async function activate(version: RulesVersion) {
    setBusy(true);
    try {
      const updated = await useRules(workspace.id, version.id);
      onWorkspace(updated);
      setSelectedVersionId(version.id);
      setRules(copyRules(version.rules));
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not use this policy.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <div className="rules-backdrop" role="presentation">
      <aside className="rules-drawer" aria-label="Research loop and policy">
        <div className="rules-head">
          <div>
            <div className="section-kicker"><ShieldCheck size={14} /> Research loop and policy</div>
            <h2>Change what the agent actually does</h2>
            <p>Main stages are the high-level cycle. Loop steps sit inside a stage. Code, data, hardware, file, and Git instructions belong inside the steps that use them. Work already started keeps the version it received.</p>
          </div>
          <div className="rules-head-actions">
            <button className="discuss-button" onClick={onDiscuss}><MessageSquareText size={14} /> Chat</button>
            <button className="icon-button" onClick={onClose} aria-label="Close policy"><X size={18} /></button>
          </div>
        </div>

        <div className="rules-layout">
          <div className="rules-version-list">
            <strong>Saved versions</strong>
            {workspace.rules_versions.slice().reverse().map((version) => (
              <button
                key={version.id}
                className={selected?.id === version.id ? "selected" : ""}
                onClick={() => { setSelectedVersionId(version.id); setEditing(false); }}
              >
                <div><span>Version {version.version}</span><small>{version.status === "active" ? "Used now" : version.status === "checked" ? "Checked" : version.status === "retired" ? "Used before" : "Has problems"}</small></div>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>

          <div className="rules-content">
            {!editing && selected ? (
              <>
                <div className="rules-content-head">
                  <div><div className="section-kicker">Version {selected.version}</div><h3>{selected.status === "active" ? "Policy used for new work" : "Saved policy"}</h3></div>
                  <div className="rules-actions">
                    {selected.id === active?.id && <button onClick={() => { setRules(copyRules(selected.rules)); setEditing(true); }}><Copy size={14} /> Edit a copy</button>}
                    {selected.status === "checked" && <button className="use-rules" disabled={busy} onClick={() => activate(selected)}><Check size={14} /> Use this policy</button>}
                    {selected.status === "retired" && <button disabled={busy} onClick={() => activate(selected)}><RotateCcw size={14} /> Go back to these</button>}
                  </div>
                </div>
                {selected.problems.length > 0 && <div className="rules-problems">{selected.problems.map((problem) => <p key={problem}>{problem}</p>)}</div>}
                <div className="rules-read-list">
                  {selected.rules.map((rule) => (
                    <div className={rule.enabled ? "rule-read-card" : "rule-read-card disabled"} key={rule.id}>
                      <div><strong>{rule.title}</strong><span>{rule.category === "loop" ? rule.loop_level === "stage" ? "Main stage" : `Step in ${selected.rules.find((item) => item.id === rule.loop_parent_id)?.title ?? "unassigned stage"}` : rule.loop_step_ids.length ? `Detail in ${rule.loop_step_ids.length} loop ${rule.loop_step_ids.length === 1 ? "step" : "steps"}` : rule.category}</span>{rule.cannot_override && <span>Required</span>}</div>
                      <small className="rule-meta">{rule.when} · {rule.scope}{rule.expires_when ? ` · Until ${rule.expires_when}` : ""}</small>
                      <p>{rule.instruction}</p>
                      {rule.source_label && <small className="rule-source">Source: {rule.source_label}</small>}
                      {!rule.enabled && <small>Turned off</small>}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="rules-content-head">
                  <div><div className="section-kicker">New version</div><h3>Edit a copy safely</h3><p>Your current policy stays in use until this copy passes its checks and you choose to use it. The check is done by code and does not spend agent tokens.</p></div>
                  <div className="rules-actions"><button onClick={() => setEditing(false)}>Cancel</button><button className="use-rules" onClick={saveAndCheck} disabled={!changed || busy}><Save size={14} /> Save and check</button></div>
                </div>
                <div className="rules-edit-list">
                  {rules.map((rule, index) => (
                    <div className="rule-edit-card" key={rule.id}>
                      <div className="rule-edit-top">
                        <label><input type="checkbox" checked={rule.enabled} disabled={rule.cannot_override} onChange={(event) => updateRule(index, { enabled: event.target.checked })} /> Use this rule</label>
                        <div className="rules-actions">
                          <button aria-label="Move up" title="Move up" disabled={index === 0} onClick={() => moveRule(index, -1)}><ArrowUp size={14} /></button>
                          <button aria-label="Move down" title="Move down" disabled={index === rules.length - 1} onClick={() => moveRule(index, 1)}><ArrowDown size={14} /></button>
                          {rule.cannot_override ? <span>Required</span> : <button onClick={() => setRules((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={14} /> Remove</button>}
                        </div>
                      </div>
                      <label><span>Short name</span><input disabled={rule.cannot_override} value={rule.title} onChange={(event) => updateRule(index, { title: event.target.value })} /></label>
                      <label><span>Type</span><select disabled={rule.cannot_override} value={rule.category} onChange={(event) => {
                        const category = event.target.value as AgentRule["category"];
                        const firstStage = rules.find((item) => item.category === "loop" && item.loop_level === "stage");
                        updateRule(index, { category, ...(category === "loop" ? { loop_level: "step", loop_parent_id: firstStage?.id ?? "", loop_step_ids: [] } : {}), ...(!nestedDetailCategories.includes(category) ? { loop_step_ids: [] } : {}) });
                      }}><option value="loop">Research loop</option><option value="checkpoint">Extra check</option><option value="project">Agent and file boundaries</option><option value="git">Git and GitHub</option><option value="hardware">Hardware</option><option value="data">Data</option><option value="resources">Time and resources</option><option value="temporary">Temporary</option></select></label>
                      {rule.category === "loop" && <label><span>Place in the loop</span><select value={rule.loop_level} onChange={(event) => {
                        const loopLevel = event.target.value as AgentRule["loop_level"];
                        const firstStage = rules.find((item) => item.category === "loop" && item.loop_level === "stage" && item.id !== rule.id);
                        updateRule(index, { loop_level: loopLevel, loop_parent_id: loopLevel === "stage" ? "" : firstStage?.id ?? "" });
                      }}><option value="stage">Main stage</option><option value="step">Step inside a stage</option></select></label>}
                      {rule.category === "loop" && rule.loop_level === "step" && <label><span>Which main stage?</span><select value={rule.loop_parent_id} onChange={(event) => updateRule(index, { loop_parent_id: event.target.value })}><option value="">Choose a stage</option>{rules.filter((item) => item.category === "loop" && item.loop_level === "stage" && item.id !== rule.id).map((stage) => <option value={stage.id} key={stage.id}>{stage.title}</option>)}</select></label>}
                      {nestedDetailCategories.includes(rule.category) && <fieldset className="rule-step-assignment" disabled={rule.cannot_override}>
                        <legend>Which loop steps use this detail?</legend>
                        <p>Select every place where the agent should see this instruction.</p>
                        {rules.filter((item) => item.category === "loop" && item.loop_level === "step").map((step) => (
                          <label key={step.id}>
                            <input
                              type="checkbox"
                              checked={rule.loop_step_ids.includes(step.id)}
                              onChange={(event) => updateRule(index, {
                                loop_step_ids: event.target.checked
                                  ? [...rule.loop_step_ids, step.id]
                                  : rule.loop_step_ids.filter((stepId) => stepId !== step.id),
                              })}
                            />
                            <span>{rules.find((item) => item.id === step.loop_parent_id)?.title ?? "Unassigned stage"} · {step.title}</span>
                          </label>
                        ))}
                      </fieldset>}
                      <label><span>When does it apply?</span><input disabled={rule.cannot_override} value={rule.when} onChange={(event) => updateRule(index, { when: event.target.value })} /></label>
                      <label><span>Where does it apply?</span><input disabled={rule.cannot_override} value={rule.scope} onChange={(event) => updateRule(index, { scope: event.target.value })} /></label>
                      {rule.category === "temporary" && <label><span>When does it end?</span><input disabled={rule.cannot_override} value={rule.expires_when} onChange={(event) => updateRule(index, { expires_when: event.target.value })} /></label>}
                      <label><span>Where did this instruction come from?</span><input disabled={rule.cannot_override} value={rule.source_label} placeholder="For example: lab rule or delta-research Phase 3" onChange={(event) => updateRule(index, { source_label: event.target.value })} /></label>
                      <label><span>What the agent must do</span><textarea disabled={rule.cannot_override} rows={3} value={rule.instruction} onChange={(event) => updateRule(index, { instruction: event.target.value })} /></label>
                    </div>
                  ))}
                  <div className="add-rule-options">
                    <button className="add-rule-button" onClick={() => addLoopItem("stage")}><Plus size={15} /> Add main stage</button>
                    <button className="add-rule-button" onClick={() => addLoopItem("step")}><Plus size={15} /> Add loop step</button>
                    <button className="add-rule-button" onClick={addRule}><Plus size={15} /> Add other rule</button>
                  </div>
                </div>
                <div className="rules-preview">
                  <div><strong>What new work will tell the agent</strong><span>about {Math.ceil(rules.filter((rule) => rule.enabled).reduce((total, rule) => total + rule.instruction.length, 0) / 4)} tokens</span></div>
                  <pre>{rules.filter((rule) => rule.enabled).map((rule) => `- When ${rule.when || "[choose when]"}: ${rule.instruction || "[write what the agent should do]"} Applies to ${rule.scope || "[choose where]"}.${rule.expires_when ? ` Ends ${rule.expires_when}.` : ""}`).join("\n")}</pre>
                </div>
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
