import type { ResearchNode, Workspace } from "./types";

export interface DiscussionRequest {
  id: number;
  nodeId: string | null;
  topic: string;
  prompt: string;
}

function opening(topic: string) {
  return [
    `You are helping the researcher discuss ${topic} in Delta Loop.`,
    "This is a discussion, not a request to start research work. Do not run experiments or edit the research code.",
    "Start by running `delta context` so you understand the current project. Ask short, focused questions and help the researcher make the decision.",
  ];
}

function mapContext(workspace: Workspace) {
  const labels = { question: "Question", direction: "Idea", approach: "Experiment" } as const;
  const nodes = workspace.nodes.map((node) => `- ${labels[node.kind]} [${node.id}]: ${node.title} [${node.status}]`).join("\n");
  const nodeTitles = new Map(workspace.nodes.map((node) => [node.id, node.title]));
  const links = workspace.research_links.map((link) => (
    `- ${nodeTitles.get(link.source_id) ?? link.source_id} --${link.relationship}--> ${nodeTitles.get(link.target_id) ?? link.target_id}`
  )).join("\n");
  return [
    `The map currently contains:\n${nodes || "No research items have been added yet."}`,
    `Its recorded relationships are:\n${links || "No relationships have been added yet."}`,
  ];
}

export function addResearchQuestionDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: null,
    topic: "adding a high-level research question",
    prompt: [
      ...opening("a possible new high-level research question"),
      ...mapContext(workspace),
      "The researcher clicked Add question on the visual research map. Help them decide whether this is genuinely a separate high-level scientific question rather than an idea or experiment under an existing question.",
      "Ask what broad uncertainty they want the project to answer. Offer concise wording of roughly 10–20 words, identify overlap with existing questions, and say whether an existing question should instead be revised.",
      "Do not change the map until the researcher approves the wording. Then use `delta map add-question \"TITLE\" --summary \"SCOPE\"`. If the new question should become the main framing, also use `delta map update QUESTION_ID --status primary --reason \"WHY\"`. Add any meaningful connection only after agreement.",
      "Run `delta map show` after saving and summarize what appeared in the visual map.",
    ].join("\n\n"),
  };
}

export function addIdeaFromQuestionDiscussion(workspace: Workspace, question: ResearchNode): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: question.id,
    topic: `adding an idea for ${question.title}`,
    prompt: [
      ...opening("a new research idea under a selected question"),
      ...mapContext(workspace),
      `The researcher clicked Add idea on this selected question [${question.id}]: ${question.title}`,
      question.summary ? `Question scope: ${question.summary}` : "",
      "Help develop one meaningful mid-level explanation, mechanism, or strategic direction that could answer this question. It must not be merely a task, script, exact comparison, dataset, metric, or single run; those belong at experiment level.",
      "Ask one short question about the researcher's initial thought, then propose concise wording and explain how the idea differs from existing ideas. Check whether it should also explore another recorded question.",
      `After explicit approval, save it with \`delta map add-idea "TITLE" --under ${question.id} --summary "SHORT THESIS"\`. If it also explores another question, add that relationship with \`delta map connect OTHER_QUESTION_ID IDEA_ID --relationship explores --note "WHY"\` only after agreement.`,
      "Run `delta map show` afterward and summarize the new idea and its visible connections.",
    ].filter(Boolean).join("\n\n"),
  };
}

export function addExperimentFromIdeaDiscussion(workspace: Workspace, idea: ResearchNode): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: idea.id,
    topic: `adding an experiment for ${idea.title}`,
    prompt: [
      ...opening("a concrete experiment under a selected research idea"),
      ...mapContext(workspace),
      `The researcher clicked Add experiment on this selected idea [${idea.id}]: ${idea.title}`,
      idea.summary ? `Idea thesis: ${idea.summary}` : "",
      "Help turn the researcher's thought into one concrete experiment: the implementation or intervention, comparison, data, measurement, and what result would distinguish the relevant explanations. Keep it small by default unless the researcher asks for a full study.",
      "Ask only for missing choices that materially change the experiment. Propose the smallest informative version and identify what it cannot establish.",
      `After explicit approval, save it with \`delta map add-test "TITLE" --under ${idea.id} --summary "METHOD AND EVIDENCE"\`. If the same experiment tests or informs another idea, use \`delta map connect OTHER_ID EXPERIMENT_ID --relationship tests|informs --note "WHY"\` only after agreement.`,
      "Do not start the experiment in this discussion. Run `delta map show` afterward and summarize what was added.",
    ].filter(Boolean).join("\n\n"),
  };
}

export function reviseResearchNodeDiscussion(workspace: Workspace, node: ResearchNode): Omit<DiscussionRequest, "id"> {
  const label = node.kind === "question" ? "question" : node.kind === "direction" ? "idea" : "experiment";
  return {
    nodeId: node.id,
    topic: `revising ${node.title}`,
    prompt: [
      ...opening(`revising a selected research ${label}`),
      ...mapContext(workspace),
      `The researcher clicked Revise on this ${label} [${node.id}]: ${node.title}`,
      node.summary ? `Current summary: ${node.summary}` : "",
      `Current status: ${node.status}. Current potential: ${node.promise}.`,
      "Find out whether they want to clarify the wording, materially reframe it, change its status or potential, move its main placement, split it, or merge its meaning with another item. Preserve the distinction between high-level questions, mid-level ideas, and concrete experiments.",
      `Do not change it until the researcher approves both the change and why it evolved. Then use \`delta map update ${node.id} ... --reason "WHY THIS CHANGED"\`. Use dormant to park it without losing it; do not delete it.`,
      "If the revision changes relationships, use `delta map connect` or `delta map disconnect` only for the agreed links. Run `delta map show` after saving and explain the visible change.",
    ].filter(Boolean).join("\n\n"),
  };
}

export function connectResearchNodeDiscussion(workspace: Workspace, node: ResearchNode): Omit<DiscussionRequest, "id"> {
  const label = node.kind === "question" ? "question" : node.kind === "direction" ? "idea" : "experiment";
  return {
    nodeId: node.id,
    topic: `connecting ${node.title} to other research`,
    prompt: [
      ...opening(`how a selected research ${label} relates to another item`),
      ...mapContext(workspace),
      `The researcher clicked Connect on this ${label} [${node.id}]: ${node.title}`,
      "Ask which other question, idea, or experiment they have in mind and what the scientific relationship means. Use explores for question → idea, tests for idea → experiment, supports or challenges for evidence-bearing relationships, informs for useful implications, depends-on for prerequisites, and related only when no more precise meaning fits.",
      "State the proposed direction in plain language before saving it; direction matters. Do not create vague links merely because two items mention similar words.",
      "After explicit approval, use `delta map connect SOURCE_ID TARGET_ID --relationship TYPE --note \"WHY\"`. If replacing an incorrect relationship, add the correct one first, verify it, then use `delta map disconnect LINK_ID` for the old one.",
      "Run `delta map show` afterward and summarize the connection that is now visible.",
    ].join("\n\n"),
  };
}

export function projectSetupDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: workspace.nodes.find((node) => node.kind === "question" && node.status === "primary")?.id
      ?? workspace.nodes.find((node) => node.kind === "question")?.id
      ?? null,
    topic: "setting up this research project",
    prompt: [
      ...opening("an existing project that does not have a research state yet"),
      `The project folder is: ${workspace.root}`,
      "No STATE.md was found. Follow the delta-research initialization approach, adapted for Delta Loop. Do not start experiments, install packages, change Git, or edit the research code during setup.",
      "First explore the repository read-only until you understand its overall purpose, main components, data flow, important entry points, current experiments, and Git state. Read README.md, AGENTS.md or CLAUDE.md, dependency files, relevant source entry points, and experiment scripts. Follow imports or references when needed. Do not read generated data, caches, checkpoints, large artifacts, secrets, or every implementation file.",
      "Do not ask the researcher to invent the structure from scratch. After exploring, lead with your best concise explanation of what the project does and a first draft of its research structure. Let the researcher correct it.",
      "Use three abstraction levels: (1) one or a small number of high-level research questions—the broad scientific problems that should remain meaningful across many experiments, with short titles of roughly 10–20 words and no command, exact hyperparameter, model version, metric threshold, or step-by-step method; (2) normally 2–5 mid-level ideas—distinct explanations, mechanisms, or strategic directions, each with a short conceptual title rather than a task or single run; and (3) concrete experiments—specific implementations, comparisons, datasets, ablations, or measurements. Put precision in summaries and experiments instead of making question or idea titles carry every detail.",
      "Treat this as a graph, not a forced tree. An idea may explore more than one question; an experiment may test or inform more than one idea; and results may support, challenge, inform, depend on, or simply relate to another item. Add only relationships that mean something scientifically.",
      "Continue one short round at a time only where correction is needed: what has already worked or failed; what competing explanations would change the researcher's mind; references, datasets, libraries, checkpoints, or implementations to reuse; and success conditions, time limits, things not to touch, and irreversible actions. Never dump all questions into one form-like message.",
      "Keep project facts found in the repository separate from choices supplied by the researcher. Reuse existing AGENTS.md, CLAUDE.md, README.md, and INFRA.md; do not overwrite them. Delta Loop owns the generated .delta-loop/LOOP.md and .delta-loop/POLICY.md files.",
      "Present a compact proposed setup as a visible map: the high-level question or questions, a few mid-level ideas, concrete experiments, and any meaningful shared or cross-cutting connections; then references and constraints. Include your own best proposal based on the repository instead of only asking questions. Wait for explicit approval before saving anything.",
      "After approval, populate the approved map. Use `delta question set` for the primary question, `delta map add-question` for additional questions, `delta map add-idea --under QUESTION_ID`, and `delta map add-test --under IDEA_ID`. Use `delta map connect SOURCE_ID TARGET_ID --relationship RELATIONSHIP` for additional meaningful connections. Add only agreed behavioral constraints with `delta rules add`; do not turn descriptive project facts into rules.",
      "Finish with exactly one `delta project finish-setup --summary SUMMARY` command, adding one `--reference VALUE` per approved reference and one `--constraint VALUE` per approved constraint. This creates the initial STATE.md and marks setup complete. Do not create or hand-edit STATE.md yourself.",
      "Run `delta context` and `delta map show` afterward. Explain what was created and tell the researcher that compute remains Unset until they choose this computer or a remote server on the Compute page.",
      "Use `delta project finish-setup --help`, `delta map --help`, and `delta rules --help` when needed.",
    ].join("\n\n"),
  };
}

export function remoteProjectSetupDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: workspace.nodes.find((node) => node.kind === "question" && node.status === "primary")?.id
      ?? workspace.nodes.find((node) => node.kind === "question")?.id
      ?? null,
    topic: "setting up the project already on your server",
    prompt: [
      ...opening("an existing research project that stays on a remote server"),
      `Delta Loop created this local notes folder: ${workspace.root}`,
      "The research code is not in that local folder. It stays on the researcher's server. Do not ask the researcher to clone it locally or create STATE.md on the server.",
      "First ask only for two things: the SSH host or alias they already use, and the full path to the existing project on that server. Never ask for a password, private key, token, or other secret.",
      "Opening this setup chat is the researcher's authorization to perform read-only inspection inside that named remote project after they provide those two values. Be as active there as you would be with a local repository; do not wait for separate permission before each safe inspection command.",
      "After receiving both values, run `delta project inspect-remote --host HOST --project PROJECT_PATH` immediately. It recursively maps the repository, skips generated data and secrets, identifies likely entry points, and reads orientation files plus several likely entry points. This is the required starting point, not the end of repository exploration.",
      "Actively follow the structure the inspection reveals. Use `delta project read-remote --host HOST --project PROJECT_PATH PATH [PATH ...]` in focused batches to read the relevant source files, experiment definitions, configuration, and imports needed to understand the project's purpose, main components, data flow, prior work, and current experiment surface. Continue until you can explain the project rather than stopping after the first inventory. Stay inside the named project, do not read secrets or artifacts, and do not explore unrelated server folders.",
      "Also run exactly one `delta compute inspect --host HOST --project PROJECT_PATH` command. This is a bounded, read-only check of the server, environment tools, storage, scheduler, and visible hardware. Do not browse unrelated server folders.",
      "Do not ask the researcher to invent the structure from scratch. Explain in plain language what the project appears to do and propose a first research map from the repository. Keep facts found on the server separate from choices supplied by the researcher. Let them correct your understanding.",
      "Use three abstraction levels: (1) one or a small number of high-level research questions—the broad scientific problems that remain meaningful across many experiments, with short titles of roughly 10–20 words and no command, exact hyperparameter, model version, metric threshold, or step-by-step method; (2) normally 2–5 mid-level ideas—distinct explanations, mechanisms, or strategic directions, each with a short conceptual title rather than a task or individual run; and (3) concrete experiments—specific implementations, comparisons, datasets, ablations, or measurements. Put precision in summaries and experiments instead of making question or idea titles carry every detail.",
      "Treat this as a graph, not a forced tree. An idea may explore more than one question; an experiment may test or inform more than one idea; and results may support, challenge, inform, depend on, or simply relate to another item. Add only relationships that mean something scientifically.",
      "Continue one short round at a time only where correction is needed: what has worked or failed; which competing explanations would change the researcher's mind; references, datasets, libraries, checkpoints, or implementations to reuse; and the exact environment, GPUs, simultaneous runs, data and output locations, Git rules, time limits, and things not to touch. Never dump all questions into one form-like message.",
      "Do not install software, clone or move the project, edit remote files, change Git, create data, or start research work during setup. Reuse existing README.md, AGENTS.md, CLAUDE.md, and INFRA.md. Present one compact proposed research map—high-level questions, a few mid-level ideas, concrete experiments, and meaningful cross-connections—followed by the server settings and rules. Make a real proposal based on the repository, then wait for explicit approval.",
      "After approval, save the remote location with `delta compute set --kind ssh --name NAME --host HOST --project PROJECT_PATH --runs RUN_PATH --setup SETUP_COMMAND --gpus GPU_LIST --max-parallel NUMBER`. Omit optional values only when the researcher explicitly leaves them unrestricted. Run `delta compute check`; do not continue until it reports ready.",
      "Then populate the approved map. Use `delta question set` for the primary question, `delta map add-question` for additional questions, `delta map add-idea --under QUESTION_ID`, and `delta map add-test --under IDEA_ID`. Use `delta map connect SOURCE_ID TARGET_ID --relationship RELATIONSHIP` for additional meaningful connections. Add only agreed behavioral limits with `delta rules add`; do not turn every observed project fact into a rule.",
      "Finish with exactly one `delta project finish-setup --summary SUMMARY` command, adding one `--reference VALUE` per approved reference and one `--constraint VALUE` per approved constraint. This creates STATE.md in the local Delta Loop notes folder, not in the remote repository. Do not create or hand-edit STATE.md yourself.",
      "Finally run `delta context`, `delta map show`, and `delta compute show`. Explain what was saved locally, what points to the server, and that the remote repository was not changed during setup.",
      "Use `delta project inspect-remote --help`, `delta project read-remote --help`, `delta compute --help`, `delta map --help`, and `delta rules --help` when needed.",
    ].join("\n\n"),
  };
}

export function questionDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  const question = workspace.nodes.find((node) => node.kind === "question");
  return {
    nodeId: question?.id ?? null,
    topic: "the main question",
    prompt: [
      ...opening("whether the main research question should change"),
      `The question currently shown is: ${workspace.goal}`,
      "Keep the main question at the broad scientific level: it should organize several competing ideas and remain useful across many experiments. Aim for one short title of roughly 10–20 words. Move exact implementations, model versions, datasets, metrics, thresholds, ablations, and run details down into ideas or experiments instead of putting them in the question title.",
      "Do not change it until the researcher clearly agrees on new wording and the reason for the change.",
      "Once agreed, save it with `delta question set \"NEW QUESTION\" --reason \"REASON\"`. Then summarize exactly what changed.",
    ].join("\n\n"),
  };
}

function ideaOpening(node: ResearchNode, subject: string) {
  return [
    ...opening(subject),
    `The selected way to test the idea is: ${node.title}`,
    "Run `delta policy show` before asking your first question.",
  ];
}

export function ideaPolicyDiscussion(node: ResearchNode): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: node.id,
    topic: "this idea's policy",
    prompt: [
      ...ideaOpening(node, "how the agent should work on this idea"),
      "Discuss the kind of work, the short guidance, and the decisions that require the researcher. Do not start the work itself.",
      "Once the researcher agrees, fill all three fields in one `delta policy set` command using `--kind`, `--guidance`, and `--ask-before`. If no extra stop point is needed, say that the general policy is enough rather than leaving the field unclear. Then summarize what changed.",
    ].join("\n\n"),
  };
}

export function researchMapDiscussion(
  workspace: Workspace,
  selected: ResearchNode | null,
): Omit<DiscussionRequest, "id"> {
  return {
    nodeId: selected?.id ?? null,
    topic: selected ? `the research map around ${selected.title}` : "the research idea map",
    prompt: [
      ...opening("how the research question branches into ideas and ways to test them"),
      ...mapContext(workspace),
      selected ? `The researcher currently has this selected: ${selected.title}` : "No particular node is selected.",
      "Run `delta map show` before asking your first question. Maintain three clear levels: one or a small number of broad questions; normally 2–5 mid-level ideas that represent explanations, mechanisms, or strategic directions; and concrete experiments. Do not force them into a tree: preserve meaningful shared connections across questions, ideas, and experiments. If a supposed idea is really one script, model setting, dataset comparison, ablation, or metric, move it to experiment level. Do not start the research work itself.",
      "Help the researcher develop, clarify, split, combine, move, park, or reopen ideas. Prefer refining a small set of meaningful ideas over adding many shallow branches. Propose a revised tree when the current abstraction is weak rather than only asking what to do.",
      "Do not change the map until the researcher clearly agrees. Then use `delta map add-question`, `delta map add-idea`, `delta map add-test`, `delta map connect`, `delta map disconnect`, or `delta map update --reason \"WHY THIS EVOLVED\"` to save it. Never delete or silently overwrite node history: park an idea with `--status dormant --reason ...`, reopen it with `--status active --reason ...`, and give a reason when renaming, moving, or materially reframing it.",
      "After saving, run `delta map show` again and summarize the visible changes.",
    ].join("\n\n"),
  };
}

export function generalPolicyDiscussion(
  workspace: Workspace,
  focus = "the whole research loop and project policy",
): Omit<DiscussionRequest, "id"> {
  const active = workspace.rules_versions.find((version) => version.id === workspace.active_rules_version_id);
  const current = (active?.rules ?? []).map((rule) => (
    `- [${rule.enabled ? "on" : "off"}] ${rule.category}: ${rule.id === "start-with-small-test" ? "Quick Test" : rule.title}\n  When: ${rule.when}\n  Do: ${rule.instruction}\n  Scope: ${rule.scope}${rule.expires_when ? `\n  Ends: ${rule.expires_when}` : ""}`
  )).join("\n");
  return {
    nodeId: null,
    topic: focus,
    prompt: [
      ...opening(focus),
      `The active policy currently contains:\n${current || "No policy rules are recorded."}`,
      "Run `delta rules show` before asking your first question. A useful rule says when it applies, what the agent must do, where it applies, and—if temporary—when it ends.",
      "Use the categories loop, checkpoint, project, git, hardware, data, resources, and temporary. Keep the research loop short enough for a human to understand.",
      "Required safety rules cannot be removed. Do not change the active policy until the researcher clearly agrees.",
      "For one change, use `delta rules add` or `delta rules update`. For several related changes, run `delta rules show --json`, create one complete updated JSON list in a temporary file, and use `delta rules apply FILE` so they become one version. Use `delta rules --help` when needed.",
      "Using a policy version automatically rewrites `.delta-loop/POLICY.md` and `.delta-loop/LOOP.md` in the research project. LOOP.md is the complete active research loop. Do not edit either generated file by hand.",
      "After saving, run `delta rules show` again and summarize what is active, what is off, and any temporary limit that will expire.",
    ].join("\n\n"),
  };
}

export function computeDiscussion(
  workspace: Workspace,
  target: "local" | "ssh",
): Omit<DiscussionRequest, "id"> {
  const compute = workspace.compute;
  const targetName = target === "local" ? "this computer" : "a remote server";
  const inspectionInstructions = target === "local"
    ? [
        "The researcher chose this computer before opening this chat. Do not ask whether they meant remote work.",
        "Run exactly one bounded read-only inspection with `delta compute inspect --local`. Do not repeat it unless the researcher asks or it fails.",
      ]
    : [
        "The researcher chose a remote server before opening this chat. Do not redirect them to local setup unless they change their mind.",
        "If the saved remote location is not enough, ask only for its SSH host or existing SSH alias and the project folder. Then run exactly one bounded read-only inspection with `delta compute inspect --host HOST --project PROJECT_PATH`. If the saved remote location is correct, run `delta compute inspect` without those options. Do not browse the server broadly or repeat the inspection unless the researcher asks or the first check fails.",
      ];
  return {
    nodeId: null,
    topic: `setting up ${targetName} for research work`,
    prompt: [
      ...opening(`how research work should run on ${targetName}`),
      `The saved location is currently: ${!compute.configured ? "none" : compute.kind === "ssh" ? `${compute.name} over SSH at ${compute.ssh_host}` : "this computer"}.`,
      "Run `delta compute show` before asking your first question.",
      "Follow the delta-research infrastructure principle: first probe objective facts, then interview the researcher about policies and conventions that commands cannot reveal. Keep detected facts and human choices visibly separate.",
      ...inspectionInstructions,
      "Summarize what the inspection found: project and Git state; existing README.md, STATE.md, or INFRA.md; possible environment managers and environments; Python; scheduler; visible GPUs; CPU and memory; and whether the project and run location are writable. A GPU missing on a login node is not proof that the cluster has no GPUs.",
      "Then ask one short round at a time about what cannot be safely inferred: (1) the environment and exact setup command, (2) which GPUs and how many runs may run together, (3) paths and rules for datasets, checkpoints, scratch files, and caches, and (4) login-node, Git, data, or lab rules. Reuse an existing INFRA.md rather than contradicting it.",
      "Use the researcher's existing SSH configuration. Never ask for, display, or save a password, private key, access token, or secret in Delta Loop.",
      "Do not install software, clone a project, move data, edit INFRA.md, change Git, create directories, or start research work during setup. Present the proposed compute settings and any proposed Delta Loop policy rules, and wait for explicit confirmation.",
      "After confirmation, save the location with one `delta compute set` command. Add only the agreed non-secret rules with `delta rules add` or `delta rules update`, then run `delta compute check`. The check must prove that the agreed environment setup resolves Python. Explain exactly what was saved and what remains unverified.",
      "Use `delta compute inspect --help`, `delta compute set --help`, and `delta rules --help` when needed. Do not make the researcher manually fill fields that the inspection and conversation can settle.",
    ].join("\n\n"),
  };
}

export function gitDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  const compute = workspace.compute;
  const repository = workspace.project_source === "remote"
    ? compute.configured && compute.kind === "ssh"
      ? `${compute.ssh_host}:${compute.project_path}`
      : "not set up yet; configure the remote project on Compute before making Git rules"
    : workspace.root;
  return {
    nodeId: null,
    topic: "how Codex should manage Git and GitHub",
    prompt: [
      ...opening("how Codex should manage Git and GitHub for this research project"),
      `The actual research repository should be ${repository}.`,
      `Delta Loop's local control folder is ${workspace.root}. For a remote project this contains notes and policy files; it is not the remote research repository and must not be mistaken for the place to commit research work.`,
      "First run `delta git check`. This is read-only: it must not fetch, pull, switch branches, stage, commit, or push. Explain the current branch, remote, upstream, local changes, and cached ahead/behind counts in plain language. If the repository or GitHub remote is missing, explain what needs setup but do not create or change it yet.",
      "Then ask one short round about the choices that control the agent: (1) when to commit—after each reviewed useful result, only at milestones, or never automatically; (2) whether to stay on the current branch or make a branch for an idea or experiment; (3) what result records belong in GitHub—normally code, configuration, small plots, and a compact reviewed report, while secrets, datasets, checkpoints, caches, and large raw outputs stay out; and (4) when pushing is allowed—ask every time, automatically only after a verified commit, or never.",
      "Treat automatic pushing as an explicit permission. Do not infer it from permission to commit. Ask whether the agent may push, which remote and branch it may push, and whether a pull request is expected. Shared or protected branches need a clear rule.",
      "Offer a concise recommended policy based on the repository state. The rule should say exactly when it applies, what to inspect, what may be staged, which checks must pass, how commits are named, which branch is used, and whether the agent must stop before pushing.",
      "Do not change Git while configuring the policy. After the researcher explicitly approves the wording, save it with `delta rules update git-reviewed-work --on --when \"WHEN\" --scope \"ACTUAL REPOSITORY\" --instruction \"APPROVED RULE\"`. Use additional `delta rules add --category git` rules only when a separate rule is genuinely clearer.",
      "Run `delta rules show` and `delta git show` after saving. Summarize what Codex may commit, what it may push, when it must ask, and which actual repository the rule controls.",
    ].join("\n\n"),
  };
}
