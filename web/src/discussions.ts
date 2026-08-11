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
