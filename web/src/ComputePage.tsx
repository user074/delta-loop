import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Computer,
  Eye,
  FileText,
  GitBranch,
  Github,
  HardDrive,
  Layers3,
  LoaderCircle,
  MessageCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { checkCompute, checkGit, listComputeProfiles, resetCompute, updateCompute } from "./api";
import { computeDiscussion, gitDiscussion, type DiscussionRequest } from "./discussions";
import type { ComputeConfig, ComputeProfile, Workspace } from "./types";

type EditableCompute = Pick<
  ComputeConfig,
  | "kind"
  | "name"
  | "ssh_host"
  | "project_path"
  | "run_path"
  | "setup_command"
  | "gpu_devices"
  | "max_parallel"
>;

function editable(compute: ComputeConfig): EditableCompute {
  return {
    kind: compute.kind,
    name: compute.name,
    ssh_host: compute.ssh_host,
    project_path: compute.project_path,
    run_path: compute.run_path,
    setup_command: compute.setup_command,
    gpu_devices: compute.gpu_devices,
    max_parallel: compute.max_parallel,
  };
}

function statusLabel(status: ComputeConfig["status"]) {
  if (status === "ready") return "Ready";
  if (status === "unreachable") return "Cannot connect";
  if (status === "needs-setup") return "Connected, but not ready";
  return "Not checked";
}

export default function ComputePage({
  workspace,
  onWorkspace,
  onError,
  onDiscuss,
}: {
  workspace: Workspace;
  onWorkspace: (workspace: Workspace) => void;
  onError: (message: string) => void;
  onDiscuss: (request: Omit<DiscussionRequest, "id">) => void;
}) {
  const [form, setForm] = useState<EditableCompute>(() => editable(workspace.compute));
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkingGit, setCheckingGit] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [profiles, setProfiles] = useState<ComputeProfile[]>([]);

  useEffect(() => {
    if (!dirty) setForm(editable(workspace.compute));
  }, [dirty, workspace.compute]);

  useEffect(() => {
    listComputeProfiles()
      .then(setProfiles)
      .catch(() => setProfiles([]));
  }, [workspace.id, workspace.compute.last_checked_at]);

  function change<K extends keyof EditableCompute>(key: K, value: EditableCompute[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    onError("");
    try {
      const updated = await updateCompute(workspace.id, form);
      onWorkspace(updated);
      setForm(editable(updated.compute));
      setDirty(false);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not save where work runs.");
    } finally {
      setSaving(false);
    }
  }

  async function check() {
    setChecking(true);
    onError("");
    try {
      const updated = await checkCompute(workspace.id);
      onWorkspace(updated);
      setForm(editable(updated.compute));
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not check this location.");
    } finally {
      setChecking(false);
    }
  }

  async function reset() {
    setResetting(true);
    onError("");
    try {
      const updated = await resetCompute(workspace.id);
      onWorkspace(updated);
      setForm(editable(updated.compute));
      setDirty(false);
      setConfirmReset(false);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not reset the compute setup.");
    } finally {
      setResetting(false);
    }
  }

  async function checkRepository() {
    setCheckingGit(true);
    onError("");
    try {
      const updated = await checkGit(workspace.id);
      onWorkspace(updated);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Could not check the research repository.");
    } finally {
      setCheckingGit(false);
    }
  }

  const compute = workspace.compute;
  const inspection = workspace.compute_inspection;
  const recentRuns = [...workspace.attempts].reverse().slice(0, 6);
  const ready = compute.configured && compute.status === "ready";
  const activeRules = workspace.rules_versions.find((version) => version.id === workspace.active_rules_version_id)?.rules ?? [];
  const gitRules = activeRules.filter((rule) => rule.category === "git" && rule.enabled);
  const git = workspace.git_repository;
  const actualRepository = workspace.project_source === "remote"
    ? compute.configured && compute.kind === "ssh"
      ? `${compute.ssh_host}:${compute.project_path}`
      : "Remote repository not set up"
    : workspace.root;
  const canCheckGit = workspace.project_source !== "remote"
    || (compute.configured && compute.kind === "ssh");
  const hasSetupToReset = compute.configured || Boolean(inspection);
  const formHasSelection = dirty || compute.configured;

  return (
    <section className="compute-page">
      <header className="compute-head">
        <div>
          <div className="section-kicker"><Server size={14} /> Compute</div>
          <h1>{ready ? "Where research work runs" : "Set up where research work runs"}</h1>
          <p>{ready
            ? "This is the active compute setup for research work. Review it here and change it only when the project moves."
            : "Let Codex look at the server first, explain what it found, and ask you about the choices it cannot know."}</p>
        </div>
      </header>

      {ready ? (
        <section className="compute-ready-summary">
          <div className="compute-ready-copy">
            <CheckCircle2 size={24} />
            <div>
              <div className="compute-complete-label">Compute setup complete</div>
              <h2>{compute.kind === "ssh" ? compute.name : "This computer"} is ready</h2>
              <p>{compute.kind === "ssh"
                ? `Research commands run in ${compute.project_path} through ${compute.ssh_host}.`
                : `Research commands run inside ${workspace.root}.`}</p>
            </div>
          </div>
          <div className="compute-ready-facts">
            <div><small>Last checked</small><strong>{compute.last_checked_at ? new Date(compute.last_checked_at).toLocaleString() : "Ready"}</strong></div>
            <div><small>Runs at once</small><strong>{compute.max_parallel}</strong></div>
            <div><small>Allowed GPUs</small><strong>{compute.gpu_devices || "No extra limit"}</strong></div>
          </div>
          <button className="compute-review-button" onClick={() => onDiscuss(computeDiscussion(workspace, compute.kind))}>
            <MessageCircle size={14} /> Review or change with Codex
          </button>
        </section>
      ) : (
        <section className="compute-codex-setup">
          <div className="compute-codex-copy">
            <div className="compute-recommended">Recommended</div>
            <h2>Set up with Codex</h2>
            <p>First choose where the work should run. Codex will use the matching setup process and will not ask you to make this choice again.</p>
            <div className="compute-codex-targets" aria-label="Set up with Codex">
              <button onClick={() => onDiscuss(computeDiscussion(workspace, "local"))}>
                <Computer size={18} />
                <span><strong>This computer</strong><small>Check the current project and local environment</small></span>
              </button>
              <button onClick={() => onDiscuss(computeDiscussion(workspace, "ssh"))}>
                <Server size={18} />
                <span><strong>Remote server</strong><small>Connect with SSH, then inspect the server</small></span>
              </button>
            </div>
            <small><ShieldCheck size={13} /> It will not install software, move data, change Git, or start research work during setup.</small>
          </div>
          <ol className="compute-setup-steps">
            <li><span>1</span><div><strong>Look</strong><p>Check the project, Python environments, GPUs, storage, Git, and any scheduler.</p></div></li>
            <li><span>2</span><div><strong>Ask you</strong><p>Confirm the environment, GPU limits, file locations, and lab or server rules.</p></div></li>
            <li><span>3</span><div><strong>Save and prove</strong><p>Save only what you approve, then test the exact environment setup without running an experiment.</p></div></li>
          </ol>
        </section>
      )}

      {!ready && profiles.length > 0 && (
        <section className="compute-reuse">
          <div className="compute-reuse-head">
            <Layers3 size={20} />
            <div>
              <small>Already known to Delta Loop</small>
              <h2>Reuse a machine you already set up</h2>
              <p>Codex will reuse the machine, hardware, and your usual limits, then check only what belongs to this new project.</p>
            </div>
          </div>
          <div className="compute-reuse-list">
            {profiles.map((profile) => (
              <article key={profile.id}>
                <div className="compute-reuse-title">
                  {profile.kind === "ssh" ? <Server size={18} /> : <Computer size={18} />}
                  <div>
                    <strong>{profile.name}</strong>
                    <small>{profile.kind === "ssh" ? profile.ssh_host : profile.hostname || "This computer"}</small>
                  </div>
                </div>
                <dl>
                  <div><dt>Hardware</dt><dd>{profile.gpus.length ? `${profile.gpus.length} GPU${profile.gpus.length === 1 ? "" : "s"}` : "No GPU recorded"}{profile.cpu ? ` · ${profile.cpu}` : ""}</dd></div>
                  <div><dt>Usual limits</dt><dd>{profile.gpu_devices ? `GPU ${profile.gpu_devices}` : "No GPU limit"} · {profile.max_parallel} run{profile.max_parallel === 1 ? "" : "s"} at once</dd></div>
                  <div><dt>Used by</dt><dd>{profile.source_projects.join(", ")}</dd></div>
                  <div><dt>Checked</dt><dd>{new Date(profile.last_checked_at).toLocaleString()}</dd></div>
                </dl>
                <button onClick={() => onDiscuss(computeDiscussion(workspace, profile.kind, profile))}>
                  <MessageCircle size={14} /> Use with Codex
                </button>
              </article>
            ))}
          </div>
          <p className="compute-reuse-boundary"><ShieldCheck size={13} /> The project folder, environment, run and output folders, repository, branch, and push permission are still checked for each project.</p>
        </section>
      )}

      <div className="compute-layout">
        <details className="compute-main compute-manual">
          <summary>
            <div>
              <span>{compute.configured ? "Saved settings" : "Manual option"}</span>
              <strong>{compute.configured ? "Review or change the saved settings" : "Enter the settings yourself"}</strong>
              <small>{compute.configured ? "Opening this does not change anything until you save." : "Use this only when you already know the exact server setup."}</small>
            </div>
            <ChevronDown size={18} />
          </summary>
          <div className="compute-manual-body">
          <div className="compute-choice" role="group" aria-label="Where research work runs">
            <button
              className={formHasSelection && form.kind === "local" ? "selected" : ""}
              onClick={() => {
                change("kind", "local");
                if (form.kind !== "local") change("name", "This computer");
              }}
            >
              <Computer size={21} />
              <span><strong>This computer</strong><small>Run in the local research folder</small></span>
            </button>
            <button
              className={formHasSelection && form.kind === "ssh" ? "selected" : ""}
              onClick={() => {
                change("kind", "ssh");
                if (form.kind !== "ssh" && form.name === "This computer") change("name", "Remote server");
              }}
            >
              <Server size={21} />
              <span><strong>Remote server</strong><small>Send commands through your existing SSH connection</small></span>
            </button>
          </div>

          {form.kind === "local" ? (
            <div className="compute-local-card">
              <Computer size={22} />
              <div>
                <strong>{workspace.root}</strong>
                <p>Commands run in this folder. Run records and small output files stay in Delta Loop's local data folder.</p>
              </div>
            </div>
          ) : (
            <div className="compute-form-card">
              <div className="compute-form-title">
                <div>
                  <h2>Remote server settings</h2>
                  <p>Delta Loop uses your normal <code>ssh</code> command. It does not store a password or private key.</p>
                </div>
              </div>
              <div className="compute-fields">
                <label>
                  <span>Name shown in Delta Loop</span>
                  <input value={form.name} onChange={(event) => change("name", event.target.value)} placeholder="Lab GPU server" />
                </label>
                <label>
                  <span>SSH host or alias</span>
                  <input value={form.ssh_host} onChange={(event) => change("ssh_host", event.target.value)} placeholder="my-lab-server" />
                  <small>The same name you use after <code>ssh</code> in a terminal.</small>
                </label>
                <label className="wide">
                  <span>Research project folder on the server</span>
                  <input value={form.project_path} onChange={(event) => change("project_path", event.target.value)} placeholder="~/projects/my-research" />
                  <small>The command starts from this folder. The project should already be present there.</small>
                </label>
                <label className="wide">
                  <span>Where run records go on the server</span>
                  <input value={form.run_path} onChange={(event) => change("run_path", event.target.value)} placeholder="~/.delta-loop/runs" />
                  <small>Each run gets its own plan, log, status, and output folder here.</small>
                </label>
                <label className="wide">
                  <span>Environment setup before each run</span>
                  <input value={form.setup_command} onChange={(event) => change("setup_command", event.target.value)} placeholder="source .venv/bin/activate" />
                  <small>Optional. For example, activate a virtual environment or Conda environment.</small>
                </label>
                <label>
                  <span>GPU numbers allowed</span>
                  <input value={form.gpu_devices} onChange={(event) => change("gpu_devices", event.target.value)} placeholder="0" />
                  <small>Optional. Use values such as <code>0</code> or <code>0,1</code>.</small>
                </label>
                <label>
                  <span>Runs allowed at once</span>
                  <input
                    type="number"
                    min={1}
                    max={16}
                    value={form.max_parallel}
                    onChange={(event) => change("max_parallel", Number(event.target.value))}
                  />
                  <small>Delta Loop will refuse extra runs above this limit.</small>
                </label>
              </div>
            </div>
          )}

          <div className="compute-actions">
            <button className="compute-save" disabled={!dirty || saving} onClick={save}>
              {saving ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}
              {saving ? "Saving…" : "Save settings"}
            </button>
            <button disabled={dirty || checking} onClick={check} title={dirty ? "Save the changed settings first" : "Check without starting research work"}>
              {checking ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}
              {checking ? "Checking…" : form.kind === "ssh" ? "Check connection" : "Check folder"}
            </button>
            {dirty && <span>Save before checking.</span>}
          </div>
          </div>
        </details>

        <aside className="compute-side">
          <div className={`compute-status-card ${dirty || !compute.configured ? "unchecked" : compute.status}`}>
            <div className="compute-status-title">
              {dirty || !compute.configured ? <Clock3 size={20} /> : ready ? <CheckCircle2 size={20} /> : compute.status === "unchecked" ? <Clock3 size={20} /> : <CircleAlert size={20} />}
              <div>
                <small>{dirty ? "Editing" : compute.configured ? "Saved location" : "Compute setup"}</small>
                <strong>{dirty ? "Changes not saved" : compute.configured ? `${compute.kind === "ssh" ? compute.name : "This computer"} · ${statusLabel(compute.status)}` : "No location selected"}</strong>
              </div>
            </div>
            <p>{dirty ? `${compute.configured ? `Research still runs on ${compute.kind === "ssh" ? compute.name : "this computer"}.` : "No location is saved yet."} Save the new settings before checking them.` : !compute.configured ? "Choose this computer or a remote server above before starting work." : compute.status_message}</p>
            {!dirty && compute.configured && compute.last_checked_at && <small>Last checked {new Date(compute.last_checked_at).toLocaleString()}</small>}
            {!dirty && compute.configured && (compute.detected_python || compute.detected_git || compute.detected_gpus.length > 0) && (
              <dl>
                {compute.detected_python && <div><dt>Python</dt><dd>{compute.detected_python}</dd></div>}
                {compute.detected_git && <div><dt>Git</dt><dd>{compute.detected_git}</dd></div>}
                {compute.detected_gpus.length > 0 && <div><dt>GPU(s)</dt><dd>{compute.detected_gpus.join("\n")}</dd></div>}
              </dl>
            )}
            {hasSetupToReset && !confirmReset && (
              <button className="compute-reset" onClick={() => setConfirmReset(true)}>
                <RotateCcw size={13} /> Reset setup
              </button>
            )}
            {confirmReset && (
              <div className="compute-reset-confirm">
                <p>Clear the saved location and inspection? Run history and research files will stay.</p>
                <div>
                  <button disabled={resetting} onClick={reset}>{resetting ? "Resetting…" : "Yes, reset"}</button>
                  <button disabled={resetting} onClick={() => setConfirmReset(false)}>Cancel</button>
                </div>
              </div>
            )}
          </div>

          {inspection && (
            <div className="compute-inspection-card">
              <div className="compute-inspection-head">
                <Eye size={18} />
                <div><small>Last read-only inspection</small><strong>{inspection.hostname || inspection.host}</strong></div>
              </div>
              <p>These are detected facts, not decisions about how the server should be used.</p>
              <dl>
                <div><dt>Project</dt><dd>{inspection.project_exists ? "Found" : "Missing"} · {inspection.project_writable ? "writable" : "not writable"}</dd></div>
                <div><dt>Environment</dt><dd>{inspection.environment_candidates.length ? `${inspection.environment_candidates.length} possible choice${inspection.environment_candidates.length === 1 ? "" : "s"}` : inspection.python_path || "Not found"}</dd></div>
                <div><dt>GPU</dt><dd>{inspection.gpus.length ? `${inspection.gpus.length} visible` : "None visible from this connection"}</dd></div>
                <div><dt>Scheduler</dt><dd>{inspection.scheduler === "none" ? "None found" : inspection.scheduler.toUpperCase()}</dd></div>
                <div><dt>INFRA.md</dt><dd>{inspection.has_infra ? "Found — review it first" : "Not found"}</dd></div>
              </dl>
              <small><HardDrive size={12} /> Looked on {new Date(inspection.inspected_at).toLocaleString()}</small>
            </div>
          )}

          <div className="compute-explainer">
            <h2>What happens when work starts</h2>
            <ol>
              <li><span>1</span><p><strong>Prepare</strong>Delta Loop freezes the approved plan and the current compute settings.</p></li>
              <li><span>2</span><p><strong>Run</strong>{!compute.configured ? "Work waits until you choose this computer or a remote server." : compute.kind === "ssh" ? "The plan and command are sent through SSH. The job keeps running if this page closes." : "The command runs in the local research folder."}</p></li>
              <li><span>3</span><p><strong>Watch</strong>Delta Loop reads the job status and recent log. Large result files remain in the run's output folder.</p></li>
            </ol>
          </div>
        </aside>
      </div>

      <section className="git-control">
        <div className="git-control-head">
          <div>
            <div className="section-kicker"><Github size={14} /> Git &amp; GitHub</div>
            <h2>Let Codex keep reviewed work in the repository</h2>
            <p>Check the real research repository, then decide when Codex may commit, push, or must stop and ask you.</p>
          </div>
          <div className="git-control-actions">
            <button onClick={checkRepository} disabled={!canCheckGit || checkingGit}>
              {checkingGit ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}
              {checkingGit ? "Checking…" : "Check repository"}
            </button>
            <button className="primary" onClick={() => onDiscuss(gitDiscussion(workspace))}>
              <MessageCircle size={14} /> Chat with Codex
            </button>
          </div>
        </div>

        <div className="git-shared-machine-note">
          <Github size={16} />
          <p><strong>The machine's Git and GitHub account is shared.</strong> Git identity, credentials, and installed tools already available on this machine do not need to be set up again. Delta Loop still checks this project's repository, branch, remote, and push permission separately.</p>
        </div>

        <div className="git-location-grid">
          <article>
            <GitBranch size={18} />
            <div><small>Research repository</small><strong>{actualRepository}</strong><p>This is where research code and approved result reports should be committed.</p></div>
          </article>
          <article>
            <FileText size={18} />
            <div><small>Delta Loop control folder</small><strong>{workspace.root}</strong><p>{compute.configured && compute.kind === "ssh" ? "These are local notes and controls. This folder is not the remote Git repository." : "Delta Loop's local policy and research notes live inside this project."}</p></div>
          </article>
        </div>

        <div className="git-control-grid">
          <article className={`git-repository-card ${git.state}`}>
            <div className="git-card-title">
              <div>
                <small>Last repository check</small>
                <strong>{git.state === "ready" ? "Repository found" : git.state === "not-repository" ? "Not a Git repository" : git.state === "unreachable" ? "Could not reach repository" : "Not checked"}</strong>
              </div>
              <span>{git.changed_files.length ? `${git.changed_files.length}${git.changes_truncated ? "+" : ""} changed` : git.state === "ready" ? "Clean" : "—"}</span>
            </div>
            <p>{git.message}</p>
            {git.repository_found && (
              <dl>
                <div><dt>Branch</dt><dd>{git.branch || "Unknown"}</dd></div>
                <div><dt>GitHub remote</dt><dd>{git.remote_url || "No remote configured"}</dd></div>
                <div><dt>Tracks</dt><dd>{git.upstream || "No upstream branch"}</dd></div>
                <div><dt>Position</dt><dd>{git.upstream ? `${git.ahead} ahead · ${git.behind} behind` : "Cannot compare without an upstream"}</dd></div>
                <div><dt>Last commit</dt><dd>{git.last_commit || "No commit found"}</dd></div>
              </dl>
            )}
            {git.changed_files.length > 0 && (
              <details>
                <summary>Show changed files</summary>
                <pre>{git.changed_files.slice(0, 12).join("\n")}{git.changed_files.length > 12 || git.changes_truncated ? "\n…" : ""}</pre>
              </details>
            )}
            {git.checked_at && <small>Checked {new Date(git.checked_at).toLocaleString()} without fetching or changing Git.</small>}
          </article>

          <article className={`git-policy-card ${gitRules.length ? "active" : "off"}`}>
            <div className="git-card-title">
              <div><small>Codex Git policy</small><strong>{gitRules.length ? "Agent management is on" : "Agent management is off"}</strong></div>
              <span>{gitRules.length ? "Active" : "Off"}</span>
            </div>
            {gitRules.length ? (
              <div className="git-policy-list">
                {gitRules.map((rule) => (
                  <div key={rule.id}>
                    <strong>{rule.title}</strong>
                    <p>{rule.instruction}</p>
                    <small>When: {rule.when}</small>
                  </div>
                ))}
              </div>
            ) : (
              <p>Codex may inspect Git, but it may not commit or push. Use Chat with Codex to choose the exact rules first.</p>
            )}
            <div className="git-safety-note">
              <ShieldCheck size={15} />
              <p>Permission to commit does not mean permission to push. Large data, checkpoints, caches, secrets, and raw run output stay out unless you explicitly decide otherwise.</p>
            </div>
          </article>
        </div>
      </section>

      <section className="compute-runs">
        <div>
          <div className="section-kicker"><Play size={13} /> Recent work</div>
          <h2>Where each run happened</h2>
        </div>
        {recentRuns.length ? (
          <div className="compute-run-list">
            {recentRuns.map((run) => {
              const plan = workspace.packages.find((item) => item.id === run.package_id);
              return (
                <article key={run.id}>
                  <div className="compute-run-top">
                    <span className={`compute-run-state ${run.status}`}>{run.status}</span>
                    <small>{run.id}</small>
                  </div>
                  <strong>{plan?.title ?? "Research run"}</strong>
                  <p>{run.executor === "ssh" ? `${run.compute_name} · ${run.remote_host}` : "This computer"}</p>
                  <code>{(run.executor === "ssh" ? run.remote_output_directory : run.output_directory) || (run.status === "starting" || run.status === "running" ? "Preparing output folder…" : "No output folder was recorded")}</code>
                  {run.error && <em>{run.error}</em>}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="compute-empty-runs">No work has been started through Delta Loop yet.</div>
        )}
      </section>
    </section>
  );
}
