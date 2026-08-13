import json
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
        assert imported["policy_schema_version"] == 6
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
        continuous = next(rule for rule in active_rules if rule["id"] == "continuous-research")
        assert continuous["enabled"] is True
        assert "without asking" in continuous["instruction"]
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
        assert "Do not stop for ordinary scientific choices" in loop_text
        assert "No Git rule is enabled. Do not commit or push; keep researching" in loop_text

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

        evolved = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{approach['id']}",
            json={
                "title": "Compare the two strongest explanations",
                "status": "dormant",
                "reason": "A broader result made this branch less urgent.",
            },
        ).json()
        history = [
            change for change in evolved["node_history"]
            if change["node_id"] == approach["id"]
        ]
        assert len(history) == 2
        assert "medium" in history[0]["changes"]["promise"]
        assert "dormant" in history[-1]["changes"]["status"]
        assert history[-1]["reason"] == "A broader result made this branch less urgent."

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


def test_project_without_state_can_be_set_up_with_codex_flow(tmp_path: Path) -> None:
    project = tmp_path / "existing-project"
    project.mkdir()
    (project / "README.md").write_text("# Existing project\n", encoding="utf-8")
    (project / "INFRA.md").write_text("# Existing infrastructure notes\n", encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        response = client.post("/api/workspaces/import", json={"path": str(project)})
        assert response.status_code == 200
        workspace = response.json()
        workspace_id = workspace["id"]
        assert workspace["setup_status"] == "needs-setup"
        assert not (project / "STATE.md").exists()
        assert (project / ".delta-loop" / "LOOP.md").is_file()

        too_early = client.post(
            f"/api/workspaces/{workspace_id}/setup/complete",
            json={"summary": "Not ready yet"},
        )
        assert too_early.status_code == 422
        assert "main research question" in too_early.json()["detail"]

        client.patch(
            f"/api/workspaces/{workspace_id}",
            json={
                "goal": "Determine why the existing model fails on long inputs",
                "reason": "Agreed during initial setup",
            },
        )
        with_idea = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "idea",
                "text": "The positional representation is the bottleneck",
                "summary": "Long inputs may exceed the learned representation range.",
            },
        ).json()
        idea = next(
            node for node in with_idea["nodes"]
            if node["title"] == "The positional representation is the bottleneck"
        )
        with_test = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "way-to-test",
                "text": "Compare short and long matched inputs",
                "summary": "Hold content constant while changing only length.",
                "parent_id": idea["id"],
            },
        ).json()
        test_node = next(
            node for node in with_test["nodes"]
            if node["title"] == "Compare short and long matched inputs"
        )
        blocked_plan = client.post(
            f"/api/workspaces/{workspace_id}/plans",
            json={
                "approach_id": test_node["id"],
                "title": "Must wait for setup",
            },
        )
        assert blocked_plan.status_code == 409
        assert "Finish setting up" in blocked_plan.json()["detail"]
        inspected = client.post(
            f"/api/workspaces/{workspace_id}/compute/inspect",
            json={"kind": "local"},
        )
        assert inspected.status_code == 200
        configured = client.put(
            f"/api/workspaces/{workspace_id}/compute",
            json={
                "kind": "local",
                "name": "This computer",
                "ssh_host": "",
                "project_path": "",
                "run_path": "~/.delta-loop/runs",
                "setup_command": "",
                "gpu_devices": "",
                "max_parallel": 1,
            },
        )
        assert configured.status_code == 200
        checked = client.post(f"/api/workspaces/{workspace_id}/compute/check")
        assert checked.status_code == 200
        assert checked.json()["compute"]["last_checked_at"]
        git_checked = client.post(f"/api/workspaces/{workspace_id}/git/check")
        assert git_checked.status_code == 200
        assert git_checked.json()["git_repository"]["state"] == "not-repository"
        completed = client.post(
            f"/api/workspaces/{workspace_id}/setup/complete",
            json={
                "summary": "Study length-related model failures using the existing evaluation code.",
                "reference_repos": ["https://github.com/example/reference"],
                "constraints": ["Do not replace the existing evaluation dataset"],
                "prior_work": ["The baseline works on short inputs but degrades with length"],
                "reusable_inputs": ["The existing matched-input evaluation script"],
                "success_condition": "Identify a reproducible cause of the long-input failure.",
                "stop_condition": "Ask before replacing the model or evaluation dataset.",
                "budget": "Two small GPU runs before review.",
                "permission_mode": "scoped",
                "environment_verified": True,
                "git_reviewed": True,
            },
        )
        assert completed.status_code == 200
        snapshot = completed.json()
        assert snapshot["setup_status"] == "ready"
        assert snapshot["status"] == "active"
        assert snapshot["reference_repos"] == ["https://github.com/example/reference"]
        assert snapshot["setup_constraints"] == ["Do not replace the existing evaluation dataset"]
        assert snapshot["initialization"]["status"] == "complete"
        assert snapshot["initialization"]["environment_verified"] is True
        assert snapshot["initialization"]["git_reviewed"] is True
        state = (project / "STATE.md").read_text(encoding="utf-8")
        assert "Determine why the existing model fails on long inputs" in state
        assert "The positional representation is the bottleneck" in state
        assert "Compare short and long matched inputs" in state
        assert "https://github.com/example/reference" in state
        assert "Literature review for belief #1" in state
        assert "| pending |" in state
        assert "Two small GPU runs before review" in state
        initialization = (project / ".delta-loop" / "INITIALIZATION.md").read_text(
            encoding="utf-8"
        )
        assert "What was already tried" in initialization
        assert "The existing matched-input evaluation script" in initialization
        assert "Run commands inside the approved project and limits" in initialization
        assert (project / "SYNTHESIS.md").is_file()
        assert (project / "LITERATURE" / "INDEX.md").is_file()
        assert (project / "REPORTS").is_dir()
        assert (project / "RUNS").is_dir()
        assert (project / "INFRA.md").read_text(encoding="utf-8") == "# Existing infrastructure notes\n"
        policy = (project / ".delta-loop" / "POLICY.md").read_text(encoding="utf-8")
        assert "## Researcher-approved starting setup" in policy
        assert "Identify a reproducible cause" in policy

        reimported = client.post(
            "/api/workspaces/import", json={"path": str(project)}
        ).json()
        assert reimported["setup_status"] == "ready"
        assert reimported["setup_summary"] == snapshot["setup_summary"]
        assert [node["id"] for node in reimported["nodes"]] == [
            node["id"] for node in snapshot["nodes"]
        ]


def test_remote_project_starts_with_local_notes_and_no_generated_results(tmp_path: Path) -> None:
    data_path = tmp_path / "data" / "workspaces.json"
    app = create_app(data_path)

    with TestClient(app) as client:
        response = client.post("/api/workspaces/remote")
        assert response.status_code == 200
        workspace = response.json()

        root = Path(workspace["root"])
        assert workspace["project_source"] == "remote"
        assert workspace["setup_status"] == "needs-setup"
        assert workspace["goal"] == "Research question not set up yet"
        assert workspace["claims"] == []
        assert workspace["runs"] == []
        assert workspace["packages"] == []
        assert root.parent == data_path.parent / "projects"
        assert not (root / "STATE.md").exists()
        assert (root / ".delta-loop" / "LOOP.md").is_file()
        assert (root / ".delta-loop" / "POLICY.md").is_file()

        client.patch(
            f"/api/workspaces/{workspace['id']}",
            json={
                "goal": "Why does the remote model fail on longer inputs?",
                "reason": "Agreed during setup",
            },
        )
        client.post(
            f"/api/workspaces/{workspace['id']}/notes",
            json={"kind": "idea", "text": "The input representation is the limit"},
        )
        unfinished = client.post(
            f"/api/workspaces/{workspace['id']}/setup/complete",
            json={
                "summary": "Study the existing model on the remote server.",
                "success_condition": "Find a reproducible explanation.",
                "stop_condition": "Ask before changing the model.",
                "budget": "One small run.",
                "environment_verified": True,
                "git_reviewed": True,
            },
        )
        assert unfinished.status_code == 422
        assert "Choose and check where research work runs" in unfinished.json()["detail"]
        assert not (root / "STATE.md").exists()


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


def test_research_map_supports_multiple_questions_and_cross_links(tmp_path: Path) -> None:
    project = tmp_path / "research"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        primary_question = next(node for node in workspace["nodes"] if node["kind"] == "question")
        second = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "question",
                "text": "How robust is the mechanism across domains?",
                "summary": "A second high-level question.",
            },
        ).json()
        second_question = next(
            node for node in second["nodes"]
            if node["title"] == "How robust is the mechanism across domains?"
        )
        with_shared_idea = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "idea",
                "text": "The representation is domain-independent",
                "summary": "This idea may answer both questions.",
                "parent_id": second_question["id"],
            },
        ).json()
        shared_idea = next(
            node for node in with_shared_idea["nodes"]
            if node["title"] == "The representation is domain-independent"
        )
        connected = client.post(
            f"/api/workspaces/{workspace_id}/research-links",
            json={
                "source_id": primary_question["id"],
                "target_id": shared_idea["id"],
                "relationship": "explores",
                "note": "The same mechanism could explain the original question.",
            },
        )
        assert connected.status_code == 200
        snapshot = connected.json()
        questions = [node for node in snapshot["nodes"] if node["kind"] == "question"]
        incoming = [
            link for link in snapshot["research_links"]
            if link["target_id"] == shared_idea["id"] and link["relationship"] == "explores"
        ]
        assert len(questions) == 2
        assert {link["source_id"] for link in incoming} == {
            primary_question["id"],
            second_question["id"],
        }

        invalid = client.post(
            f"/api/workspaces/{workspace_id}/research-links",
            json={
                "source_id": shared_idea["id"],
                "target_id": primary_question["id"],
                "relationship": "explores",
            },
        )
        assert invalid.status_code == 422

        promoted_question = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{second_question['id']}",
            json={"status": "primary", "reason": "This is now the main framing."},
        ).json()
        assert promoted_question["goal"] == second_question["title"]
        assert len([
            node for node in promoted_question["nodes"]
            if node["kind"] == "question" and node["status"] == "primary"
        ]) == 1

        removed = client.delete(
            f"/api/workspaces/{workspace_id}/research-links/{incoming[0]['id']}"
        ).json()
        assert len(removed["research_links"]) == len(snapshot["research_links"]) - 1


def test_research_map_supports_reviews_findings_and_continuing_paths(tmp_path: Path) -> None:
    project = tmp_path / "research-trace"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "loop-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        workspace_id = workspace["id"]
        question = next(node for node in workspace["nodes"] if node["kind"] == "question")

        with_review = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "work",
                "work_kind": "literature-review",
                "text": "Review evidence for representation limits",
                "summary": "Find what is established before choosing a mechanism.",
                "parent_id": question["id"],
            },
        ).json()
        review = next(node for node in with_review["nodes"] if node["title"].startswith("Review evidence"))
        assert review["kind"] == "approach"
        assert review["next_work_kind"] == "literature-review"

        with_idea = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "idea",
                "text": "The representation discards task structure",
                "parent_id": review["id"],
                "relationship": "informs",
            },
        ).json()
        idea = next(node for node in with_idea["nodes"] if node["title"].startswith("The representation discards"))
        assert idea["parent_id"] == review["id"]

        with_test = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "work",
                "work_kind": "quick-test",
                "text": "Compare matched representations",
                "parent_id": idea["id"],
                "relationship": "tests",
            },
        ).json()
        test = next(node for node in with_test["nodes"] if node["title"] == "Compare matched representations")

        with_finding = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "finding",
                "text": "Only structured inputs improve transfer",
                "summary": "The difference survives the matched control but needs replication.",
                "parent_id": test["id"],
            },
        ).json()
        finding = next(node for node in with_finding["nodes"] if node["kind"] == "finding")
        assert any(
            link["source_id"] == test["id"]
            and link["target_id"] == finding["id"]
            and link["relationship"] == "produces"
            for link in with_finding["research_links"]
        )

        revised = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "idea",
                "text": "Structure matters only under transfer",
                "parent_id": finding["id"],
                "relationship": "revises",
            },
        ).json()
        revised_idea = next(node for node in revised["nodes"] if node["title"].startswith("Structure matters"))
        assert revised_idea["parent_id"] == finding["id"]
        revised_links = [
            link for link in revised["research_links"]
            if link["source_id"] == finding["id"] and link["target_id"] == revised_idea["id"]
        ]
        assert len(revised_links) == 1
        assert revised_links[0]["relationship"] == "revises"

        alternative = client.post(
            f"/api/workspaces/{workspace_id}/notes",
            json={
                "kind": "work",
                "text": "Try a different matched control",
                "parent_id": test["id"],
                "relationship": "leads-to",
            },
        ).json()
        second_test = next(node for node in alternative["nodes"] if node["title"].startswith("Try a different"))
        assert second_test["parent_id"] == test["id"]

        circular = client.patch(
            f"/api/workspaces/{workspace_id}/nodes/{review['id']}",
            json={"parent_id": revised_idea["id"], "reason": "This should be rejected."},
        )
        assert circular.status_code == 422
        assert "circular" in circular.json()["detail"]


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

        configured = client.put(
            f"/api/workspaces/{workspace_id}/compute",
            json={
                "kind": "local",
                "name": "This computer",
                "ssh_host": "",
                "project_path": "",
                "run_path": "~/.delta-loop/runs",
                "setup_command": "",
                "gpu_devices": "",
                "max_parallel": 1,
            },
        )
        assert configured.status_code == 200

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
    old_active["rules"] = [
        rule for rule in old_active["rules"] if rule["id"] != "continuous-research"
    ]
    legacy_rules = {rule["id"]: rule for rule in old_active["rules"]}
    legacy_rules["loop-run-worker"]["instruction"] = (
        "Give a worker the sealed plan, exact resources, environment, and policy. The worker may run, "
        "debug, plot, and report within that scope, and must stop for blockers or changes that require approval."
    )
    legacy_rules["loop-finish-cycle"]["instruction"] = (
        "Follow the active Git and publishing rules, then check the recorded stop conditions. If no "
        "condition applies, continue to the next cycle in the same supervisor session."
    )
    legacy_rules["ask-before-full-study"].update({
        "title": "Ask before a full study",
        "instruction": "Stop and ask the researcher before moving from a small or confirming test into a full study.",
        "when": "Before starting a full study",
    })
    legacy_rules["keep-main-question"].update({
        "title": "Do not change the main question",
        "instruction": "Do not change the main research question, the main comparison, or the measurement without stopping and asking the researcher.",
        "when": "Before changing the question, main comparison, or measurement",
    })
    legacy_rules["protect-project-files"]["instruction"] = (
        "Only the supervisor may update STATE.md after checking a result. Workers must not modify it, "
        "and the agent must not accept a scientific conclusion on the researcher's behalf."
    )
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
    assert upgraded["policy_schema_version"] == 6
    assert active["version"] == 3
    assert any(rule["id"] == "lab-specific-rule" for rule in active["rules"])
    assert any(rule["category"] == "loop" for rule in active["rules"])
    assert any(rule["category"] == "checkpoint" for rule in active["rules"])
    assert any(rule["id"] == "plan-exact-inputs" for rule in active["rules"])
    assert any(rule["id"] == "continuous-research" for rule in active["rules"])
    full_study = next(rule for rule in active["rules"] if rule["id"] == "ask-before-full-study")
    assert full_study["title"] == "Promote useful signals to a full study"
    assert "continue without waiting" in full_study["instruction"]


def test_project_can_keep_multiple_research_terminals_running(tmp_path: Path, monkeypatch) -> None:
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
            "title": f"Research · {focus['title']}",
        }
        first = client.post(f"/api/workspaces/{workspace['id']}/terminals", json=payload).json()
        second = client.post(f"/api/workspaces/{workspace['id']}/terminals", json=payload).json()
        running = client.get(f"/api/workspaces/{workspace['id']}/terminals").json()
        stopped = client.delete(f"/api/workspaces/{workspace['id']}/terminals").json()

    assert first["kind"] == "research"
    assert first["node_id"] == focus["id"]
    assert first["title"] == f"Research · {focus['title']}"
    assert second["id"] != first["id"]
    assert {session["id"] for session in running if session["status"] == "active"} == {first["id"], second["id"]}
    assert stopped == {"status": "closed", "count": 2}


def test_terminal_websocket_prepares_the_browser_size_before_accepting_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "terminal-size"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "terminal-size-data.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/import", json={"path": str(project)}).json()
        session = client.post(
            f"/api/workspaces/{workspace['id']}/terminals",
            json={"kind": "shell", "title": "Size test"},
        ).json()
        prepared: list[tuple[str, int, int]] = []

        def connection_output(session_id: str, columns: int, rows: int) -> tuple[bytes, int]:
            prepared.append((session_id, columns, rows))
            return b"\x1bcBROWSER-SIZED-SCREEN", 1_000_000

        monkeypatch.setattr(app.state.terminals, "connection_output", connection_output)
        with client.websocket_connect(
            f"/api/terminals/{session['id']}/ws?columns=137&rows=17"
        ) as websocket:
            assert websocket.receive_bytes() == b"\x1bcBROWSER-SIZED-SCREEN"
            assert json.loads(websocket.receive_text()) == {"type": "ready"}

        client.delete(f"/api/terminals/{session['id']}")

    assert prepared == [(session["id"], 137, 17)]


def test_installed_app_serves_web_ui_and_api_from_one_port(tmp_path: Path) -> None:
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        "<!doctype html><title>Installed Delta Loop</title>",
        encoding="utf-8",
    )
    app = create_app(
        tmp_path / "workspaces.json",
        serve_web=True,
        api_url="http://127.0.0.1:4321",
        web_dist=web_dist,
    )

    with TestClient(app) as client:
        page = client.get("/")
        health = client.get("/api/health")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/not-a-terminal"):
                pass

    assert page.status_code == 200
    assert "Installed Delta Loop" in page.text
    assert health.json() == {"status": "ok"}
