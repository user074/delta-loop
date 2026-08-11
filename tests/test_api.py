import json
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
        active_rules = next(
            version
            for version in imported["rules_versions"]
            if version["id"] == imported["active_rules_version_id"]
        )["rules"]
        assert imported["policy_schema_version"] == 4
        assert [
            rule["id"] for rule in active_rules
            if rule["category"] == "loop" and rule["loop_level"] == "stage"
        ] == [
            "stage-ideation",
            "stage-implementation",
            "stage-experimentation",
            "stage-evaluation",
        ]
        assert [
            rule["id"] for rule in active_rules
            if rule["category"] == "loop" and rule["loop_level"] == "step"
        ] == [
            "loop-read-context",
            "loop-ground-and-select",
            "loop-create-plan",
            "loop-run-worker",
            "loop-review-result",
            "loop-update-project",
            "loop-finish-cycle",
        ]
        assert any(rule["category"] == "loop" for rule in active_rules)
        assert any(rule["category"] == "checkpoint" for rule in active_rules)
        git_rule = next(rule for rule in active_rules if rule["id"] == "git-reviewed-work")
        assert git_rule["category"] == "git"
        assert git_rule["enabled"] is False
        assert git_rule["loop_step_ids"] == ["loop-finish-cycle"]
        exact_inputs = next(rule for rule in active_rules if rule["id"] == "plan-exact-inputs")
        assert exact_inputs["loop_step_ids"] == ["loop-create-plan"]
        assert exact_inputs["source_label"] == "delta-research · PLAN Resources"
        policy_file = Path(imported["policy_file"])
        loop_file = Path(imported["loop_file"])
        assert policy_file == project / ".delta-loop" / "POLICY.md"
        assert loop_file == project / ".delta-loop" / "LOOP.md"
        policy_text = policy_file.read_text(encoding="utf-8")
        assert "# Active Delta Loop Policy" in policy_text
        assert "**Quick Test**" in policy_text
        assert "start of every cycle" in policy_text
        assert "Default loop imported from" not in policy_text
        assert "Imported source revision" not in policy_text
        assert imported["harness"]["source_url"].endswith("user074/delta-research.git")
        loop_text = loop_file.read_text(encoding="utf-8")
        assert "# Delta Loop Research Instructions" in loop_text
        assert "complete active research loop" in loop_text
        assert "Do not look for or combine it with another supervisor specification" in loop_text
        assert "### 1. Ideation" in loop_text
        assert "#### 1.1 Read the current research state" in loop_text
        assert "### 4. Evaluation" in loop_text
        assert "#### 4.3 Save reviewed work and continue" in loop_text
        assert "##### Details for this step" in loop_text
        assert "Name the exact data, model, and prior files" in loop_text
        assert "delta-research · PLAN Resources" in loop_text
        assert "Git workflow" not in loop_text
        assert "SUPERVISOR.md" not in loop_text
        assert "Initial default came from" not in loop_text
        assert "## Delta Loop Policy" in loop_text
        assert "DELTA_LOOP_WORKSPACE_ID" in loop_text

        patch_response = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{approach['id']}",
            json={
                "promise": "medium",
                "next_work_kind": "literature-review",
                "agent_guidance": "Read the closest prior work before proposing an experiment.",
                "ask_before": "Ask before changing the main dataset.",
            },
        )
        assert patch_response.status_code == 200
        patched_approach = next(
            node for node in patch_response.json()["nodes"] if node["id"] == approach["id"]
        )
        assert patched_approach["promise"] == "medium"
        assert patched_approach["next_work_kind"] == "literature-review"
        assert "prior work" in patched_approach["agent_guidance"]
        policy_text = policy_file.read_text(encoding="utf-8")
        assert "Literature review" in policy_text
        assert "Read the closest prior work" in policy_text
        assert "Ask before changing the main dataset" in policy_text

        changed_question = client.patch(
            f"/api/workspaces/{workspace_id}",
            json={
                "goal": "Which representation change best explains the observed result?",
                "reason": "The first result narrowed the question.",
            },
        ).json()
        assert changed_question["question_history"][0]["previous"] == imported["goal"]
        assert changed_question["question_history"][0]["current"] == changed_question["goal"]
        question_node = next(node for node in changed_question["nodes"] if node["kind"] == "question")
        assert question_node["title"] == changed_question["goal"]

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
        reimported = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        assert reimported["goal"] == changed_question["goal"]
        preserved_approach = next(node for node in reimported["nodes"] if node["id"] == approach["id"])
        assert preserved_approach["next_work_kind"] == "literature-review"


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
            json={
                "kind": "idea",
                "text": "Try a different representation",
                "summary": "Check whether representation choice explains the result.",
            },
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
        edited_map = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{new_test['id']}",
            json={
                "title": "Compare two matched encodings",
                "summary": "Keep data and evaluation fixed while changing encoding.",
            },
        ).json()
        edited_test = next(node for node in edited_map["nodes"] if node["id"] == new_test["id"])
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
    assert "representation choice" in new_direction["summary"]
    assert edited_test["title"] == "Compare two matched encodings"
    assert "evaluation fixed" in edited_test["summary"]
    assert changed_test["current_stage"] == "replicate"
    assert promoted_test["current_stage"] == "controlled-variation"
    assert any(node["id"] == new_direction["id"] for node in reimported["nodes"])
    preserved_test = next(node for node in reimported["nodes"] if node["id"] == new_test["id"])
    assert preserved_test["title"] == "Compare two matched encodings"


def test_plan_run_and_review_flow(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        approach = next(node for node in workspace["nodes"] if node["kind"] == "approach")

        workspace = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{approach['id']}",
            json={
                "next_work_kind": "compare-explanations",
                "agent_guidance": "Use only the safe fixture and compare the two explanations.",
                "ask_before": "Ask before using any other data.",
            },
        ).json()

        workspace = client.post(
            f"/api/workspaces/{workspace_id}/plans",
            json={
                "approach_id": approach["id"],
                "title": "Quick safe test",
                "stage": "minimal-probe",
            },
        ).json()
        plan = workspace["packages"][0]
        assert plan["work_kind"] == "compare-explanations"
        assert "safe fixture" in plan["idea_guidance"]
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
        handoff_text = handoff.read_text(encoding="utf-8")
        assert "## Rules for the agent" in handoff_text
        assert "When The selected idea says Next work: Quick test" in handoff_text
        assert "Applies to Entire project" in handoff_text
        assert "## Guidance for this idea" in handoff_text
        assert "safe fixture" in handoff_text
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
        reordered_rules = active_rules.copy()
        first_stage_index = next(index for index, rule in enumerate(reordered_rules) if rule["id"] == "stage-ideation")
        second_stage_index = next(index for index, rule in enumerate(reordered_rules) if rule["id"] == "stage-implementation")
        reordered_rules[first_stage_index], reordered_rules[second_stage_index] = reordered_rules[second_stage_index], reordered_rules[first_stage_index]
        reordered_rules.append(new_rule)
        drafted = client.post(
            f"/api/workspaces/{workspace_id}/rules/drafts",
            json={"rules": reordered_rules},
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
        policy_text = Path(activated["policy_file"]).read_text(encoding="utf-8")
        assert f"**Policy version:** {draft['version']}" in policy_text
        assert "Save one short summary" in policy_text
        loop_text = Path(activated["loop_file"]).read_text(encoding="utf-8")
        assert "### 1. Implementation" in loop_text
        assert "#### 1.1 Write and seal the run plan" in loop_text
        assert "### 2. Ideation" in loop_text
        assert "Save one short summary" in loop_text
        assert "SUPERVISOR.md" not in loop_text


def test_old_policy_is_upgraded_without_losing_its_rules(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    store_path = tmp_path / "loop-data.json"

    with TestClient(create_app(store_path)) as client:
        imported = client.post("/api/workspaces/import", json={"path": str(project)}).json()

    saved = json.loads(store_path.read_text(encoding="utf-8"))
    old_workspace = saved["workspaces"][0]
    old_workspace["policy_schema_version"] = 0
    old_active = next(
        version
        for version in old_workspace["rules_versions"]
        if version["id"] == old_workspace["active_rules_version_id"]
    )
    old_active["version"] = 2
    for rule in old_active["rules"]:
        rule.pop("category", None)
        rule.pop("when", None)
        rule.pop("scope", None)
        rule.pop("expires_when", None)
    old_active["rules"].append(
        {
            "id": "lab-specific-rule",
            "title": "Keep the lab note",
            "instruction": "Save the final interpretation in the lab note.",
            "enabled": True,
            "cannot_override": False,
        }
    )
    store_path.write_text(json.dumps(saved), encoding="utf-8")

    with TestClient(create_app(store_path)) as client:
        upgraded = client.get(f"/api/workspaces/{imported['id']}").json()

    active = next(
        version
        for version in upgraded["rules_versions"]
        if version["id"] == upgraded["active_rules_version_id"]
    )
    assert upgraded["policy_schema_version"] == 4
    assert active["version"] == 3
    assert any(rule["id"] == "lab-specific-rule" for rule in active["rules"])
    assert any(rule["category"] == "loop" for rule in active["rules"])
    assert any(rule["category"] == "checkpoint" for rule in active["rules"])
    assert any(rule["id"] == "plan-exact-inputs" for rule in active["rules"])


def test_starting_research_reuses_the_active_supervisor(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    monkeypatch.setenv("DELTA_LOOP_AGENT_COMMAND", "/bin/sh -c 'sleep 5'")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        focus = next(node for node in workspace["nodes"] if node["kind"] == "direction")
        payload = {
            "node_id": focus["id"],
            "agent_prompt": f"Start the real research loop with visual focus on {focus['title']}.",
            "kind": "research",
        }
        first = client.post(f"/api/workspaces/{workspace['id']}/terminals", json=payload).json()
        second = client.post(f"/api/workspaces/{workspace['id']}/terminals", json=payload).json()
        client.delete(f"/api/terminals/{first['id']}")

    assert first["kind"] == "research"
    assert first["node_id"] == focus["id"]
    assert second["id"] == first["id"]
