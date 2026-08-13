from __future__ import annotations

from pathlib import Path
import subprocess
import time

from fastapi.testclient import TestClient

from delta_loop.api import create_app
from delta_loop.compute import check_compute
from delta_loop.models import ComputeConfig
from test_importer import STATE


def fake_ssh(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-ssh"
    executable.write_text(
        "#!/bin/sh\n"
        "for last do :; done\n"
        "exec /bin/sh -c \"$last\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def make_git_repo(path: Path, remote: str = "git@github.com:user074/example-research.git") -> None:
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Delta Test"], check=True)
    subprocess.run(["git", "-C", str(path), "add", "STATE.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "initial research state"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)


def test_local_compute_check_reports_project_tools(tmp_path: Path) -> None:
    result = check_compute(ComputeConfig(), str(tmp_path))
    assert result.status == "ready"
    assert result.project_exists is True
    assert result.python


def test_local_compute_inspection_uses_the_local_project(tmp_path: Path) -> None:
    project = tmp_path / "local-project"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    (project / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    app = create_app(tmp_path / "local-data.json")

    with TestClient(app) as client:
        workspace = client.post(
            "/api/workspaces/import", json={"path": str(project)}
        ).json()
        inspected = client.post(
            f"/api/workspaces/{workspace['id']}/compute/inspect",
            json={"kind": "local"},
        )
        assert inspected.status_code == 200
        inspection = inspected.json()
        assert inspection["host"] == "this-computer"
        assert inspection["project_path"] == str(project)
        assert inspection["project_exists"] is True
        assert inspection["has_state"] is True
        assert "requirements.txt" in inspection["dependency_files"]


def test_ready_compute_is_reusable_as_a_machine_profile(tmp_path: Path) -> None:
    first_project = tmp_path / "first-project"
    first_project.mkdir()
    (first_project / "STATE.md").write_text(STATE, encoding="utf-8")
    second_project = tmp_path / "second-project"
    second_project.mkdir()
    (second_project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "profiles-data.json")

    with TestClient(app) as client:
        first = client.post("/api/workspaces/import", json={"path": str(first_project)}).json()
        client.post(
            f"/api/workspaces/{first['id']}/compute/inspect",
            json={"kind": "local"},
        )
        client.put(
            f"/api/workspaces/{first['id']}/compute",
            json={
                "kind": "local",
                "name": "This computer",
                "ssh_host": "",
                "project_path": "",
                "run_path": "~/.delta-loop/runs",
                "setup_command": "source project-one-env",
                "gpu_devices": "0",
                "max_parallel": 2,
            },
        )
        checked = client.post(f"/api/workspaces/{first['id']}/compute/check")
        assert checked.status_code == 200
        client.post("/api/workspaces/import", json={"path": str(second_project)})

        profiles = client.get("/api/compute-profiles")
        assert profiles.status_code == 200
        profile = profiles.json()[0]
        assert profile["id"] == "local"
        assert profile["gpu_devices"] == "0"
        assert profile["max_parallel"] == 2
        assert first["name"] in profile["source_projects"]
        assert "project_path" not in profile
        assert "setup_command" not in profile
        assert "run_path" not in profile
        assert "detected_python" not in profile


def test_git_check_reads_local_research_repository_and_policy(tmp_path: Path) -> None:
    project = tmp_path / "git-project"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    make_git_repo(project)
    (project / "notes.txt").write_text("new result\n", encoding="utf-8")
    app = create_app(tmp_path / "git-data.json")

    with TestClient(app) as client:
        workspace = client.post(
            "/api/workspaces/import", json={"path": str(project)}
        ).json()
        response = client.post(f"/api/workspaces/{workspace['id']}/git/check")
        assert response.status_code == 200
        snapshot = response.json()
        repository = snapshot["git_repository"]
        assert repository["state"] == "ready"
        assert repository["repository_root"] == str(project)
        assert repository["branch"] == "main"
        assert repository["github_url"] == "https://github.com/user074/example-research"
        assert any("notes.txt" in line for line in repository["changed_files"])
        active = next(
            version
            for version in snapshot["rules_versions"]
            if version["id"] == snapshot["active_rules_version_id"]
        )
        git_rule = next(rule for rule in active["rules"] if rule["id"] == "git-reviewed-work")
        assert git_rule["enabled"] is False


def test_git_check_uses_remote_project_not_local_control_folder(
    tmp_path: Path, monkeypatch
) -> None:
    remote_project = tmp_path / "actual-remote-repository"
    remote_project.mkdir()
    (remote_project / "STATE.md").write_text(STATE, encoding="utf-8")
    make_git_repo(remote_project)
    monkeypatch.setenv("DELTA_LOOP_SSH_COMMAND", str(fake_ssh(tmp_path)))
    app = create_app(tmp_path / "data" / "workspaces.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/remote").json()
        unset = client.post(f"/api/workspaces/{workspace['id']}/git/check")
        assert unset.status_code == 422
        assert "remote research project" in unset.json()["detail"]
        configured = client.put(
            f"/api/workspaces/{workspace['id']}/compute",
            json={
                "kind": "ssh",
                "name": "Research server",
                "ssh_host": "fake-server",
                "project_path": str(remote_project),
                "run_path": "~/.delta-loop/runs",
                "setup_command": "",
                "gpu_devices": "",
                "max_parallel": 1,
            },
        )
        assert configured.status_code == 200
        checked = client.post(
            f"/api/workspaces/{workspace['id']}/git/check"
        )
        assert checked.status_code == 200
        snapshot = checked.json()
        repository = snapshot["git_repository"]
        assert repository["state"] == "ready"
        assert repository["repository_root"] == str(remote_project)
        assert repository["location"] == f"fake-server:{remote_project}"
        assert repository["repository_root"] != workspace["root"]


def test_compute_setup_can_be_reset_without_removing_research(tmp_path: Path) -> None:
    project = tmp_path / "reset-project"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    app = create_app(tmp_path / "reset-data.json")

    with TestClient(app) as client:
        workspace = client.post(
            "/api/workspaces/import", json={"path": str(project)}
        ).json()
        workspace_id = workspace["id"]
        client.post(
            f"/api/workspaces/{workspace_id}/compute/inspect",
            json={"kind": "local"},
        )
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
        ).json()
        assert configured["compute"]["configured"] is True
        assert configured["compute_inspection"] is not None

        reset = client.post(
            f"/api/workspaces/{workspace_id}/compute/reset"
        )
        assert reset.status_code == 200
        snapshot = reset.json()
        assert snapshot["compute"]["configured"] is False
        assert snapshot["compute"]["status"] == "unchecked"
        assert snapshot["compute_inspection"] is None
        assert snapshot["goal"] == workspace["goal"]
        assert (project / "STATE.md").is_file()


def test_remote_project_setup_reads_only_bounded_useful_files(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "existing-remote-repo"
    project.mkdir()
    (project / "README.md").write_text("# Remote study\nThis studies long inputs.\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("Use the existing evaluation script.\n", encoding="utf-8")
    (project / "pyproject.toml").write_text("[project]\nname = 'remote-study'\n", encoding="utf-8")
    (project / ".env").write_text("SECRET_SHOULD_NOT_BE_READ=1\n", encoding="utf-8")
    (project / "large-result.bin").write_bytes(b"result" * 1000)
    nested = project / "src" / "model" / "training" / "pipelines"
    nested.mkdir(parents=True)
    (nested / "train.py").write_text(
        "from src.model.core import Model\n\ndef train():\n    return Model()\n",
        encoding="utf-8",
    )
    (project / "src" / "model" / "core.py").write_text(
        "class Model:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DELTA_LOOP_SSH_COMMAND", str(fake_ssh(tmp_path)))
    app = create_app(tmp_path / "data" / "workspaces.json")

    with TestClient(app) as client:
        workspace = client.post("/api/workspaces/remote").json()
        response = client.post(
            f"/api/workspaces/{workspace['id']}/setup/inspect-remote",
            json={
                "ssh_host": "fake-server",
                "project_path": str(project),
            },
        )
        assert response.status_code == 200
        inspection = response.json()
        assert inspection["project_exists"] is True
        assert "This studies long inputs" in inspection["documentation"]["README.md"]
        assert "existing evaluation script" in inspection["documentation"]["AGENTS.md"]
        assert inspection["total_files"] >= 5
        assert "src/model/training/pipelines/train.py" in inspection["top_level_files"]
        assert "src/model/training/pipelines/train.py" in inspection["entry_points"]
        assert "def train" in inspection["documentation"]["src/model/training/pipelines/train.py"]
        assert inspection["file_types"][".py"] == 2
        assert ".env" not in inspection["top_level_files"]
        assert ".env" not in inspection["documentation"]
        assert "large-result.bin" not in inspection["top_level_files"]
        assert "large-result.bin" not in inspection["documentation"]

        followed = client.post(
            f"/api/workspaces/{workspace['id']}/setup/read-remote",
            json={
                "ssh_host": "fake-server",
                "project_path": str(project),
                "paths": ["src/model/core.py"],
            },
        )
        assert followed.status_code == 200
        assert "class Model" in followed.json()["files"]["src/model/core.py"]

        secret = client.post(
            f"/api/workspaces/{workspace['id']}/setup/read-remote",
            json={
                "ssh_host": "fake-server",
                "project_path": str(project),
                "paths": [".env"],
            },
        )
        assert secret.status_code == 422
        refreshed = client.get(f"/api/workspaces/{workspace['id']}").json()
        assert refreshed["name"] == "existing-remote-repo"


def test_remote_compute_settings_check_and_run_over_ssh(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "remote-project"
    project.mkdir()
    (project / "STATE.md").write_text(STATE, encoding="utf-8")
    (project / "pyproject.toml").write_text("[project]\nname = 'remote-test'\n", encoding="utf-8")
    (project / "INFRA.md").write_text("# Existing infrastructure choices\n", encoding="utf-8")
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "activate").write_text(
        "export DELTA_TEST_ENV=ready\n", encoding="utf-8"
    )
    remote_home = tmp_path / "remote-home"
    remote_home.mkdir()
    run_root = remote_home / ".delta-loop" / "runs"
    monkeypatch.setenv("HOME", str(remote_home))
    monkeypatch.setenv("DELTA_LOOP_SSH_COMMAND", str(fake_ssh(tmp_path)))
    data_path = tmp_path / "loop-data.json"
    app = create_app(data_path)

    with TestClient(app) as client:
        workspace = client.post(
            "/api/workspaces/import", json={"path": str(project)}
        ).json()
        workspace_id = workspace["id"]
        approach = next(
            node for node in workspace["nodes"] if node["kind"] == "approach"
        )

        inspected = client.post(
            f"/api/workspaces/{workspace_id}/compute/inspect",
            json={
                "ssh_host": "fake-server",
                "project_path": str(project),
                "run_path": "~/.delta-loop/runs",
            },
        )
        assert inspected.status_code == 200
        inspection = inspected.json()
        assert inspection["project_exists"] is True
        assert inspection["has_state"] is True
        assert inspection["has_infra"] is True
        assert "pyproject.toml" in inspection["dependency_files"]
        assert any(".venv/bin/activate" in item for item in inspection["environment_candidates"])
        assert client.get(f"/api/workspaces/{workspace_id}").json()["compute_inspection"]["host"] == "fake-server"

        configured = client.put(
            f"/api/workspaces/{workspace_id}/compute",
            json={
                "kind": "ssh",
                "name": "Test GPU server",
                "ssh_host": "fake-server",
                "project_path": str(project),
                "run_path": "~/.delta-loop/runs",
                "setup_command": "source .venv/bin/activate",
                "gpu_devices": "0",
                "max_parallel": 1,
            },
        )
        assert configured.status_code == 200
        assert configured.json()["compute"]["status"] == "unchecked"
        assert configured.json()["compute_inspection"]["host"] == "fake-server"

        checked = client.post(
            f"/api/workspaces/{workspace_id}/compute/check"
        )
        assert checked.status_code == 200
        assert checked.json()["compute"]["status"] == "ready"
        assert checked.json()["compute"]["detected_python"]

        broken = client.put(
            f"/api/workspaces/{workspace_id}/compute",
            json={
                **{
                    key: checked.json()["compute"][key]
                    for key in (
                        "kind",
                        "name",
                        "ssh_host",
                        "project_path",
                        "run_path",
                        "gpu_devices",
                        "max_parallel",
                    )
                },
                "setup_command": "false",
            },
        )
        assert broken.status_code == 200
        broken_check = client.post(
            f"/api/workspaces/{workspace_id}/compute/check"
        ).json()
        assert broken_check["compute"]["status"] == "needs-setup"
        assert "environment setup" in broken_check["compute"]["status_message"]

        configured = client.put(
            f"/api/workspaces/{workspace_id}/compute",
            json={
                **{
                    key: broken.json()["compute"][key]
                    for key in (
                        "kind",
                        "name",
                        "ssh_host",
                        "project_path",
                        "run_path",
                        "gpu_devices",
                        "max_parallel",
                    )
                },
                "setup_command": "source .venv/bin/activate",
            },
        )
        assert configured.status_code == 200
        checked = client.post(
            f"/api/workspaces/{workspace_id}/compute/check"
        ).json()
        assert checked["compute"]["status"] == "ready"

        workspace = client.post(
            f"/api/workspaces/{workspace_id}/plans",
            json={
                "approach_id": approach["id"],
                "title": "Remote smoke test",
            },
        ).json()
        plan = workspace["packages"][-1]
        command = (
            "python3 -c \"import os, sys; "
            "print('remote-run-ok'); "
            "open(os.path.join(os.environ['DELTA_LOOP_OUTPUT_DIR'], 'proof.txt'), "
            "'w').write(os.environ.get('CUDA_VISIBLE_DEVICES', 'missing')); "
            "open(sys.argv[1], 'w').write('placeholder-ok')\" "
            "{output_dir}/placeholder.txt"
        )
        client.patch(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}",
            json={
                "goal": "Prove the SSH runner executes in the remote project.",
                "instructions": "Write one proof file and print one line.",
                "measure": "The line and proof file exist.",
                "command": command,
            },
        )
        client.post(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}/approve"
        )
        started = client.post(
            f"/api/workspaces/{workspace_id}/plans/{plan['id']}/run"
        )
        assert started.status_code == 200
        run_id = started.json()["attempts"][-1]["id"]

        current = started.json()
        for _ in range(80):
            current = client.get(f"/api/workspaces/{workspace_id}").json()
            attempt = next(item for item in current["attempts"] if item["id"] == run_id)
            if attempt["status"] in {"finished", "blocked", "failed"}:
                break
            time.sleep(0.05)

        attempt = next(item for item in current["attempts"] if item["id"] == run_id)
        assert attempt["status"] == "finished", attempt.get("error")
        assert attempt["executor"] == "ssh"
        assert attempt["compute_name"] == "Test GPU server"
        assert attempt["remote_host"] == "fake-server"
        assert "remote-run-ok" in attempt["output"]
        remote_record = run_root / run_id
        assert attempt["remote_record_directory"] == f"~/.delta-loop/runs/{run_id}"
        assert (remote_record / "PLAN.md").is_file()
        assert (remote_record / "run.log").is_file()
        assert (remote_record / "output" / "try-1" / "proof.txt").read_text() == "0"
        assert (remote_record / "output" / "try-1" / "placeholder.txt").read_text() == "placeholder-ok"
        assert Path(attempt["handoff_file"]).is_file()

        retried = client.post(
            f"/api/workspaces/{workspace_id}/runs/{run_id}/retry",
            json={
                "command": "python3 -c \"print('remote-retry-ok')\"",
                "reason": "Adjusted the implementation while preserving the same remote smoke test.",
            },
        )
        assert retried.status_code == 200
        retried_current = retried.json()
        for _ in range(80):
            retried_current = client.get(f"/api/workspaces/{workspace_id}").json()
            retried_attempt = next(
                item for item in retried_current["attempts"] if item["id"] == run_id
            )
            if retried_attempt["status"] in {"finished", "blocked", "failed"}:
                break
            time.sleep(0.05)
        retried_attempt = next(
            item for item in retried_current["attempts"] if item["id"] == run_id
        )
        assert retried_attempt["status"] == "finished", retried_attempt.get("error")
        assert "remote-retry-ok" in retried_attempt["output"]
        assert len(retried_current["attempts"]) == 1
        assert len(retried_attempt["execution_history"]) == 1
        assert "remote-run-ok" in retried_attempt["execution_history"][0]["output_tail"]
        assert retried_attempt["remote_output_directory"].endswith("/output/try-2")
        assert retried_attempt["execution_history"][0]["remote_output_directory"].endswith("/output/try-1")

    # A fresh API process can recover a remote job from the files on the server.
    stored = app.state.store.get(workspace_id)
    assert stored is not None
    stored_attempt = next(item for item in stored.attempts if item.id == run_id)
    stored_plan = next(item for item in stored.packages if item.id == stored_attempt.package_id)
    stored_attempt.status = "running"
    stored_attempt.output = []
    stored_plan.status = "running"
    app.state.store.save(stored)

    restarted = create_app(data_path)
    with TestClient(restarted) as client:
        recovered = client.get(f"/api/workspaces/{workspace_id}").json()
    recovered_attempt = next(item for item in recovered["attempts"] if item["id"] == run_id)
    assert recovered_attempt["status"] == "finished"
    assert "remote-retry-ok" in recovered_attempt["output"]


def test_remote_compute_does_not_store_credentials(tmp_path: Path) -> None:
    fields = ComputeConfig.model_fields
    assert "password" not in fields
    assert "private_key" not in fields
    assert "token" not in fields
    assert "ssh_host" in fields
