from pathlib import Path

from delta_loop.harness import OFFICIAL_REPOSITORY, inspect_harness


def test_project_harness_is_discovered_without_git(tmp_path: Path) -> None:
    project = tmp_path / "research"
    harness = project / "delta-research"
    for name in ("SUPERVISOR.md", "INIT.md", "PLAN.template.md", "STATE.template.md"):
        path = harness / "templates" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")

    info = inspect_harness(project)

    assert info.path == str(harness)
    assert info.source_url == OFFICIAL_REPOSITORY
    assert info.status == "unversioned"
