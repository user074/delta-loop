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
                cannot_override=True,
            ),
            AgentRule(
                id="protect-project-files",
                title="Keep project records safe",
                instruction=(
                    "Do not rewrite the project's central STATE.md or accept a scientific conclusion on the "
                    "researcher's behalf."
                ),
                cannot_override=True,
            ),
            AgentRule(
                id="start-with-small-test",
                title="Start with the smallest useful test",
                instruction=(
                    "When the plan says Quick test, reuse existing code and run the smallest test that can show "
                    "whether the idea is worth checking again."
                ),
            ),
            AgentRule(
                id="real-work-first",
                title="Spend time on the research work",
                instruction=(
                    "Use the work budget to produce the requested research result or project file. Do not spend "
                    "it rehearsing Delta Loop, retesting the control flow, or writing progress narration unless "
                    "the approved plan specifically requires that work."
                ),
            ),
            AgentRule(
                id="state-result-limits",
                title="Say what the result cannot prove",
                instruction=(
                    "In the result, clearly separate what happened from what it might mean, and say what this test "
                    "cannot prove."
                ),
            ),
            AgentRule(
                id="show-work",
                title="Leave useful files and a clear summary",
                instruction=(
                    "Save commands, measurements, plots, and useful files in the assigned output folder and end "
                    "with a short plain-language summary."
                ),
            ),
        ],
        checked_at=None,
        activated_at=None,
    )


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
        elif candidate.instruction != baseline.instruction or not candidate.enabled:
            problems.append(f"Required rule '{baseline.title}' cannot be changed or turned off.")
    return problems


def render_rules(version: RulesVersion) -> str:
    enabled = [rule for rule in version.rules if rule.enabled]
    if not enabled:
        return ""
    lines = ["Rules for this work:"]
    lines.extend(f"- {rule.instruction}" for rule in enabled)
    return "\n".join(lines)
