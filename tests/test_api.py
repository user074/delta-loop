from pathlib import Path
import time

from fastapi.testclient import TestClient

from delta_loop.api import create_app
from test_importer import STATE


def test_import_patch_and_protocol_decision_round_trip(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        imported_response = client.post("/api/workspaces/import", json={"path": str(project)})
        assert imported_response.status_code == 200
        imported = imported_response.json()
        workspace_id = imported["id"]
        approach = next(node for node in imported["nodes"] if node["kind"] == "approach")

        patch_response = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{approach['id']}",
            json={"promise": "medium"},
        )
        assert patch_response.status_code == 200
        patched_approach = next(
            node for node in patch_response.json()["nodes"] if node["id"] == approach["id"]
        )
        assert patched_approach["promise"] == "medium"

        decision_response = client.post(
            f"/api/workspaces/{workspace_id}/protocol-decisions",
            json={
                "node_id": approach["id"],
                "action": "promote",
                "rationale": "The minimal probe produced a valid directional signal.",
            },
        )
        assert decision_response.status_code == 200
        decided = decision_response.json()
        decided_approach = next(node for node in decided["nodes"] if node["id"] == approach["id"])
        assert decided_approach["current_stage"] == "signal-confirmation"
        assert decided["decisions"][0]["action"] == "promote"


def test_invalid_workspace_returns_actionable_error(tmp_path: Path) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        response = client.post("/api/workspaces/import", json={"path": str(project)})

    assert response.status_code == 422
    assert "No STATE.md" in response.json()["detail"]


def test_new_idea_can_have_its_own_way_to_test(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        with_idea = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={"kind": "idea", "text": "Try a different representation"},
        ).json()
        new_direction = next(
            node for node in with_idea["nodes"] if node["title"] == "Try a different representation"
        )
        with_test = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "way-to-test",
                "text": "Compare the simplest two encodings",
                "parent_id": new_direction["id"],
            },
        ).json()
        new_test = next(
            node for node in with_test["nodes"] if node["title"] == "Compare the simplest two encodings"
        )
        changed_style = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{new_test['id']}",
            json={"protocol_id": "replication-first"},
        ).json()
        changed_test = next(node for node in changed_style["nodes"] if node["id"] == new_test["id"])
        promoted = client.post(
            f"/api/workspaces/{workspace_id}/protocol-decisions",
            json={"node_id": new_test["id"], "action": "promote", "rationale": "The repeat worked."},
        ).json()
        promoted_test = next(node for node in promoted["nodes"] if node["id"] == new_test["id"])

        reimported = client.post("/api/workspaces/import", json={"path": str(project)}).json()

    assert new_test["parent_id"] == new_direction["id"]
    assert changed_test["current_stage"] == "replicate"
    assert promoted_test["current_stage"] == "controlled-variation"
    assert any(node["id"] == new_direction["id"] for node in reimported["nodes"])
    assert any(node["id"] == new_test["id"] for node in reimported["nodes"])


def test_plan_run_and_review_flow(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        approach = next(node for node in workspace["nodes"] if node["kind"] == "approach")

        workspace = client.post(
            f"/api/workspaces/{workspace_id}/plans",
            json={
                "approach_id": approach["id"],
                "title": "Quick safe test",
                "stage": "minimal-probe",
            },
        ).json()
        plan = workspace["packages"][0]
        workspace = client.patch(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}",
            json={
                "goal": "Check that a small command can run.",
                "instructions": "Print one known line and stop.",
                "measure": "The expected line appears.",
                "command": (
                    "python3 -c \"import os; print('delta-loop-run-ok'); "
                    "print(open(os.environ['DELTA_LOOP_HANDOFF']).readline().strip()); "
                    "open(os.path.join(os.environ['DELTA_LOOP_OUTPUT_DIR'], 'proof.txt'), "
                    "'w').write('ok')\""
                ),
            },
        ).json()
        assert workspace["packages"][0]["status"] == "draft"

        approved = client.post(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}/approve"
        ).json()
        assert approved["packages"][0]["status"] == "ready"
        assert approved["packages"][0]["rules_version_id"] == "rules-v1"

        started = client.post(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}/run"
        ).json()
        run_id = started["attempts"][0]["id"]
        finished = started
        for _ in range(40):
            finished = client.get(f"/api/workspaces/{workspace_id}").json()
            if finished["attempts"][0]["status"] == "finished":
                break
            time.sleep(0.05)
        assert finished["attempts"][0]["status"] == "finished"
        assert "delta-loop-run-ok" in finished["attempts"][0]["output"]
        assert "# Approved plan" in finished["attempts"][0]["output"]
        handoff = Path(finished["attempts"][0]["handoff_file"])
        output_directory = Path(finished["attempts"][0]["output_directory"])
        assert handoff.is_file()
        assert "## Rules for the agent" in handoff.read_text(encoding="utf-8")
        assert (output_directory / "proof.txt").read_text(encoding="utf-8") == "ok"

        reviewed = client.post(
            f"/api/workspaces/{workspace_id}/runs/{run_id}/review",
            json={
                "followed_plan": "yes",
                "trust_result": "yes",
                "what_it_means": "The local run path works.",
                "next_step": "park",
                "notes": "Safe fixture only.",
                "keep_code": False,
            },
        ).json()
        assert reviewed["reviews"][0]["trust_result"] == "yes"
        reviewed_approach = next(node for node in reviewed["nodes"] if node["id"] == approach["id"])
        assert reviewed_approach["status"] == "dormant"


def test_rules_must_be_checked_before_use(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        active_rules = workspace["rules_versions"][0]["rules"]
        new_rule = {
            "id": "save-one-summary",
            "title": "Save one short summary",
            "instruction": "End with five lines explaining what happened.",
            "enabled": True,
            "cannot_override": False,
        }
        drafted = client.post(
            f"/api/workspaces/{workspace_id}/rules/drafts",
            json={"rules": [*active_rules, new_rule]},
        ).json()
        draft = drafted["rules_versions"][-1]
        rejected = client.post(
            f"/api/workspaces/{workspace_id}/rules/{draft['id']}/use"
        )
        assert rejected.status_code == 422

        checked = client.post(
            f"/api/workspaces/{workspace_id}/rules/{draft['id']}/check"
        ).json()
        assert checked["rules_versions"][-1]["status"] == "checked"
        activated = client.post(
            f"/api/workspaces/{workspace_id}/rules/{draft['id']}/use"
        ).json()
        assert activated["active_rules_version_id"] == draft["id"]
