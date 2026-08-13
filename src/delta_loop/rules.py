from __future__ import annotations

from .models import AgentRule, RulesVersion


POLICY_SCHEMA_VERSION = 8

# These were the first POC's simplified loop. Their jobs now live in the complete
# delta-research cycle below, so keeping them as loop steps would show the work twice.
LEGACY_LOOP_RULE_IDS = {
    "review-every-result",
    "choose-next-direction",
    "update-research-map",
    "state-result-limits",
}

LEGACY_RULE_INSTRUCTIONS = {
    "stage-implementation": (
        "Turn the selected idea into a precise, bounded, and executable piece of work.",
    ),
    "loop-create-plan": (
        "Write PLAN.md with the question, method, data and resources, commands, success and stop conditions, "
        "literature status, active policy, and time or compute limits. Preserve the initial plan before handing "
        "off the work.",
    ),
    "stage-experimentation": (
        "Run the sealed work without silently changing the scientific question or comparison.",
    ),
    "loop-run-worker": (
        "Give a worker the sealed plan, exact resources, environment, and policy. The worker may run, debug, "
        "plot, and report within that scope, and must stop for blockers or changes that require approval.",
        "Give a worker the sealed plan, exact resources, environment, and policy. The worker may run, debug, "
        "plot, repair scope-preserving failures, and report within that scope. If the worker cannot finish, the "
        "supervisor should revise the package or choose another useful path without waiting for routine "
        "researcher approval.",
        "Give the worker the test intent, starting method, resources, boundaries, environment, and policy. "
        "The worker may revise code, commands, implementation, and intermediate steps; debug; replace a "
        "broken technique; and rerun within the saved limits. Record meaningful adaptations, but never count "
        "a changed plan as a failure. Preserve the intended idea, fair comparison, measurement, and hard boundaries.",
    ),
    "loop-review-result": (
        "Read the report, check that the intended comparison was followed, decide whether the result is "
        "trustworthy, separate what happened from its interpretation, and state what it cannot prove.",
        "Read the final method and result. First decide whether the execution produced trustworthy evidence; "
        "then classify that evidence as supporting the idea, challenging the idea, inconclusive, invalid, or "
        "not applicable. Record implementation adaptations separately. A changed starting plan is not a "
        "negative result and must not increment any failure or evidence-against count.",
    ),
    "controlled-plan-amendments": (
        "Keep the initial plan unchanged. Record scope-preserving execution repairs in the live plan; make a new "
        "run for a changed hypothesis, main comparison, dataset family, or success condition.",
        "Keep the initial test brief as provenance and record the final method plus meaningful adaptations. "
        "Implementation changes, repaired commands, and revised intermediate steps are normal and do not make "
        "the run fail. If the idea, comparison meaning, or measurement changes, link the result to a revised "
        "test instead of labeling the original idea as failed.",
    ),
    "continuous-research": (
        "Choose, run, review, and record one useful piece of work after another without asking for plan, "
        "implementation, interpretation, map-update, or promotion approval. Resolve ambiguity with the "
        "smallest discriminating test. If one path is blocked, record why, park it when appropriate, and "
        "continue with another eligible path. Stop only for a saved success or stop condition, an exhausted "
        "resource limit, an action prohibited by policy, or when no safe useful work remains.",
        "Choose, run, review, and record one useful piece of work after another without asking for plan, "
        "implementation, interpretation, map-update, or promotion approval. Resolve ambiguity with the "
        "smallest discriminating test. Adapt working plans freely inside scientific and policy boundaries; "
        "never count a plan revision as a failed experiment. If one path is blocked, record why, park it when appropriate, and "
        "continue with another eligible path. Stop only for a saved success or stop condition, an exhausted "
        "resource limit, an action prohibited by policy, or when no safe useful work remains.",
    ),
    "real-work-first": (
        "Use the work budget to produce the requested research result or project file. Do not spend "
        "it rehearsing Delta Loop, retesting the control flow, or writing progress narration unless "
        "the approved plan specifically requires that work.",
    ),
    "plan-exact-inputs": (
        "Put the exact dataset, checkpoint, prior artifact, output folder, and environment paths in the plan. "
        "Do not leave the worker to guess or silently substitute a different resource.",
    ),
    "plan-hardware-and-execution": (
        "Use INFRA.md to choose device placement, precision, parallelism, storage, and direct or SLURM execution. "
        "Request only the hardware needed and put the exact launch command in the plan.",
    ),
    "show-work": (
        "Save commands, measurements, plots, and useful files in the assigned output folder and end "
        "with a short plain-language summary.",
    ),
    "loop-finish-cycle": (
        "Follow the active Git and publishing rules, then check the recorded stop conditions. If no "
        "condition applies, continue to the next cycle in the same supervisor session.",
    ),
    "ask-before-full-study": (
        "Stop and ask the researcher before moving from a small or confirming test into a full study.",
    ),
    "git-reviewed-work": (
        "Commit meaningful reviewed work in a focused commit, and ask the researcher before pushing "
        "or changing shared GitHub state.",
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
            instruction="Turn the selected idea into a bounded test brief with clear scientific intent and a practical starting approach.",
            category="loop",
            when="After the next test is chosen",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-create-plan",
            title="Write a flexible test brief",
            instruction=(
                "Write PLAN.md with the idea being tested, intended comparison, measurement, scientific and policy "
                "boundaries, resource limit, and a starting method. Preserve the initial brief for audit, but do not "
                "treat its implementation steps or command as an immutable contract."
            ),
            category="loop",
            when="After the next work is chosen",
            loop_parent_id="stage-implementation",
            source_label="delta-research · Supervisor Phase 3",
        ),
        AgentRule(
            id="stage-experimentation",
            title="Experimentation",
            instruction="Test the idea while adapting implementation details as needed to obtain trustworthy evidence.",
            category="loop",
            when="After the plan is ready",
            loop_level="stage",
            source_label="delta-research · research cycle",
        ),
        AgentRule(
            id="loop-run-worker",
            title="Let the worker adapt the test",
            instruction=(
                "Give the worker the test intent, starting method, resources, boundaries, environment, and policy. "
                "The worker may revise code, commands, implementation, and intermediate steps; debug; replace a "
                "broken technique; and retry inside the same research run until it produces a valid test or reaches "
                "a hard boundary. Use `delta work retry` for a repaired command. Do not create another package or run "
                "for a minor edit, command repair, or debugging attempt. Record meaningful adaptations, but never count "
                "them as research progress. Preserve the intended idea, fair comparison, measurement, and hard boundaries."
            ),
            category="loop",
            when="After the test brief is ready",
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
            title="Judge what the test says about the idea",
            instruction=(
                "Read the final method and result. First decide whether the execution produced trustworthy evidence; "
                "then classify that evidence as supporting the idea, challenging the idea, inconclusive, invalid, or "
                "not applicable. Do not close and review an intermediate broken implementation when it can still be "
                "repaired; retry it inside the same run. Record implementation adaptations separately. A changed starting "
                "plan is not a negative result and must not increment any failure or evidence-against count."
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
                "Follow the active Git and publishing rules, check the recorded success, stop, and resource "
                "conditions, then immediately begin the next cycle when none applies. Do not wait for the "
                "researcher between cycles."
            ),
            category="loop",
            when="After research memory is updated",
            loop_parent_id="stage-evaluation",
            source_label="delta-research · Supervisor Phases 6b–7",
        ),
        AgentRule(
            id="keep-main-question",
            title="Keep the main question stable",
            instruction=(
                "Keep the saved main research question as the project frame. If evidence suggests a different "
                "question, record it as a connected question or idea and continue useful work under the current "
                "frame instead of stopping for approval."
            ),
            category="checkpoint",
            when="Evidence suggests changing the main project question",
            source_label="Delta Loop · stable project boundary",
            cannot_override=True,
        ),
        AgentRule(
            id="protect-project-files",
            title="Keep project records safe",
            instruction=(
                "Only the supervisor may update STATE.md after checking a result. Workers must not modify it, "
                "and the supervisor must keep observations, working interpretations, uncertainty, and final "
                "claims visibly separate."
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
            title="Promote useful signals to a full study",
            instruction=(
                "Move from a small or confirming test into a full study when the checked evidence, active idea "
                "policy, and saved resource limits justify it. Record why the larger study is worth running and "
                "continue without waiting for approval."
            ),
            category="checkpoint",
            when="A checked result may justify a full study",
            source_label="Researcher preference · Delta Loop",
        ),
        AgentRule(
            id="continuous-research",
            title="Keep researching while unattended",
            instruction=(
                "Choose, run, review, and record one useful piece of work after another without asking for plan, "
                "implementation, interpretation, map-update, or promotion approval. Resolve ambiguity with the "
                "smallest discriminating test. Adapt working plans freely inside scientific and policy boundaries; "
                "keep implementation retries inside the same research run, and never count commands, retries, or plan "
                "revisions as completed research cycles. A cycle ends only with usable evidence or a genuine hard boundary. "
                "If one path is blocked after exhausting reasonable repairs, record why, park it when appropriate, and "
                "continue with another eligible path. Stop only for a saved success or stop condition, an exhausted "
                "resource limit, an action prohibited by policy, or when no safe useful work remains."
            ),
            category="project",
            when="The researcher starts the continuous research loop",
            loop_step_ids=["loop-finish-cycle"],
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
                "Put the starting dataset, checkpoint, prior artifact, output folder, and environment paths in the "
                "test brief. The worker may substitute a scientifically equivalent resource when needed, but must "
                "record the substitution and preserve the intended comparison."
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
                "Request only the hardware needed and put a starting launch command in the test brief; the worker may "
                "repair or replace that command within the saved resource limits."
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
            title="Adapt implementation without calling it failure",
            instruction=(
                "Keep the initial test brief as provenance and record the final method plus meaningful adaptations. "
                "Implementation changes, repaired commands, and revised intermediate steps are normal and do not make "
                "the run fail. Keep all such repairs and retries under the same run ID. Create a new research run only "
                "when the idea, comparison meaning, or measurement changes, or after the current run produces a reviewed "
                "scientific result."
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
                "the test itself requires that work. Do not inflate run counts with minor edits, repeated setup checks, "
                "or repaired commands; those remain implementation tries inside one research run."
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
                "with a short plain-language summary of the final method, adaptations, execution validity, observed "
                "result, and whether the evidence supports, challenges, or leaves the idea unresolved."
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
            migrate_from_legacy = current.instruction in LEGACY_RULE_INSTRUCTIONS.get(current.id, ())
            if migrate_from_legacy and current.instruction != template.instruction:
                current.title = template.title
                current.instruction = template.instruction
                current.when = template.when
                current.source_label = template.source_label
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
