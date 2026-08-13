from __future__ import annotations

from .models import ProtocolProfile, ProtocolStage


def default_protocols() -> list[ProtocolProfile]:
    return [
        ProtocolProfile(
            id="fast-signal-first",
            version=1,
            name="Start small, then check more",
            description=(
                "Start with a quick useful test. The agent checks the result and automatically does more work "
                "when the evidence and saved limits justify it."
            ),
            stages=[
                ProtocolStage(
                    id="minimal-probe",
                    name="Quick test",
                    purpose="See whether the idea causes any noticeable change.",
                    scope="Use existing code, one useful example, one basic comparison, and a small time limit.",
                    permitted_evidence="This only tells you whether the idea is worth checking again.",
                    gate="The agent checks again, changes the test, tries another idea, or parks it based on the result.",
                    budget="Small",
                ),
                ProtocolStage(
                    id="signal-confirmation",
                    name="Check the result",
                    purpose="See whether the first result happens again and is not caused by an obvious mistake.",
                    scope="Run it again, add one fair comparison, and check the most likely alternative reason.",
                    permitted_evidence="This tells you whether a larger study is worth the time and cost.",
                    gate="The agent starts a full study, runs another check, changes the test, or redirects based on the evidence and limits.",
                    budget="Medium",
                ),
                ProtocolStage(
                    id="full-investigation",
                    name="Full study",
                    purpose="Measure how large and reliable the result is, when it works, and when it fails.",
                    scope="Use all planned settings and comparisons, repeat when needed, and study failures.",
                    permitted_evidence="The result may support a final conclusion after you review it.",
                    gate="The agent records the evidence, its limits, and the justified working conclusion, then continues if useful work remains.",
                    budget="Large",
                ),
            ],
        ),
        ProtocolProfile(
            id="replication-first",
            version=1,
            name="Repeat the original first",
            description="Make sure the original result can be repeated before trying to explain or extend it.",
            stages=[
                ProtocolStage(
                    id="replicate",
                    name="Repeat the original",
                    purpose="See whether the original result happens again under the same conditions.",
                    scope="Use the original code, data, measurement, and setup when available.",
                    permitted_evidence="This only tells you whether the original result can be repeated.",
                    gate="The agent fixes routine problems, changes one controlled factor, or redirects based on the result.",
                    budget="Medium",
                ),
                ProtocolStage(
                    id="controlled-variation",
                    name="Change one thing",
                    purpose="See what happens when one part of the original test changes.",
                    scope="Change one chosen item and keep everything else the same.",
                    permitted_evidence="This gives an early view of where the result does or does not hold.",
                    gate="The agent explains the result, tries another controlled change, or redirects based on the evidence and limits.",
                    budget="Medium",
                ),
            ],
        ),
    ]


def next_stage(profile: ProtocolProfile, current_stage: str) -> str | None:
    ids = [stage.id for stage in profile.stages]
    try:
        position = ids.index(current_stage)
    except ValueError:
        return None
    return ids[position + 1] if position + 1 < len(ids) else None
