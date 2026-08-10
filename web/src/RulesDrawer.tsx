import { Check, ChevronRight, Copy, Plus, RotateCcw, Save, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { checkRules, createRulesDraft, useRules } from "./api";
import type { AgentRule, RulesVersion, Workspace } from "./types";

function copyRules(rules: AgentRule[]): AgentRule[] {
  return rules.map((rule) => ({ ...rule }));
}

export default function RulesDrawer({
  open,
  workspace,
  onClose,
  onWorkspace,
  onError,
}: {
  open: boolean;
  workspace: Workspace;
  onClose: () => void;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
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
  }, [active, open, workspace.active_rules_version_id]);

  const changed = useMemo(
    () => JSON.stringify(rules) !== JSON.stringify(active?.rules ?? []),
    [active?.rules, rules],
  );

  function updateRule(index: number, patch: Partial<AgentRule>) {
    setRules((current) => current.map((rule, itemIndex) => itemIndex === index ? { ...rule, ...patch } : rule));
  }

  function addRule() {
    setRules((current) => [...current, {
      id: `custom-${Date.now()}`,
      title: "New rule",
      instruction: "",
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
      onError(caught instanceof Error ? caught.message : "Could not check the rules.");
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
      onError(caught instanceof Error ? caught.message : "Could not use these rules.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <div className="rules-backdrop" role="presentation">
      <aside className="rules-drawer" aria-label="Rules for agents">
        <div className="rules-head">
          <div>
            <div className="section-kicker"><ShieldCheck size={14} /> Rules for agents</div>
            <h2>Change how agents should work</h2>
            <p>These rules apply to new plans. Plans you already approved keep the rules they received.</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close rules"><X size={18} /></button>
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
                  <div><div className="section-kicker">Version {selected.version}</div><h3>{selected.status === "active" ? "Rules used for new plans" : "Saved rules"}</h3></div>
                  <div className="rules-actions">
                    {selected.id === active?.id && <button onClick={() => { setRules(copyRules(selected.rules)); setEditing(true); }}><Copy size={14} /> Edit a copy</button>}
                    {selected.status === "checked" && <button className="use-rules" disabled={busy} onClick={() => activate(selected)}><Check size={14} /> Use these rules</button>}
                    {selected.status === "retired" && <button disabled={busy} onClick={() => activate(selected)}><RotateCcw size={14} /> Go back to these</button>}
                  </div>
                </div>
                {selected.problems.length > 0 && <div className="rules-problems">{selected.problems.map((problem) => <p key={problem}>{problem}</p>)}</div>}
                <div className="rules-read-list">
                  {selected.rules.map((rule) => (
                    <div className={rule.enabled ? "rule-read-card" : "rule-read-card disabled"} key={rule.id}>
                      <div><strong>{rule.title}</strong>{rule.cannot_override && <span>Required</span>}</div>
                      <p>{rule.instruction}</p>
                      {!rule.enabled && <small>Turned off</small>}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="rules-content-head">
                  <div><div className="section-kicker">New version</div><h3>Edit a copy safely</h3><p>Your current rules stay in use until this copy passes its checks and you choose to use it. The check is done by code and does not spend agent tokens.</p></div>
                  <div className="rules-actions"><button onClick={() => setEditing(false)}>Cancel</button><button className="use-rules" onClick={saveAndCheck} disabled={!changed || busy}><Save size={14} /> Save and check</button></div>
                </div>
                <div className="rules-edit-list">
                  {rules.map((rule, index) => (
                    <div className="rule-edit-card" key={rule.id}>
                      <div className="rule-edit-top">
                        <label><input type="checkbox" checked={rule.enabled} disabled={rule.cannot_override} onChange={(event) => updateRule(index, { enabled: event.target.checked })} /> Use this rule</label>
                        {rule.cannot_override ? <span>Required</span> : <button onClick={() => setRules((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={14} /> Remove</button>}
                      </div>
                      <label><span>Short name</span><input disabled={rule.cannot_override} value={rule.title} onChange={(event) => updateRule(index, { title: event.target.value })} /></label>
                      <label><span>What the agent must do</span><textarea disabled={rule.cannot_override} rows={3} value={rule.instruction} onChange={(event) => updateRule(index, { instruction: event.target.value })} /></label>
                    </div>
                  ))}
                  <button className="add-rule-button" onClick={addRule}><Plus size={15} /> Add another rule</button>
                </div>
                <div className="rules-preview">
                  <div><strong>What a new plan will tell the agent</strong><span>about {Math.ceil(rules.filter((rule) => rule.enabled).reduce((total, rule) => total + rule.instruction.length, 0) / 4)} tokens</span></div>
                  <pre>{rules.filter((rule) => rule.enabled).map((rule) => `- ${rule.instruction || "[Write this rule]"}`).join("\n")}</pre>
                </div>
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
