from __future__ import annotations

import re
from pathlib import Path

from .models import Claim, ProjectSnapshot, ResearchNode, RunRecord
from .rules import initial_rules_version


class ImportFailure(ValueError):
    """Raised when a directory is not an importable Delta workspace."""


def _slug(value: str, fallback: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result[:64] or fallback


def _plain(value: str) -> str:
    value = value.strip().strip("`")
    match = re.fullmatch(r"\[([^]]+)]\(([^)]+)\)", value)
    return match.group(1) if match else value


def _section(markdown: str, name: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(name)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(markdown)
    return match.group("body").strip() if match else ""


def _meta(markdown: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _section(markdown, "Meta").splitlines():
        match = re.match(r"^-\s+\*\*(.+?)\*\*:\s*(.*)$", line.strip())
        if match:
            result[match.group(1).strip().lower()] = _plain(match.group(2))
    return result


def _table(section: str) -> list[dict[str, str]]:
    rows = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return []

    def cells(line: str) -> list[str]:
        return [_plain(item.strip()) for item in line.strip("|").split("|")]

    headers = [re.sub(r"\s+", "_", item.lower()) for item in cells(rows[0])]
    parsed: list[dict[str, str]] = []
    for row in rows[1:]:
        values = cells(row)
        if all(re.fullmatch(r":?-{3,}:?", value) for value in values):
            continue
        if len(values) != len(headers):
            continue
        parsed.append(dict(zip(headers, values, strict=True)))
    return parsed


def _confidence(value: str) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _evidence(status: str, confidence: float | None) -> str:
    normalized = status.lower()
    if normalized in {"conflicting", "needs-review"}:
        return "mixed"
    if normalized in {"supported", "rejected"} or (confidence is not None and abs(confidence - 0.5) >= 0.3):
        return "strong"
    if confidence is not None and abs(confidence - 0.5) >= 0.15:
        return "weak"
    return "none"


def _promise(info_gain: str, feasibility: str) -> str:
    values = {info_gain.lower(), feasibility.lower()}
    if values == {"high"}:
        return "high"
    if "low" in values:
        return "low"
    if values & {"high", "med", "medium"}:
        return "medium"
    return "unassessed"


def _summary(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    paragraphs = [
        re.sub(r"\s+", " ", block.strip())
        for block in re.split(r"\n\s*\n", text)
        if block.strip() and not block.lstrip().startswith(("#", "<!--"))
    ]
    return paragraphs[0][:600] if paragraphs else ""


def import_workspace(root_value: str | Path) -> ProjectSnapshot:
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise ImportFailure(f"Project directory does not exist: {root}")

    state_path = root / "STATE.md"
    if not state_path.is_file():
        raise ImportFailure(f"No STATE.md found in {root}")

    markdown = state_path.read_text(encoding="utf-8")
    meta = _meta(markdown)
    name = meta.get("project") or root.name
    goal = meta.get("goal") or "Main question not written yet"

    claims: list[Claim] = []
    for index, row in enumerate(_table(_section(markdown, "BeliefState")), start=1):
        raw_id = row.get("#") or str(index)
        confidence = _confidence(row.get("confidence", ""))
        claims.append(
            Claim(
                id=f"claim-{_slug(raw_id, str(index))}",
                statement=row.get("belief", "Untitled idea"),
                status=row.get("status", "active"),
                confidence=confidence,
                evidence=row.get("key_evidence", ""),
                updated_at=row.get("last_updated", ""),
            )
        )

    runs: list[RunRecord] = []
    for index, row in enumerate(_table(_section(markdown, "Ledger")), start=1):
        raw_id = row.get("run") or f"R{index:03d}"
        belief = row.get("belief", "").lstrip("#")
        runs.append(
            RunRecord(
                id=raw_id,
                delta=row.get("delta", "Untitled run"),
                signal=row.get("signal", "unknown"),
                verdict=row.get("verdict", "unknown"),
                claim_id=f"claim-{_slug(belief, belief)}" if belief else None,
                link=row.get("link") or None,
            )
        )

    question_id = f"question-{_slug(name, 'project')}"
    direction_id = "direction-current-frontier"
    nodes: list[ResearchNode] = [
        ResearchNode(
            id=question_id,
            kind="question",
            title=goal,
            summary=f"Imported from {state_path.name}",
            status="primary",
            promise="high",
            evidence_strength="mixed" if claims else "none",
        ),
        ResearchNode(
            id=direction_id,
            kind="direction",
            title="Ideas to test next",
            summary="The unfinished ideas listed in the project's current to-do list.",
            parent_id=question_id,
            status="primary",
            promise="high",
            evidence_strength="mixed" if runs else "none",
        ),
    ]

    frontier = _table(_section(markdown, "Frontier"))
    claim_by_number = {claim.id.removeprefix("claim-"): claim for claim in claims}
    for index, row in enumerate(frontier, start=1):
        target = row.get("target", "").lstrip("#")
        claim = claim_by_number.get(_slug(target, target))
        nodes.append(
            ResearchNode(
                id=f"approach-{index}-{_slug(row.get('delta', ''), str(index))}",
                kind="approach",
                title=row.get("delta", "Untitled way to test this idea"),
                summary=row.get("rationale", ""),
                parent_id=direction_id,
                status="primary" if index == 1 else "active",
                promise=_promise(row.get("info_gain", ""), row.get("feasibility", "")),
                evidence_strength=_evidence(claim.status, claim.confidence) if claim else "none",
                target_claim_id=claim.id if claim else None,
                current_stage="minimal-probe",
            )
        )

    if not frontier:
        for index, claim in enumerate(claims, start=1):
            nodes.append(
                ResearchNode(
                    id=f"approach-belief-{index}",
                    kind="approach",
                    title=f"Test this idea: {claim.statement}",
                    summary=claim.evidence,
                    parent_id=direction_id,
                    status="primary" if index == 1 else "active",
                    promise="unassessed",
                    evidence_strength=_evidence(claim.status, claim.confidence),
                    target_claim_id=claim.id,
                    current_stage="minimal-probe",
                )
            )

    scratch = [
        line.removeprefix("-").strip()
        for line in _section(markdown, "Scratch").splitlines()
        if line.strip().startswith("-")
    ]
    source_files = ["STATE.md"]
    if (root / "INFRA.md").exists():
        source_files.append("INFRA.md")
    if (root / "SYNTHESIS.md").exists():
        source_files.append("SYNTHESIS.md")

    return ProjectSnapshot(
        id=_slug(str(root), "workspace"),
        root=str(root),
        name=name,
        goal=goal,
        status=meta.get("status", "active"),
        last_updated=meta.get("last_updated", ""),
        source_files=source_files,
        synthesis=_summary(root / "SYNTHESIS.md"),
        claims=claims,
        runs=runs,
        nodes=nodes,
        scratch=scratch,
        rules_versions=[initial_rules_version()],
        active_rules_version_id="rules-v1",
    )
