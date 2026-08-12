from __future__ import annotations

from .models import AgentRule, RulesVersion


POLICY_SCHEMA_VERSION = 5

# These were the first POC's simplified loop. Their jobs now live in the complete
# delta-research cycle below, so keeping them as loop steps would show the work twice.
LEGACY_LOOP_RULE_IDS = {
    "review-every-result",
    "choose-next-direction",
    "update-research-map",
    "state-result-limits",
}

LEGACY_RULE_INSTRUCTIONS = {
    "git-reviewed-work": (
        "Commit meaningful reviewed work in a focused commit, and ask the researcher before pushing "
        "or changing shared GitHub state."
    ),
}


def _default_rules() -> list[AgentRule]:
    return [
        AgentRule(
            id="stage-ideation",
            title="Ideation",
            instruction="Understand the current research picture and decide which question is most useful to test next.",
            category="loop",
            when="At the beginning of a cycle",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-read-context",
            title="Read the current research state",
            instruction=(
                "Read STATE.md, the selected idea and its policy, prior reports, INFRA.md when needed, "
                "and the Git status. Find the next run ID and any unfinished run before choosing new work."
            ),
            category="loop",
            when="At the start of every cycle",
            loop_parent_id="stage-ideation",
            source_label="delta-research · Supervisor Phase 1",
        ),
        AgentRule(
            id="loop-ground-and-select",
            title="Choose the next useful test",
            instruction=(
                "Apply the idea status and active policy first. Enforce any enabled literature rule, then "
                "rank eligible work by uncertainty, what the result would distinguish, feasibility, and "
                "the researcher's priority. Do not choose parked or closed work."
            ),
            category="loop",
            when="After the current state is understood",
            loop_parent_id="stage-ideation",
            source_label="delta-research · Supervisor Phase 2",
        ),
        AgentRule(
            id="stage-implementation",
            title="Implementation",
            instruction="Turn the selected idea into a precise, bounded, and executable piece of work.",
            category="loop",
            when="After the next test is chosen",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-create-plan",
            title="Write and seal the run plan",
            instruction=(
                "Write PLAN.md with the question, method, data and resources, commands, success and stop "
                "conditions, literature status, active policy, and time or compute limits. Preserve the "
                "initial plan before handing off the work."
            ),
            category="loop",
            when="After the next work is chosen",
            loop_parent_id="stage-implementation",
            source_label="delta-research · Supervisor Phase 3",
        ),
        AgentRule(
            id="stage-experimentation",
            title="Experimentation",
            instruction="Run the sealed work without silently changing the scientific question or comparison.",
            category="loop",
            when="After the plan is ready",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-run-worker",
            title="Give the work to a bounded worker",
            instruction=(
                "Give a worker the sealed plan, exact resources, environment, and policy. The worker may run, "
                "debug, plot, and report within that scope, and must stop for blockers or changes that require "
                "approval."
            ),
            category="loop",
            when="After the plan is sealed",
            loop_parent_id="stage-experimentation",
            source_label="delta-research · Supervisor Phase 4",
        ),
        AgentRule(
            id="stage-evaluation",
            title="Evaluation",
            instruction="Judge the evidence, update the research picture, and decide whether to continue or stop.",
            category="loop",
            when="After the worker finishes",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-review-result",
            title="Read and check the result",
            instruction=(
                "Read the report, check that the intended comparison was followed, decide whether the result "
                "is trustworthy, separate what happened from its interpretation, and state what it cannot prove."
            ),
            category="loop",
            when="When the worker finishes",
            loop_parent_id="stage-evaluation",
            source_label="delta-research · Supervisor Phase 5",
        ),
        AgentRule(
            id="loop-update-project",
            title="Update research memory and the idea map",
            instruction=(
                "Update STATE.md, the run record and next-work list, SYNTHESIS.md when needed, and the Delta Loop "
                "idea and evidence map. Record new hypotheses and explain why an approach is parked or reopened."
            ),
            category="loop",
            when="After the result is checked",
            loop_parent_id="stage-evaluation",
            source_label="delta-research · Supervisor Phase 6",
        ),
        AgentRule(
            id="loop-finish-cycle",
            title="Save reviewed work and continue",
            instruction=(
                "Follow the active Git and publishing rules, then check the recorded stop conditions. If no "
                "condition applies, continue to the next cycle in the same supervisor session."
            ),
            category="loop",
            when="After research memory is updated",
            loop_parent_id="stage-evaluation",
            source_label="delta-research · Supervisor Phases 6b–7",
        ),
        AgentRule(
            id="keep-main-question",
            title="Do not change the main question",
            instruction=(
                "Do not change the main research question, the main comparison, or the measurement without "
                "stopping and asking the researcher."
            ),
            category="checkpoint",
            when="Before changing the question, main comparison, or measurement",
            source_label="Delta Loop · researcher approval boundary",
            cannot_override=True,
        ),
        AgentRule(
            id="protect-project-files",
            title="Keep project records safe",
            instruction=(
                "Only the supervisor may update STATE.md after checking a result. Workers must not modify it, "
                "and the agent must not accept a scientific conclusion on the researcher's behalf."
            ),
            category="project",
            when="Whenever project records are updated",
            loop_step_ids=["loop-run-worker", "loop-update-project"],
            source_label="delta-research · file ownership contracts",
            cannot_override=True,
        ),
        AgentRule(
            id="start-with-small-test",
            title="Quick Test",
            instruction=(
                "When the idea says Quick test, reuse existing code and run the smallest test that can show "
                "whether the idea is worth checking again."
            ),
            category="checkpoint",
            when="The selected idea says Next work: Quick test",
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="ground-every-hypothesis",
            title="Review literature before testing a hypothesis",
            instruction=(
                "Before empirical work on a new or materially changed hypothesis, complete a focused literature "
                "review for that hypothesis. Use it to sharpen, redirect, or drop the proposed test."
            ),
            category="checkpoint",
            when="A hypothesis is new, changed, or not yet grounded",
            source_label="delta-research · literature grounding gate",
        ),
        AgentRule(
            id="replicate-promising-result",
            title="Replicate before expanding",
            instruction=(
                "When a small test produces a promising difference, repeat the motivating result before "
                "expanding into a larger investigation."
            ),
            category="checkpoint",
            when="A result looks promising",
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="literature-after-milestone",
            title="Check the literature at major milestones",
            instruction=(
                "After a major result changes the research direction, review the closest prior work before "
                "committing to the next large investigation."
            ),
            category="checkpoint",
            when="A major milestone changes the direction",
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="ask-before-full-study",
            title="Ask before a full study",
            instruction=(
                "Stop and ask the researcher before moving from a small or confirming test into a full study."
            ),
            category="checkpoint",
            when="Before starting a full study",
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="read-environment-and-git",
            title="Read the environment and current Git state",
            instruction=(
                "Read the environment, paths, and resources recorded in STATE.md; read INFRA.md when it exists; "
                "record the current branch, working-tree state, and pre-run commit. Keep unrelated changed files out of the run."
            ),
            category="resources",
            when="Before choosing or planning new work",
            loop_step_ids=["loop-read-context"],
            source_label="delta-research · Supervisor Phase 1",
        ),
        AgentRule(
            id="plan-exact-inputs",
            title="Name the exact data, model, and prior files",
            instruction=(
                "Put the exact dataset, checkpoint, prior artifact, output folder, and environment paths in the plan. "
                "Do not leave the worker to guess or silently substitute a different resource."
            ),
            category="data",
            when="While writing the run plan",
            loop_step_ids=["loop-create-plan"],
            source_label="delta-research · PLAN Resources",
        ),
        AgentRule(
            id="plan-hardware-and-execution",
            title="Specify how the work will run",
            instruction=(
                "Use INFRA.md to choose device placement, precision, parallelism, storage, and direct or SLURM execution. "
                "Request only the hardware needed and put the exact launch command in the plan."
            ),
            category="hardware",
            when="While writing the run plan",
            loop_step_ids=["loop-create-plan"],
            source_label="delta-research · Supervisor Phase 3 and INFRA.md",
        ),
        AgentRule(
            id="smoke-test-long-work",
            title="Test a small version before a long run",
            instruction=(
                "For training, long benchmarks, or work expected to take more than 30 minutes, first run a short small-data test. "
                "Check paths, memory, speed, and errors before starting the full run."
            ),
            category="resources",
            when="Before a non-trivial or long run",
            loop_step_ids=["loop-create-plan", "loop-run-worker"],
            source_label="delta-research · Smoke test policy",
        ),
        AgentRule(
            id="controlled-plan-amendments",
            title="Keep the initial plan and record repairs",
            instruction=(
                "Keep the initial plan unchanged. Record scope-preserving execution repairs in the live plan; "
                "make a new run for a changed hypothesis, main comparison, dataset family, or success condition."
            ),
            category="project",
            when="A running plan needs to change",
            loop_step_ids=["loop-create-plan", "loop-run-worker"],
            source_label="delta-research · Controlled plan amendments",
        ),
        AgentRule(
            id="real-work-first",
            title="Spend time on the research work",
            instruction=(
                "Use the work budget to produce the requested research result or project file. Do not spend "
                "it rehearsing Delta Loop, retesting the control flow, or writing progress narration unless "
                "the approved plan specifically requires that work."
            ),
            category="project",
            when="Work time or tokens are allocated",
            loop_step_ids=["loop-create-plan", "loop-run-worker"],
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="show-work",
            title="Leave useful files and a clear summary",
            instruction=(
                "Save commands, measurements, plots, and useful files in the assigned output folder and end "
                "with a short plain-language summary."
            ),
            category="project",
            when="A piece of work ends",
            loop_step_ids=["loop-run-worker", "loop-review-result"],
            source_label="delta-research · worker output and report contract",
        ),
        AgentRule(
            id="git-reviewed-work",
            title="Git workflow",
            instruction=(
                "Inspect the run-scoped diff, keep large or secret files out, stage explicit paths only, run relevant tests, "
                "and make one focused commit. Push only when the researcher has already authorized it or asks for it."
            ),
            category="git",
            when="Reviewed work changes the project",
            loop_step_ids=["loop-finish-cycle"],
            source_label="delta-research · Supervisor Phase 6b",
            enabled=False,
        ),
    ]


def initial_rules_version() -> RulesVersion:
    return RulesVersion(
        id="rules-v1",
        version=1,
        status="active",
        rules=[rule.model_copy(deep=True) for rule in _default_rules()],
        checked_at=None,
        activated_at=None,
    )


def upgrade_policy_rules(version: RulesVersion) -> tuple[list[AgentRule], bool]:
    """Import the real research cycle while preserving user-created policy."""
    baseline = {rule.id: rule for rule in _default_rules()}
    existing: list[AgentRule] = []
    changed = False

    for rule in version.rules:
        if rule.id in LEGACY_LOOP_RULE_IDS:
            changed = True
            continue
        current = rule.model_copy(deep=True)
        template = baseline.get(current.id)
        if template and template.cannot_override:
            if current != template:
                changed = True
            current = template.model_copy(deep=True)
        elif template:
            if (
                current.instruction == LEGACY_RULE_INSTRUCTIONS.get(current.id)
                and current.instruction != template.instruction
            ):
                current.instruction = template.instruction
                changed = True
            if current.category in {"project", "loop"} and current.category != template.category:
                current.category = template.category
                changed = True
            if current.when == "Always" and template.when != "Always":
                current.when = template.when
                changed = True
            if current.category == "loop" and (
                current.loop_level != template.loop_level
                or current.loop_parent_id != template.loop_parent_id
            ):
                current.loop_level = template.loop_level
                current.loop_parent_id = template.loop_parent_id
                changed = True
            if current.loop_step_ids != template.loop_step_ids:
                current.loop_step_ids = list(template.loop_step_ids)
                changed = True
            if not current.source_label and template.source_label:
                current.source_label = template.source_label
                changed = True
        existing.append(current)

    by_id = {rule.id: rule for rule in existing}
    loop_steps: list[AgentRule] = []
    for template in _default_rules():
        if template.category != "loop":
            continue
        current = by_id.pop(template.id, None)
        loop_steps.append((current or template).model_copy(deep=True))
        if current is None:
            changed = True

    non_loop = [rule for rule in existing if rule.id in by_id]
    non_loop_ids = {rule.id for rule in non_loop}
    for template in _default_rules():
        if template.category == "loop" or template.id in non_loop_ids:
            continue
        non_loop.append(template.model_copy(deep=True))
        non_loop_ids.add(template.id)
        changed = True

    upgraded = [*loop_steps, *non_loop]
    if [rule.model_dump() for rule in upgraded] != [rule.model_dump() for rule in version.rules]:
        changed = True
    return upgraded, changed


def check_rules(version: RulesVersion) -> list[str]:
    problems: list[str] = []
    required = {rule.id: rule for rule in _default_rules() if rule.cannot_override}
    seen: set[str] = set()
    for rule in version.rules:
        if not rule.id.strip():
            problems.append("Every rule needs an ID.")
        elif rule.id in seen:
            problems.append(f"The rule ID '{rule.id}' is used more than once.")
        seen.add(rule.id)
        if not rule.title.strip():
            problems.append(f"Rule '{rule.id or 'without an ID'}' needs a short name.")
        if not rule.instruction.strip():
            problems.append(f"Rule '{rule.title or rule.id}' needs an instruction.")
        if not rule.when.strip():
            problems.append(f"Rule '{rule.title or rule.id}' needs to say when it runs.")
        if rule.cannot_override and not rule.enabled:
            problems.append(f"Required rule '{rule.title}' cannot be turned off.")
    if not version.rules:
        problems.append("At least one rule is required.")
    by_id = {rule.id: rule for rule in version.rules}
    enabled_stages = {
        rule.id
        for rule in version.rules
        if rule.enabled and rule.category == "loop" and rule.loop_level == "stage"
    }
    enabled_steps = {
        rule.id
        for rule in version.rules
        if rule.enabled and rule.category == "loop" and rule.loop_level == "step"
    }
    if not enabled_stages:
        problems.append("Keep at least one active main stage in the research loop.")
    for rule in version.rules:
        if not rule.enabled or rule.category != "loop":
            continue
        if rule.loop_level == "stage" and rule.loop_parent_id:
            problems.append(f"Main stage '{rule.title}' cannot sit inside another stage.")
        if rule.loop_level == "step" and rule.loop_parent_id not in enabled_stages:
            problems.append(f"Loop step '{rule.title}' needs an active main stage.")
    for rule in version.rules:
        if not rule.enabled or rule.category == "loop":
            continue
        missing_steps = [step_id for step_id in rule.loop_step_ids if step_id not in enabled_steps]
        if missing_steps:
            problems.append(
                f"Rule '{rule.title}' points to a loop step that is missing or turned off: {', '.join(missing_steps)}."
            )
    for rule_id, baseline in required.items():
        candidate = by_id.get(rule_id)
        if not candidate:
            problems.append(f"Required rule '{baseline.title}' is missing.")
        elif (
            candidate.title != baseline.title
            or candidate.instruction != baseline.instruction
            or candidate.category != baseline.category
            or candidate.when != baseline.when
            or candidate.scope != baseline.scope
            or candidate.expires_when != baseline.expires_when
            or candidate.loop_level != baseline.loop_level
            or candidate.loop_parent_id != baseline.loop_parent_id
            or candidate.loop_step_ids != baseline.loop_step_ids
            or candidate.source_label != baseline.source_label
            or not candidate.enabled
        ):
            problems.append(f"Required rule '{baseline.title}' cannot be changed or turned off.")
    return problems


def render_rules(version: RulesVersion) -> str:
    enabled = [rule for rule in version.rules if rule.enabled]
    if not enabled:
        return ""
    lines = ["Rules for this work:"]
    for rule in enabled:
        line = f"- When {rule.when}: {rule.instruction} Applies to {rule.scope}."
        if rule.expires_when:
            line += f" This rule ends {rule.expires_when}."
        lines.append(line)
    return "\n".join(lines)
