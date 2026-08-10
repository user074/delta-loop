from __future__ import annotations

from .models import AgentRule, RulesVersion


def initial_rules_version() -> RulesVersion:
    return RulesVersion(
        id="rules-v1",
        version=1,
        status="active",
        rules=[
            AgentRule(
                id="keep-main-question",
                title="Do not change the main question",
                instruction=(
                    "Do not change the main research question, the main comparison, or the measurement without "
                    "stopping and asking the researcher."
                ),
                category="checkpoint",
                when="Before changing the question, main comparison, or measurement",
                cannot_override=True,
            ),
            AgentRule(
                id="protect-project-files",
                title="Keep project records safe",
                instruction=(
                    "Do not rewrite the project's central STATE.md or accept a scientific conclusion on the "
                    "researcher's behalf."
                ),
                category="project",
                when="Whenever project records are updated",
                cannot_override=True,
            ),
            AgentRule(
                id="start-with-small-test",
                title="Quick Test",
                instruction=(
                    "When the plan says Quick test, reuse existing code and run the smallest test that can show "
                    "whether the idea is worth checking again."
                ),
                category="loop",
                when="A new idea is ready to test",
            ),
            AgentRule(
                id="review-every-result",
                title="Review every result",
                instruction=(
                    "After a test finishes, check whether it followed the intended comparison, whether the result "
                    "is trustworthy, and what it does and does not show."
                ),
                category="loop",
                when="A test finishes",
            ),
            AgentRule(
                id="choose-next-direction",
                title="Choose the next direction",
                instruction=(
                    "After reviewing a result, choose whether to repeat it, change the test, go deeper, try another "
                    "idea, or park the current idea."
                ),
                category="loop",
                when="A result has been reviewed",
            ),
            AgentRule(
                id="update-research-map",
                title="Keep the research map current",
                instruction=(
                    "After deciding what a result means, update the relevant idea, testing approach, evidence, and "
                    "next direction in the research map."
                ),
                category="loop",
                when="A next direction is chosen",
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
            ),
            AgentRule(
                id="ask-before-full-study",
                title="Ask before a full study",
                instruction=(
                    "Stop and ask the researcher before moving from a small or confirming test into a full study."
                ),
                category="checkpoint",
                when="Before starting a full study",
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
            ),
            AgentRule(
                id="state-result-limits",
                title="Say what the result cannot prove",
                instruction=(
                    "In the result, clearly separate what happened from what it might mean, and say what this test "
                    "cannot prove."
                ),
                category="loop",
                when="A result is summarized",
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
            ),
            AgentRule(
                id="git-reviewed-work",
                title="Git workflow",
                instruction=(
                    "Commit meaningful reviewed work in a focused commit, and ask the researcher before pushing "
                    "or changing shared GitHub state."
                ),
                category="git",
                when="Reviewed work changes the project",
                enabled=False,
            ),
        ],
        checked_at=None,
        activated_at=None,
    )


def upgrade_policy_rules(version: RulesVersion) -> tuple[list[AgentRule], bool]:
    baseline = {rule.id: rule for rule in initial_rules_version().rules}
    upgraded = [rule.model_copy(deep=True) for rule in version.rules]
    changed = False
    by_id = {rule.id: rule for rule in upgraded}
    for rule_id, template in baseline.items():
        current = by_id.get(rule_id)
        if not current:
            upgraded.append(template.model_copy(deep=True))
            changed = True
            continue
        if current.category == "project" and template.category != "project":
            current.category = template.category
            changed = True
        if current.when == "Always" and template.when != "Always":
            current.when = template.when
            changed = True
        if current.scope == "Entire project" and template.scope != "Entire project":
            current.scope = template.scope
            changed = True
    return upgraded, changed


def check_rules(version: RulesVersion) -> list[str]:
    problems: list[str] = []
    required = {
        rule.id: rule for rule in initial_rules_version().rules if rule.cannot_override
    }
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
        if rule.cannot_override and not rule.enabled:
            problems.append(f"Required rule '{rule.title}' cannot be turned off.")
    if not version.rules:
        problems.append("At least one rule is required.")
    by_id = {rule.id: rule for rule in version.rules}
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
