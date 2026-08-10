from pathlib import Path

import pytest

from delta_loop.importer import ImportFailure, import_workspace


STATE = """# STATE — demo

## Meta
- **project**: demo-project
- **goal**: Determine whether feature A changes outcome B
- **last_updated**: 2026-08-09
- **status**: active

## BeliefState
| # | Parent | Belief | Status | Confidence | Key evidence | Last updated |
|---|---|---|---|---|---|---|
| 1 | — | Feature A matters | active | 0.5 | seed | 2026-08-09 |

## Ledger
| Run | Delta | Signal | Verdict | Belief | Link |
|---|---|---|---|---|---|
| R001 | Baseline | partial | unclear | #1 | REPORTS/R001.md |

## Frontier
| Rank | Delta | Target | Uncertainty | Info gain | Feasibility | Rationale | Blocked by |
|---|---|---|---|---|---|---|---|
| 1 | Run a minimal intervention | #1 | high | high | high | Cheapest discriminating test | — |

## Scratch
- Check matched magnitude before scaling up
"""


def test_import_workspace_normalizes_delta_state(tmp_path: Path) -> None:
    (tmp_path / "STATE.md").write_text(STATE, encoding="utf-8")

    result = import_workspace(tmp_path)

    assert result.name == "demo-project"
    assert result.goal == "Determine whether feature A changes outcome B"
    assert len(result.claims) == 1
    assert len(result.runs) == 1
    approaches = [node for node in result.nodes if node.kind == "approach"]
    assert approaches[0].title == "Run a minimal intervention"
    assert approaches[0].promise == "high"
    assert approaches[0].current_stage == "minimal-probe"
    assert result.scratch == ["Check matched magnitude before scaling up"]


def test_import_workspace_requires_state_file(tmp_path: Path) -> None:
    with pytest.raises(ImportFailure, match="No STATE.md"):
        import_workspace(tmp_path)
