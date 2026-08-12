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

export function questionDiscussion(workspace: Workspace): Omit<DiscussionRequest, "id"> {
  const question = workspace.nodes.find((node) => node.kind === "question");
  return {
    nodeId: question?.id ?? null,
    topic: "the main question",
    prompt: [
      ...opening("whether the main research question should change"),
      `The question currently shown is: ${workspace.goal}`,
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
  const directions = workspace.nodes.filter((node) => node.kind === "direction");
  const approaches = workspace.nodes.filter((node) => node.kind === "approach");
  const outline = directions.map((direction) => {
    const tests = approaches
      .filter((approach) => approach.parent_id === direction.id)
      .map((approach) => `  - ${approach.title} [${approach.status}]`)
      .join("\n");
    return `- ${direction.title} [${direction.status}]${tests ? `\n${tests}` : ""}`;
  }).join("\n");
  return {
    nodeId: selected?.id ?? null,
    topic: selected ? `the research map around ${selected.title}` : "the research idea map",
    prompt: [
      ...opening("how the research question branches into ideas and ways to test them"),
      `The map currently shown is:\n${outline || "No ideas have been added yet."}`,
      selected ? `The researcher currently has this selected: ${selected.title}` : "No particular node is selected.",
      "Run `delta map show` before asking your first question. Help the researcher develop, clarify, split, combine, move, or park ideas and ways to test them. Do not start the research work itself.",
      "Do not change the map until the researcher clearly agrees. Then use `delta map add-idea`, `delta map add-test`, or `delta map update` to save the agreed map. Use `delta map --help` when needed. Never delete history; park an idea with `--status dormant` instead.",
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
