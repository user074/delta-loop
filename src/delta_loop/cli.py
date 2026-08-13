from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from uuid import uuid4

from .importer import ImportFailure, import_workspace


DEFAULT_API_URL = "http://127.0.0.1:4317"


def _default_api_url() -> str:
    return os.environ.get("DELTA_LOOP_API_URL", DEFAULT_API_URL)


def _default_ws_url() -> str:
    return _default_api_url().replace("http://", "ws://", 1).replace("https://", "wss://", 1)


def main(argv: list[str] | None = None, *, program: str = "delta") -> None:
    parser = argparse.ArgumentParser(prog=program, description="Delta Loop local research cockpit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ui_parser = subparsers.add_parser("ui", help="Start Delta Loop and open it in your browser")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", default=4317, type=int)
    ui_parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    ui_parser.add_argument(
        "--data",
        help="Advanced: use a different Delta Loop data file",
    )

    serve_parser = subparsers.add_parser("serve", help="Run the local Delta Loop API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=4318, type=int)

    connect_parser = subparsers.add_parser(
        "connect",
        help="Open a remote Delta Loop through a reconnecting SSH tunnel",
    )
    connect_parser.add_argument("host", help="SSH host or alias for the server running Delta Loop")
    connect_parser.add_argument("--remote-port", default=4317, type=int)
    connect_parser.add_argument("--local-port", default=4318, type=int)
    connect_parser.add_argument("--no-open", action="store_true", help="Do not open a browser")

    import_parser = subparsers.add_parser("import", help="Preview a delta-research workspace import")
    import_parser.add_argument("path")

    terminal_parser = subparsers.add_parser("terminal", help="Use a Delta Loop terminal")
    terminal_subparsers = terminal_parser.add_subparsers(dest="terminal_command", required=True)
    attach_parser = terminal_subparsers.add_parser("attach", help="Attach to a live terminal")
    attach_parser.add_argument("session_id")
    attach_parser.add_argument("--url", default=_default_ws_url())

    context_parser = subparsers.add_parser("context", help="Show the research context for this terminal")
    context_parser.add_argument("--json", action="store_true", dest="as_json")
    context_parser.add_argument("--workspace")
    context_parser.add_argument("--node")
    context_parser.add_argument("--url", default=_default_api_url())

    project_parser = subparsers.add_parser(
        "project", help="Finish the initial setup of an existing research project"
    )
    project_subparsers = project_parser.add_subparsers(
        dest="project_command", required=True
    )
    project_finish = project_subparsers.add_parser(
        "finish-setup",
        help="Create the initial STATE.md after the researcher approves the setup",
    )
    project_finish.add_argument("--summary", required=True)
    project_finish.add_argument("--reference", action="append", default=[])
    project_finish.add_argument("--constraint", action="append", default=[])
    project_finish.add_argument("--prior-work", action="append", default=[])
    project_finish.add_argument(
        "--input",
        action="append",
        default=[],
        dest="reusable_inputs",
        help="Reusable dataset, checkpoint, model, library, or evaluation tool",
    )
    project_finish.add_argument("--success", required=True, dest="success_condition")
    project_finish.add_argument("--stop", required=True, dest="stop_condition")
    project_finish.add_argument("--budget", required=True)
    project_finish.add_argument(
        "--permissions",
        choices=["manual", "scoped", "full"],
        default="scoped",
        dest="permission_mode",
    )
    project_finish.add_argument("--environment-verified", action="store_true")
    project_finish.add_argument("--git-reviewed", action="store_true")
    project_finish.add_argument("--workspace")
    project_finish.add_argument(
        "--url",
        default=_default_api_url(),
    )
    project_inspect = project_subparsers.add_parser(
        "inspect-remote",
        help="Read a bounded set of project files from an existing SSH server",
    )
    project_inspect.add_argument("--host", required=True, dest="ssh_host")
    project_inspect.add_argument("--project", required=True, dest="project_path")
    project_inspect.add_argument("--json", action="store_true", dest="as_json")
    project_inspect.add_argument("--workspace")
    project_inspect.add_argument(
        "--url",
        default=_default_api_url(),
    )
    project_read = project_subparsers.add_parser(
        "read-remote",
        help="Read selected text files inside the remote project after mapping it",
    )
    project_read.add_argument("paths", nargs="+")
    project_read.add_argument("--host", required=True, dest="ssh_host")
    project_read.add_argument("--project", required=True, dest="project_path")
    project_read.add_argument("--json", action="store_true", dest="as_json")
    project_read.add_argument("--workspace")
    project_read.add_argument("--url", default=_default_api_url())

    compute_parser = subparsers.add_parser(
        "compute", help="Read, change, or check where research work runs"
    )
    compute_subparsers = compute_parser.add_subparsers(
        dest="compute_command", required=True
    )
    compute_show = compute_subparsers.add_parser(
        "show", help="Show where work runs and the current connection status"
    )
    compute_show.add_argument("--json", action="store_true", dest="as_json")
    compute_set = compute_subparsers.add_parser(
        "set", help="Use this computer or an SSH server"
    )
    compute_set.add_argument("--kind", choices=["local", "ssh"])
    compute_set.add_argument("--name")
    compute_set.add_argument("--host", dest="ssh_host")
    compute_set.add_argument("--project", dest="project_path")
    compute_set.add_argument("--runs", dest="run_path")
    compute_set.add_argument("--setup", dest="setup_command")
    compute_set.add_argument("--gpus", dest="gpu_devices")
    compute_set.add_argument("--max-parallel", type=int, dest="max_parallel")
    compute_check = compute_subparsers.add_parser(
        "check", help="Test the saved location without starting research work"
    )
    compute_reset = compute_subparsers.add_parser(
        "reset", help="Clear the saved location and its inspection"
    )
    compute_inspect = compute_subparsers.add_parser(
        "inspect",
        help="Read basic remote environment facts before discussing and saving settings",
    )
    compute_inspect.add_argument(
        "--local",
        action="store_true",
        help="Inspect this computer and the local research project",
    )
    compute_inspect.add_argument("--host", dest="ssh_host")
    compute_inspect.add_argument("--project", dest="project_path")
    compute_inspect.add_argument("--runs", dest="run_path")
    compute_inspect.add_argument("--json", action="store_true", dest="as_json")
    for item in (compute_show, compute_set, compute_check, compute_reset, compute_inspect):
        item.add_argument("--workspace")
        item.add_argument(
            "--url",
            default=_default_api_url(),
        )

    git_parser = subparsers.add_parser(
        "git", help="Check the research repository and its agent policy"
    )
    git_subparsers = git_parser.add_subparsers(dest="git_command", required=True)
    git_show = git_subparsers.add_parser(
        "show", help="Show the last repository check and active Git rules"
    )
    git_show.add_argument("--json", action="store_true", dest="as_json")
    git_check = git_subparsers.add_parser(
        "check", help="Read the actual local or remote repository without changing it"
    )
    git_check.add_argument("--json", action="store_true", dest="as_json")
    for item in (git_show, git_check):
        item.add_argument("--workspace")
        item.add_argument("--url", default=_default_api_url())

    work_parser = subparsers.add_parser(
        "work", help="Start and follow a bounded research run through Delta Loop"
    )
    work_subparsers = work_parser.add_subparsers(dest="work_command", required=True)
    work_show = work_subparsers.add_parser(
        "show", help="Show recent work and where it ran"
    )
    work_show.add_argument("--json", action="store_true", dest="as_json")
    work_start = work_subparsers.add_parser(
        "start", help="Save one test brief and start it at the saved compute location"
    )
    work_start.add_argument("--approach", required=True, dest="approach_id")
    work_start.add_argument("--title", required=True)
    work_start.add_argument("--goal", required=True)
    work_start.add_argument("--steps", required=True, dest="instructions")
    work_start.add_argument("--measure", required=True)
    work_start.add_argument("--command", required=True)
    work_start.add_argument("--data", default="", dest="inputs")
    work_start.add_argument("--comparison", default="")
    work_start.add_argument("--expected", default="")
    work_start.add_argument("--limits", default="")
    work_start.add_argument("--do-not-change", default="", dest="do_not_change")
    work_start.add_argument("--budget", default="Small")
    work_review = work_subparsers.add_parser(
        "review", help="Record what a completed test says about the idea"
    )
    work_review.add_argument("run_id")
    work_review.add_argument(
        "--outcome",
        required=True,
        choices=["supports", "challenges", "inconclusive", "invalid", "not-applicable"],
        help="Scientific evidence outcome; implementation changes are not an outcome",
    )
    work_review.add_argument(
        "--validity",
        default="valid",
        choices=["valid", "partly-valid", "invalid", "unsure"],
        help="Whether the final execution can answer the intended question",
    )
    work_review.add_argument("--meaning", required=True)
    work_review.add_argument(
        "--next",
        required=True,
        dest="next_step",
        choices=["go-deeper", "run-again", "change-test", "try-another", "park"],
    )
    work_review.add_argument("--adaptations", default="")
    work_review.add_argument("--notes", default="")
    work_review.add_argument("--keep-code", action="store_true")
    work_cancel = work_subparsers.add_parser("cancel", help="Stop a running job")
    work_cancel.add_argument("run_id")
    for item in (work_show, work_start, work_review, work_cancel):
        item.add_argument("--workspace")
        item.add_argument(
            "--url",
            default=_default_api_url(),
        )

    policy_parser = subparsers.add_parser("policy", help="Read or update policy for the selected idea")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command", required=True)
    policy_show = policy_subparsers.add_parser("show", help="Show policy for the selected idea")
    policy_set = policy_subparsers.add_parser("set", help="Update policy for the selected idea")
    for item in (policy_show, policy_set):
        item.add_argument("--workspace")
        item.add_argument("--node")
        item.add_argument("--url", default=_default_api_url())
    policy_set.add_argument(
        "--kind",
        choices=[
            "quick-test",
            "replicate",
            "literature-review",
            "compare-explanations",
            "ablation",
            "full-study",
            "research-engineering",
        ],
    )
    policy_set.add_argument("--guidance")
    policy_set.add_argument("--ask-before")

    question_parser = subparsers.add_parser("question", help="Update the main research question")
    question_subparsers = question_parser.add_subparsers(dest="question_command", required=True)
    question_set = question_subparsers.add_parser("set", help="Save a discussed change to the question")
    question_set.add_argument("question")
    question_set.add_argument("--reason", default="")
    question_set.add_argument("--workspace")
    question_set.add_argument("--url", default=_default_api_url())

    rules_parser = subparsers.add_parser("rules", help="Read or replace the general policy")
    rules_subparsers = rules_parser.add_subparsers(dest="rules_command", required=True)
    rules_show = rules_subparsers.add_parser("show", help="Show the general policy used now")
    rules_show.add_argument("--json", action="store_true", dest="as_json")
    rules_sync = rules_subparsers.add_parser(
        "sync",
        help="Rewrite the active policy file read by the research loop",
    )
    rules_apply = rules_subparsers.add_parser(
        "apply",
        help="Check and use a general policy from a JSON file",
    )
    rules_apply.add_argument("file", help="A JSON file containing the full rules list, or - for stdin")
    rule_categories = ["loop", "checkpoint", "project", "git", "hardware", "data", "resources", "temporary"]
    rules_add = rules_subparsers.add_parser("add", help="Add and activate one policy rule")
    rules_add.add_argument("title")
    rules_add.add_argument("--instruction", required=True)
    rules_add.add_argument("--category", choices=rule_categories, default="project")
    rules_add.add_argument("--when", default="Always")
    rules_add.add_argument("--scope", default="Entire project")
    rules_add.add_argument("--expires", default="", dest="expires_when")
    rules_add.add_argument("--off", action="store_false", dest="enabled", default=True)
    rules_update = rules_subparsers.add_parser("update", help="Change and activate one policy rule")
    rules_update.add_argument("rule_id")
    rules_update.add_argument("--title")
    rules_update.add_argument("--instruction")
    rules_update.add_argument("--category", choices=rule_categories)
    rules_update.add_argument("--when")
    rules_update.add_argument("--scope")
    rules_update.add_argument("--expires", dest="expires_when")
    rules_update_state = rules_update.add_mutually_exclusive_group()
    rules_update_state.add_argument("--on", action="store_true", dest="enabled")
    rules_update_state.add_argument("--off", action="store_false", dest="enabled")
    rules_update.set_defaults(enabled=None)
    for item in (rules_show, rules_sync, rules_apply, rules_add, rules_update):
        item.add_argument("--workspace")
        item.add_argument("--url", default=_default_api_url())

    harness_parser = subparsers.add_parser("harness", help="Inspect or update the delta-research harness")
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command", required=True)
    harness_show = harness_subparsers.add_parser("show", help="Show the connected harness source and revision")
    harness_update = harness_subparsers.add_parser("update", help="Fast-forward a clean harness checkout")
    for item in (harness_show, harness_update):
        item.add_argument("--workspace")
        item.add_argument("--url", default=_default_api_url())

    map_parser = subparsers.add_parser("map", help="Read or develop the research idea map")
    map_subparsers = map_parser.add_subparsers(dest="map_command", required=True)
    map_show = map_subparsers.add_parser("show", help="Show questions, ideas, work, findings, and their relationships")
    map_show.add_argument("--json", action="store_true", dest="as_json")
    map_add_question = map_subparsers.add_parser("add-question", help="Add another high-level research question")
    map_add_question.add_argument("title")
    map_add_question.add_argument("--summary", default="")
    map_add_idea = map_subparsers.add_parser("add-idea", help="Add an idea after any relevant map item")
    map_add_idea.add_argument("title")
    map_add_idea.add_argument("--summary", default="")
    map_add_idea.add_argument("--under", dest="parent_id")
    map_add_idea.add_argument("--relationship", choices=["explores", "revises", "leads-to", "informs"])
    map_add_test = map_subparsers.add_parser("add-test", help="Add a way to test an idea")
    map_add_test.add_argument("title")
    map_add_test.add_argument("--under", required=True, dest="parent_id")
    map_add_test.add_argument("--summary", default="")
    map_add_work = map_subparsers.add_parser("add-work", help="Add an experiment, review, analysis, or other research work")
    map_add_work.add_argument("title")
    map_add_work.add_argument("--under", required=True, dest="parent_id")
    map_add_work.add_argument("--summary", default="")
    map_add_work.add_argument(
        "--kind",
        default="quick-test",
        choices=["quick-test", "replicate", "literature-review", "compare-explanations", "ablation", "full-study", "research-engineering"],
        dest="work_kind",
    )
    map_add_work.add_argument("--relationship", choices=["tests", "leads-to", "informs", "depends-on"])
    map_add_finding = map_subparsers.add_parser("add-finding", help="Record an important result from earlier work")
    map_add_finding.add_argument("title")
    map_add_finding.add_argument("--under", required=True, dest="parent_id")
    map_add_finding.add_argument("--summary", default="")
    map_update = map_subparsers.add_parser("update", help="Update or move something on the map")
    map_update.add_argument("node_id")
    map_update.add_argument("--title")
    map_update.add_argument("--summary")
    map_update.add_argument("--parent", dest="parent_id")
    map_update.add_argument("--status", choices=["primary", "active", "dormant", "closed"])
    map_update.add_argument("--promise", choices=["high", "medium", "low", "unassessed"])
    map_update.add_argument("--reason", default="")
    map_connect = map_subparsers.add_parser("connect", help="Show how two research-map items relate")
    map_connect.add_argument("source_id")
    map_connect.add_argument("target_id")
    map_connect.add_argument(
        "--relationship",
        required=True,
        choices=["explores", "tests", "produces", "revises", "leads-to", "alternative-to", "supports", "challenges", "informs", "depends-on", "related"],
    )
    map_connect.add_argument("--note", default="")
    map_disconnect = map_subparsers.add_parser("disconnect", help="Remove a relationship from the map")
    map_disconnect.add_argument("link_id")
    for item in (map_show, map_add_question, map_add_idea, map_add_test, map_add_work, map_add_finding, map_update, map_connect, map_disconnect):
        item.add_argument("--workspace")
        item.add_argument("--url", default=_default_api_url())

    args = parser.parse_args(argv)
    if args.command == "ui":
        _run_ui(args.host, args.port, not args.no_open, args.data)
        return

    if args.command == "serve":
        import uvicorn
        from .api import create_app

        public_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
        uvicorn.run(
            create_app(api_url=f"http://{public_host}:{args.port}"),
            host=args.host,
            port=args.port,
            reload=False,
        )
        return

    if args.command == "connect":
        _connect_remote(
            args.host,
            args.remote_port,
            args.local_port,
            not args.no_open,
        )
        return

    if args.command == "terminal":
        _attach_terminal(args.url, args.session_id)
        return

    if args.command == "context":
        _show_context(args.url, args.workspace, args.node, args.as_json)
        return

    if args.command == "project":
        if args.project_command == "inspect-remote":
            _inspect_remote_project(
                args.url,
                args.workspace,
                args.ssh_host,
                args.project_path,
                args.as_json,
            )
        elif args.project_command == "read-remote":
            _read_remote_project(
                args.url,
                args.workspace,
                args.ssh_host,
                args.project_path,
                args.paths,
                args.as_json,
            )
        else:
            _finish_project_setup(
                args.url,
                args.workspace,
                args.summary,
                args.reference,
                args.constraint,
                args.prior_work,
                args.reusable_inputs,
                args.success_condition,
                args.stop_condition,
                args.budget,
                args.permission_mode,
                args.environment_verified,
                args.git_reviewed,
            )
        return

    if args.command == "compute":
        if args.compute_command == "show":
            _show_compute(args.url, args.workspace, args.as_json)
        elif args.compute_command == "set":
            _set_compute(
                args.url,
                args.workspace,
                args.kind,
                args.name,
                args.ssh_host,
                args.project_path,
                args.run_path,
                args.setup_command,
                args.gpu_devices,
                args.max_parallel,
            )
        elif args.compute_command == "check":
            _check_compute(args.url, args.workspace)
        elif args.compute_command == "inspect":
            _inspect_compute(
                args.url,
                args.workspace,
                args.local,
                args.ssh_host,
                args.project_path,
                args.run_path,
                args.as_json,
            )
        else:
            _reset_compute(args.url, args.workspace)
        return

    if args.command == "git":
        if args.git_command == "check":
            _check_git(args.url, args.workspace, args.as_json)
        else:
            _show_git(args.url, args.workspace, args.as_json)
        return

    if args.command == "work":
        if args.work_command == "show":
            _show_work(args.url, args.workspace, args.as_json)
        elif args.work_command == "start":
            _start_work(
                args.url,
                args.workspace,
                args.approach_id,
                args.title,
                args.goal,
                args.instructions,
                args.measure,
                args.command,
                args.inputs,
                args.comparison,
                args.expected,
                args.limits,
                args.do_not_change,
                args.budget,
            )
        elif args.work_command == "review":
            _review_work(
                args.url,
                args.workspace,
                args.run_id,
                args.outcome,
                args.validity,
                args.meaning,
                args.next_step,
                args.adaptations,
                args.notes,
                args.keep_code,
            )
        else:
            _cancel_work(args.url, args.workspace, args.run_id)
        return

    if args.command == "policy":
        if args.policy_command == "show":
            _show_policy(args.url, args.workspace, args.node)
        else:
            _set_policy(
                args.url,
                args.workspace,
                args.node,
                args.kind,
                args.guidance,
                args.ask_before,
            )
        return

    if args.command == "question":
        _set_question(args.url, args.workspace, args.question, args.reason)
        return

    if args.command == "rules":
        if args.rules_command == "show":
            _show_rules(args.url, args.workspace, args.as_json)
        elif args.rules_command == "sync":
            _sync_rules(args.url, args.workspace)
        elif args.rules_command == "apply":
            _apply_rules(args.url, args.workspace, args.file)
        elif args.rules_command == "add":
            _add_rule(
                args.url,
                args.workspace,
                args.title,
                args.instruction,
                args.category,
                args.when,
                args.scope,
                args.expires_when,
                args.enabled,
            )
        else:
            _update_rule(
                args.url,
                args.workspace,
                args.rule_id,
                args.title,
                args.instruction,
                args.category,
                args.when,
                args.scope,
                args.expires_when,
                args.enabled,
            )
        return

    if args.command == "harness":
        if args.harness_command == "show":
            _show_harness(args.url, args.workspace)
        else:
            _update_harness(args.url, args.workspace)
        return

    if args.command == "map":
        if args.map_command == "show":
            _show_map(args.url, args.workspace, args.as_json)
        elif args.map_command == "add-question":
            _add_map_node(args.url, args.workspace, "question", args.title, args.summary, None)
        elif args.map_command == "add-idea":
            _add_map_node(args.url, args.workspace, "idea", args.title, args.summary, args.parent_id, relationship=args.relationship)
        elif args.map_command == "add-test":
            _add_map_node(
                args.url,
                args.workspace,
                "way-to-test",
                args.title,
                args.summary,
                args.parent_id,
            )
        elif args.map_command == "add-work":
            _add_map_node(
                args.url,
                args.workspace,
                "work",
                args.title,
                args.summary,
                args.parent_id,
                work_kind=args.work_kind,
                relationship=args.relationship,
            )
        elif args.map_command == "add-finding":
            _add_map_node(
                args.url,
                args.workspace,
                "finding",
                args.title,
                args.summary,
                args.parent_id,
            )
        elif args.map_command == "update":
            _update_map_node(
                args.url,
                args.workspace,
                args.node_id,
                args.title,
                args.summary,
                args.parent_id,
                args.status,
                args.promise,
                args.reason,
            )
        elif args.map_command == "connect":
            _connect_map_nodes(
                args.url,
                args.workspace,
                args.source_id,
                args.target_id,
                args.relationship,
                args.note,
            )
        else:
            _disconnect_map_nodes(args.url, args.workspace, args.link_id)
        return

    try:
        snapshot = import_workspace(args.path)
    except ImportFailure as exc:
        parser.error(str(exc))
    print(json.dumps(snapshot.model_dump(mode="json"), indent=2))


def ui_main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "connect":
        main(sys.argv[1:], program="delta-loop")
    else:
        main(["ui", *sys.argv[1:]], program="delta-loop")


def _default_data_path() -> Path:
    configured = os.environ.get("DELTA_LOOP_DATA_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".delta-loop" / "workspaces.json").resolve()


def _app_is_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=0.6) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _open_when_ready(url: str) -> None:
    for _ in range(80):
        if _app_is_running(url):
            webbrowser.open(url)
            return
        time.sleep(0.1)


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _connection_port(preferred: int) -> tuple[int, bool]:
    preferred_url = f"http://127.0.0.1:{preferred}"
    if _app_is_running(preferred_url):
        return preferred, True
    if _port_is_available(preferred):
        return preferred, False
    for candidate in range(preferred + 1, preferred + 21):
        if _app_is_running(f"http://127.0.0.1:{candidate}"):
            return candidate, True
        if _port_is_available(candidate):
            return candidate, False
    raise SystemExit(
        f"Could not find a free local port from {preferred} through {preferred + 20}."
    )


def _connect_remote(
    host: str,
    remote_port: int,
    local_port: int,
    open_browser: bool,
) -> None:
    chosen_port, already_connected = _connection_port(local_port)
    url = f"http://127.0.0.1:{chosen_port}"
    if already_connected:
        print(f"Delta Loop is already reachable at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    if chosen_port != local_port:
        print(
            f"Local port {local_port} is occupied but not responding. "
            f"Using {chosen_port} instead."
        )

    command = [
        "ssh",
        "-N",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=3",
        "-L", f"{chosen_port}:127.0.0.1:{remote_port}",
        host,
    ]
    opened = False
    print(f"Connecting to remote Delta Loop at {url}")
    print("Keep this command running. It will reconnect after sleep or a network interruption.")
    print("Press Ctrl+C to disconnect.")
    try:
        while True:
            process = subprocess.Popen(command)
            while process.poll() is None:
                if _app_is_running(url):
                    if not opened:
                        print(f"Delta Loop is ready at {url}")
                        if open_browser:
                            webbrowser.open(url)
                        opened = True
                    time.sleep(2)
                else:
                    time.sleep(1)
            print("Connection was interrupted. Retrying…")
            time.sleep(2)
    except KeyboardInterrupt:
        if "process" in locals() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        print("\nDisconnected from remote Delta Loop.")


def _run_ui(host: str, port: int, open_browser: bool, data_path: str | None) -> None:
    import uvicorn

    from .api import create_app

    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"
    if _app_is_running(url):
        print(f"Delta Loop is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return

    store_path = Path(data_path).expanduser().resolve() if data_path else _default_data_path()
    try:
        application = create_app(
            store_path,
            serve_web=True,
            api_url=url,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    if open_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    print(f"Opening Delta Loop at {url}")
    print(f"Your Delta Loop data is stored in {store_path.parent}")
    print("Keep this window open while using Delta Loop. Press Ctrl+C to stop it.")
    uvicorn.run(application, host=host, port=port, reload=False)


def _attach_terminal(base_url: str, session_id: str) -> None:
    from websockets.sync.client import connect

    url = f"{base_url.rstrip('/')}/api/terminals/{session_id}/ws"
    old_settings = termios.tcgetattr(sys.stdin.fileno())
    finished = threading.Event()
    with connect(url) as websocket:
        print("Attached. Press Ctrl-] to return to your local shell.\r", file=sys.stderr)

        def receive() -> None:
            try:
                for message in websocket:
                    data = message if isinstance(message, bytes) else message.encode()
                    os.write(sys.stdout.fileno(), data)
            finally:
                finished.set()

        receiver = threading.Thread(target=receive, daemon=True)
        receiver.start()
        try:
            tty.setraw(sys.stdin.fileno())
            while not finished.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.2)
                if not ready:
                    continue
                data = os.read(sys.stdin.fileno(), 1024)
                if b"\x1d" in data:
                    break
                websocket.send(data)
        finally:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)


def _ids(workspace_id: str | None, node_id: str | None = None) -> tuple[str, str | None]:
    workspace = workspace_id or os.environ.get("DELTA_LOOP_WORKSPACE_ID", "")
    node = node_id or os.environ.get("DELTA_LOOP_NODE_ID") or None
    if not workspace:
        raise SystemExit("No Delta Loop project is connected to this terminal. Use --workspace.")
    return workspace, node


def _api_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    full_url = f"{base_url.rstrip('/')}{path}"
    if os.environ.get("CODEX_NETWORK_PROXY_ACTIVE") == "1" and os.environ.get("HTTP_PROXY"):
        return _api_json_through_codex_proxy(full_url, method, data)
    request = urllib.request.Request(
        full_url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("detail")
        except (json.JSONDecodeError, AttributeError):
            detail = None
        raise SystemExit(detail or f"Delta Loop returned {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise SystemExit("Delta Loop is not running on the expected local address.") from exc


def _api_json_through_codex_proxy(full_url: str, method: str, data: bytes | None):
    proxy = urllib.parse.urlparse(os.environ["HTTP_PROXY"])
    if proxy.scheme != "http" or not proxy.hostname:
        raise SystemExit("The agent's local connection is not configured correctly.")
    connection = http.client.HTTPConnection(proxy.hostname, proxy.port or 80, timeout=30)
    try:
        connection.request(
            method,
            full_url,
            body=data,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
    except (OSError, http.client.HTTPException) as exc:
        raise SystemExit("Delta Loop is not running on the expected local address.") from exc
    finally:
        connection.close()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SystemExit("Delta Loop returned an unreadable response.") from exc
    if response.status >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise SystemExit(detail or f"Delta Loop returned {response.status}.")
    return body


def _workspace(base_url: str, workspace_id: str) -> dict:
    encoded = urllib.parse.quote(workspace_id, safe="")
    return _api_json(base_url, f"/api/workspaces/{encoded}")


def _selected_node(workspace: dict, node_id: str | None) -> dict | None:
    return next((node for node in workspace.get("nodes", []) if node["id"] == node_id), None)


def _show_context(base_url: str, workspace_id: str | None, node_id: str | None, as_json: bool) -> None:
    workspace_id, node_id = _ids(workspace_id, node_id)
    workspace = _workspace(base_url, workspace_id)
    node = _selected_node(workspace, node_id)
    nodes_by_id = {item["id"]: item for item in workspace.get("nodes", [])}
    selected_relationships = []
    if node:
        for link in workspace.get("research_links", []):
            if link["source_id"] == node["id"]:
                other = nodes_by_id.get(link["target_id"])
                if other:
                    selected_relationships.append(
                        {"direction": "outgoing", "relationship": link["relationship"], "item": other}
                    )
            elif link["target_id"] == node["id"]:
                other = nodes_by_id.get(link["source_id"])
                if other:
                    selected_relationships.append(
                        {"direction": "incoming", "relationship": link["relationship"], "item": other}
                    )
    context = {
        "main_question": workspace["goal"],
        "research_questions": [
            item for item in workspace.get("nodes", []) if item["kind"] == "question"
        ],
        "selected": node,
        "selected_relationships": selected_relationships,
        "compute": workspace.get("compute"),
        "research_loop_instructions": workspace.get("loop_file"),
        "base_harness": workspace.get("harness"),
        "recent_work": [
            {
                "title": plan["title"],
                "status": plan["status"],
                "what_it_tests": plan["goal"],
                "method": plan["instructions"],
                "data": plan["inputs"],
            }
            for plan in workspace.get("packages", [])
            if not node or node.get("kind") != "approach" or plan["approach_id"] == node["id"]
        ][-3:],
    }
    if as_json:
        print(json.dumps(context, indent=2))
        return
    print(f"Main question: {context['main_question']}")
    other_questions = [
        item for item in context["research_questions"] if item["title"] != context["main_question"]
    ]
    for question in other_questions:
        print(f"Additional question [{question['id']}]: {question['title']}")
    if workspace.get("setup_status") == "needs-setup":
        print("Project setup: incomplete — agree on the research questions and map before research starts")
    compute = context["compute"] or {}
    if not compute.get("configured"):
        print("Work runs on: not set up")
    elif compute.get("kind") == "ssh":
        print(
            f"Work runs on: {compute.get('name') or compute.get('ssh_host')} "
            f"over SSH ({compute.get('status', 'unchecked')})"
        )
        print(f"Remote project: {compute.get('project_path')}")
    else:
        print("Work runs on: this computer")
    if context["research_loop_instructions"]:
        print(f"Complete research loop: {context['research_loop_instructions']}")
    if node:
        node_label = {"question": "question", "direction": "idea", "approach": "experiment"}.get(
            node["kind"], node["kind"]
        )
        print(f"Selected {node_label}: {node['title']}")
        for relationship in selected_relationships:
            arrow = "→" if relationship["direction"] == "outgoing" else "←"
            print(
                f"  {arrow} {relationship['relationship']}: "
                f"{relationship['item']['title']} [{relationship['item']['id']}]"
            )
        if node["kind"] == "approach":
            print(f"Next work: {node['next_work_kind'].replace('-', ' ')}")
            print(f"Guidance: {node['agent_guidance'] or 'None recorded.'}")
            print(f"Stop only if: {node['ask_before'] or 'No additional stop recorded.'}")
    else:
        print("No idea is selected for this terminal.")


def _show_compute(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    compute = _workspace(base_url, workspace_id).get("compute", {})
    if as_json:
        print(json.dumps(compute, indent=2))
        return
    if not compute.get("configured"):
        print("No compute location is set up. Choose this computer or a remote server.")
        return
    if compute.get("kind") == "ssh":
        print(f"Work runs on: {compute.get('name') or compute.get('ssh_host')}")
        print(f"SSH host: {compute.get('ssh_host')}")
        print(f"Remote project: {compute.get('project_path')}")
        print(f"Remote run records: {compute.get('run_path')}")
        print(f"Environment setup: {compute.get('setup_command') or 'None'}")
        print(f"GPU(s): {compute.get('gpu_devices') or 'No restriction'}")
    else:
        print("Work runs on: this computer")
    print(f"At most {compute.get('max_parallel', 1)} run(s) at once")
    print(f"Connection: {compute.get('status', 'unchecked')}")
    print(compute.get("status_message") or "Not checked yet.")


def _git_view(workspace: dict) -> dict:
    active_id = workspace.get("active_rules_version_id")
    active = next(
        (
            version
            for version in workspace.get("rules_versions", [])
            if version.get("id") == active_id
        ),
        {},
    )
    return {
        "repository": workspace.get("git_repository", {}),
        "rules": [
            rule for rule in active.get("rules", [])
            if rule.get("category") == "git"
        ],
        "delta_loop_control_folder": workspace.get("root", ""),
    }


def _print_git(view: dict) -> None:
    repository = view["repository"]
    print(f"Research repository: {repository.get('location') or 'not checked'}")
    print(repository.get("message") or "The repository has not been checked yet.")
    if repository.get("repository_found"):
        print(f"Branch: {repository.get('branch') or 'unknown'}")
        print(f"Remote: {repository.get('remote_url') or 'none configured'}")
        print(f"Upstream: {repository.get('upstream') or 'none configured'}")
        print(
            f"Local branch position: {repository.get('ahead', 0)} ahead, "
            f"{repository.get('behind', 0)} behind (using existing local refs; no fetch was run)"
        )
        print(f"Changed paths: {len(repository.get('changed_files', []))}")
        if repository.get("last_commit"):
            print(f"Last commit: {repository['last_commit']}")
    enabled = [rule for rule in view["rules"] if rule.get("enabled")]
    if enabled:
        print("Active Git policy:")
        for rule in enabled:
            print(f"- {rule['title']}: {rule['instruction']}")
    else:
        print("Active Git policy: off. The agent must not commit or push.")
    print(f"Delta Loop control folder: {view['delta_loop_control_folder']}")


def _show_git(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    view = _git_view(_workspace(base_url, workspace_id))
    if as_json:
        print(json.dumps(view, indent=2))
        return
    _print_git(view)


def _check_git(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    workspace = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/git/check",
        method="POST",
    )
    view = _git_view(workspace)
    if as_json:
        print(json.dumps(view, indent=2))
        return
    _print_git(view)


def _finish_project_setup(
    base_url: str,
    workspace_id: str | None,
    summary: str,
    references: list[str],
    constraints: list[str],
    prior_work: list[str],
    reusable_inputs: list[str],
    success_condition: str,
    stop_condition: str,
    budget: str,
    permission_mode: str,
    environment_verified: bool,
    git_reviewed: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/setup/complete",
        method="POST",
        payload={
            "summary": summary,
            "reference_repos": references,
            "constraints": constraints,
            "prior_work": prior_work,
            "reusable_inputs": reusable_inputs,
            "success_condition": success_condition,
            "stop_condition": stop_condition,
            "budget": budget,
            "permission_mode": permission_mode,
            "environment_verified": environment_verified,
            "git_reviewed": git_reviewed,
        },
    )
    print(f"Project setup complete: {updated['name']}")
    print(f"Main question: {updated['goal']}")
    print(f"Created: {updated['root']}/STATE.md")
    print(f"Initialization record: {updated['initialization']['initialization_file']}")
    print("Created or reused INFRA.md, SYNTHESIS.md, REPORTS/, RUNS/, and LITERATURE/INDEX.md.")


def _inspect_remote_project(
    base_url: str,
    workspace_id: str | None,
    ssh_host: str,
    project_path: str,
    as_json: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    inspection = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/setup/inspect-remote",
        method="POST",
        payload={"ssh_host": ssh_host, "project_path": project_path},
    )
    if as_json:
        print(json.dumps(inspection, indent=2))
        return
    print(
        f"Remote project: {inspection['project_path']} "
        f"({'found' if inspection['project_exists'] else 'missing'})"
    )
    print(
        f"Mapped {inspection['total_files']} files recursively"
        f"{' (showing the first 500)' if inspection['inventory_truncated'] else ''}."
    )
    if inspection["file_types"]:
        common_types = sorted(
            inspection["file_types"].items(), key=lambda item: item[1], reverse=True
        )[:12]
        print("Main file types: " + ", ".join(f"{kind} {count}" for kind, count in common_types))
    if inspection["top_level_files"]:
        print("Recursive project tree:")
        for name in inspection["top_level_files"]:
            print(f"- {name}")
    if inspection["entry_points"]:
        print("Likely entry points:")
        for name in inspection["entry_points"]:
            print(f"- {name}")
    for name, content in inspection["documentation"].items():
        print(f"\n--- {name} (bounded excerpt) ---")
        print(content.rstrip())
    if inspection["git_branch"] or inspection["git_remote"]:
        print(
            f"\nGit: branch {inspection['git_branch'] or 'unknown'} · "
            f"origin {inspection['git_remote'] or 'not set'}"
        )
    if inspection["git_status"]:
        print("Changed paths (at most 60):")
        for line in inspection["git_status"]:
            print(f"- {line}")
    if inspection["recent_commits"]:
        print("Recent commits:")
        for line in inspection["recent_commits"]:
            print(f"- {line}")


def _read_remote_project(
    base_url: str,
    workspace_id: str | None,
    ssh_host: str,
    project_path: str,
    paths: list[str],
    as_json: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    reading = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/setup/read-remote",
        method="POST",
        payload={
            "ssh_host": ssh_host,
            "project_path": project_path,
            "paths": paths,
        },
    )
    if as_json:
        print(json.dumps(reading, indent=2))
        return
    for name, content in reading["files"].items():
        print(f"\n--- {name} (first 16 KB) ---")
        print(content.rstrip())
    for name, problem in reading["problems"].items():
        print(f"\nCould not read {name}: {problem}")


def _set_compute(
    base_url: str,
    workspace_id: str | None,
    kind: str | None,
    name: str | None,
    ssh_host: str | None,
    project_path: str | None,
    run_path: str | None,
    setup_command: str | None,
    gpu_devices: str | None,
    max_parallel: int | None,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace = _workspace(base_url, workspace_id)
    current = workspace.get("compute", {})
    changes = {
        key: value
        for key, value in {
            "kind": kind,
            "name": name,
            "ssh_host": ssh_host,
            "project_path": project_path,
            "run_path": run_path,
            "setup_command": setup_command,
            "gpu_devices": gpu_devices,
            "max_parallel": max_parallel,
        }.items()
        if value is not None
    }
    if not changes:
        raise SystemExit("Nothing changed. Add --kind or one of the compute settings.")
    fields = [
        "kind",
        "name",
        "ssh_host",
        "project_path",
        "run_path",
        "setup_command",
        "gpu_devices",
        "max_parallel",
    ]
    payload = {field: current.get(field) for field in fields}
    payload.update(changes)
    if kind == "local" and name is None:
        payload["name"] = "This computer"
    if kind == "ssh" and name is None and current.get("kind") != "ssh":
        payload["name"] = ssh_host or "Remote server"
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/compute",
        method="PUT",
        payload=payload,
    )
    compute = updated["compute"]
    print(
        "Saved remote compute settings. Run `delta compute check` before starting work."
        if compute["kind"] == "ssh"
        else "Research work will run on this computer."
    )


def _check_compute(base_url: str, workspace_id: str | None) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/compute/check",
        method="POST",
    )
    compute = updated["compute"]
    print(f"Connection: {compute['status']}")
    print(compute["status_message"])
    if compute.get("detected_python"):
        print(f"Python: {compute['detected_python']}")
    if compute.get("detected_gpus"):
        print("GPU(s):")
        for gpu in compute["detected_gpus"]:
            print(f"- {gpu}")


def _reset_compute(base_url: str, workspace_id: str | None) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/compute/reset",
        method="POST",
    )
    print("Compute setup reset. Run history and research files were not changed.")


def _inspect_compute(
    base_url: str,
    workspace_id: str | None,
    local: bool,
    ssh_host: str | None,
    project_path: str | None,
    run_path: str | None,
    as_json: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    payload = {
        key: value
        for key, value in {
            "ssh_host": ssh_host,
            "project_path": project_path,
            "run_path": run_path,
        }.items()
        if value is not None
    }
    payload["kind"] = "local" if local else "ssh"
    inspection = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/compute/inspect",
        method="POST",
        payload=payload,
    )
    if as_json:
        print(json.dumps(inspection, indent=2))
        return
    print("Detected facts (read-only inspection):")
    print(f"- Host: {inspection['hostname'] or inspection['host']} · {inspection['operating_system'] or 'OS unknown'}")
    print(
        f"- Project: {inspection['project_path']} "
        f"({'found' if inspection['project_exists'] else 'missing'}, "
        f"{'writable' if inspection['project_writable'] else 'not writable'})"
    )
    print(f"- Run path: {inspection['run_path']} · parent {'writable' if inspection['run_parent_writable'] else 'not writable'}")
    print(f"- Scheduler: {inspection['scheduler']}")
    print(f"- Python now: {inspection['python_path'] or 'not found'} {inspection['python_version']}")
    print(f"- CPU: {inspection['cpu'] or 'not detected'} · Memory: {inspection['memory'] or 'not detected'}")
    print(f"- GPU(s): {len(inspection['gpus']) if inspection['gpus'] else 'none visible'}")
    for gpu in inspection["gpus"]:
        print(f"  - {gpu}")
    print(f"- Existing INFRA.md: {'yes' if inspection['has_infra'] else 'no'}")
    if inspection["dependency_files"]:
        print(f"- Environment files: {', '.join(inspection['dependency_files'])}")
    if inspection["environment_tools"]:
        print(f"- Environment tools: {', '.join(inspection['environment_tools'])}")
    if inspection["environment_candidates"]:
        print("- Possible environments (not selected yet):")
        for candidate in inspection["environment_candidates"]:
            print(f"  - {candidate}")
    if inspection["git_branch"] or inspection["git_remote"]:
        print(
            f"- Git: branch {inspection['git_branch'] or 'unknown'} · "
            f"{inspection['git_status'] or 'status unknown'} · "
            f"origin {inspection['git_remote'] or 'not set'}"
        )
    for note in inspection["notes"]:
        print(f"- Note: {note}")
    print("\nHuman confirmation still needed:")
    print("- Which environment and exact setup command should runs use?")
    print("- Which GPUs and how many simultaneous runs are allowed?")
    print("- Where should datasets, checkpoints, scratch files, and caches go?")
    print("- Are there login-node, Git, data, or lab rules that commands cannot reveal?")
    print("Do not install, move, or start anything until those choices are confirmed.")


def _show_work(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace = _workspace(base_url, workspace_id)
    plans = {plan["id"]: plan for plan in workspace.get("packages", [])}
    attempts = list(reversed(workspace.get("attempts", [])))
    if as_json:
        print(json.dumps(attempts, indent=2))
        return
    if not attempts:
        print("No research work has been started through Delta Loop yet.")
        return
    for attempt in attempts[:10]:
        plan = plans.get(attempt["package_id"], {})
        location = (
            f"{attempt.get('compute_name')} over SSH ({attempt.get('remote_host')})"
            if attempt.get("executor") == "ssh"
            else "this computer"
        )
        output = (
            attempt.get("remote_output_directory")
            if attempt.get("executor") == "ssh"
            else attempt.get("output_directory")
        )
        print(f"{attempt['id']} · {attempt['status']} · {plan.get('title', 'Research work')}")
        print(f"  Ran on: {location}")
        if output:
            print(f"  Output: {output}")
        if attempt.get("output"):
            print(f"  Latest: {attempt['output'][-1]}")
        if attempt.get("error"):
            print(f"  Problem: {attempt['error']}")


def _start_work(
    base_url: str,
    workspace_id: str | None,
    approach_id: str,
    title: str,
    goal: str,
    instructions: str,
    measure: str,
    command: str,
    inputs: str,
    comparison: str,
    expected: str,
    limits: str,
    do_not_change: str,
    budget: str,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    before = _workspace(base_url, workspace_id)
    known = {plan["id"] for plan in before.get("packages", [])}
    created = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/plans",
        method="POST",
        payload={"approach_id": approach_id, "title": title},
    )
    plan = next(plan for plan in created["packages"] if plan["id"] not in known)
    plan_path = urllib.parse.quote(plan["id"], safe="")
    _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/plans/{plan_path}",
        method="PATCH",
        payload={
            "goal": goal,
            "instructions": instructions,
            "inputs": inputs,
            "comparison": comparison,
            "measure": measure,
            "expected": expected,
            "limits": limits,
            "do_not_change": do_not_change,
            "command": command,
            "budget": budget,
        },
    )
    _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/plans/{plan_path}/approve",
        method="POST",
    )
    started = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/plans/{plan_path}/run",
        method="POST",
    )
    attempt = started["attempts"][-1]
    location = (
        f"{attempt['compute_name']} over SSH"
        if attempt["executor"] == "ssh"
        else "this computer"
    )
    print(f"Started {attempt['id']} on {location}.")
    print("Use `delta work show` to follow it.")


def _cancel_work(base_url: str, workspace_id: str | None, run_id: str) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    run_path = urllib.parse.quote(run_id, safe="")
    _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/runs/{run_path}/cancel",
        method="POST",
    )
    print(f"Stopped {run_id}.")


def _review_work(
    base_url: str,
    workspace_id: str | None,
    run_id: str,
    outcome: str,
    validity: str,
    meaning: str,
    next_step: str,
    adaptations: str,
    notes: str,
    keep_code: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    run_path = urllib.parse.quote(run_id, safe="")
    reviewed = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/runs/{run_path}/review",
        method="POST",
        payload={
            "trust_result": (
                "no" if validity == "invalid" else "unsure" if validity == "unsure" else "yes"
            ),
            "execution_validity": validity,
            "evidence_outcome": outcome,
            "adaptations": adaptations,
            "what_it_means": meaning,
            "next_step": next_step,
            "notes": notes,
            "keep_code": keep_code,
        },
    )
    review = next(item for item in reviewed["reviews"] if item["attempt_id"] == run_id)
    print(f"Recorded {review['evidence_outcome']} evidence for {run_id}.")
    if adaptations:
        print("Implementation adaptations were saved separately and were not counted as a failure.")


def _show_policy(base_url: str, workspace_id: str | None, node_id: str | None) -> None:
    workspace_id, node_id = _ids(workspace_id, node_id)
    workspace = _workspace(base_url, workspace_id)
    node = _selected_node(workspace, node_id)
    if not node or node["kind"] != "approach":
        raise SystemExit("Select a way to test an idea before reading its policy.")
    print(f"Idea: {node['title']}")
    print(f"Next work: {node['next_work_kind'].replace('-', ' ')}")
    print(f"Guidance: {node['agent_guidance'] or 'None recorded.'}")
    print(f"Stop only if: {node['ask_before'] or 'No additional stop recorded.'}")


def _show_harness(base_url: str, workspace_id: str | None) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace = _workspace(base_url, workspace_id)
    harness = workspace.get("harness", {})
    print(f"Source: {harness.get('source_url') or 'Unknown'}")
    print(f"Local checkout: {harness.get('path') or 'Not found'}")
    print(f"Revision: {harness.get('revision') or 'Unknown'}")
    print(f"Status: {harness.get('status') or 'unknown'}")
    print(harness.get("detail") or "No status detail is available.")


def _update_harness(base_url: str, workspace_id: str | None) -> None:
    workspace_id, _ = _ids(workspace_id)
    encoded = urllib.parse.quote(workspace_id, safe="")
    workspace = _api_json(base_url, f"/api/workspaces/{encoded}/harness/update", method="POST")
    harness = workspace["harness"]
    print(f"delta-research is at {harness['revision'][:12]} in {harness['path']}")
    print(harness["detail"])


def _set_policy(
    base_url: str,
    workspace_id: str | None,
    node_id: str | None,
    kind: str | None,
    guidance: str | None,
    ask_before: str | None,
) -> None:
    workspace_id, node_id = _ids(workspace_id, node_id)
    if not node_id:
        raise SystemExit("Select a way to test an idea before updating its policy.")
    changes = {
        key: value
        for key, value in {
            "next_work_kind": kind,
            "agent_guidance": guidance,
            "ask_before": ask_before,
        }.items()
        if value is not None
    }
    if not changes:
        raise SystemExit("Nothing changed. Add --kind, --guidance, or --ask-before.")
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    node_path = urllib.parse.quote(node_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/nodes/{node_path}",
        method="PATCH",
        payload=changes,
    )
    node = _selected_node(updated, node_id)
    print(f"Updated policy for: {node['title'] if node else node_id}")


def _set_question(base_url: str, workspace_id: str | None, question: str, reason: str) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}",
        method="PATCH",
        payload={"goal": question, "reason": reason},
    )
    print(f"Updated main question: {updated['goal']}")


def _active_rules(workspace: dict) -> dict:
    active_id = workspace.get("active_rules_version_id")
    version = next(
        (item for item in workspace.get("rules_versions", []) if item["id"] == active_id),
        None,
    )
    if not version:
        raise SystemExit("This project does not have an active general policy.")
    return version


def _show_rules(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    version = _active_rules(_workspace(base_url, workspace_id))
    if as_json:
        print(json.dumps(version["rules"], indent=2))
        return
    print(f"Policy version {version['version']}:")
    categories = ["loop", "checkpoint", "project", "git", "hardware", "data", "resources", "temporary"]
    for category in categories:
        rules = [rule for rule in version["rules"] if rule["category"] == category]
        if not rules:
            continue
        print(f"\n{category.replace('-', ' ').title()}:")
        for rule in rules:
            state = "used" if rule["enabled"] else "off"
            required = ", required" if rule["cannot_override"] else ""
            title = "Quick Test" if rule["id"] == "start-with-small-test" else rule["title"]
            print(f"- {title} [{rule['id']}] ({state}{required})")
            print(f"  When: {rule['when']}")
            print(f"  Do: {rule['instruction']}")
            print(f"  Applies to: {rule['scope']}")
            if rule["expires_when"]:
                print(f"  Ends: {rule['expires_when']}")


def _sync_rules(base_url: str, workspace_id: str | None) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/policy/sync",
        method="POST",
    )
    print(f"Research loop policy written to: {updated['policy_file']}")
    print(f"Written at: {updated['policy_synced_at']}")


def _apply_rules(base_url: str, workspace_id: str | None, file_name: str) -> None:
    workspace_id, _ = _ids(workspace_id)
    try:
        raw = sys.stdin.read() if file_name == "-" else Path(file_name).read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read the policy JSON: {exc}") from exc
    rules = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(rules, list):
        raise SystemExit("The policy JSON must be a list of rules or an object with a 'rules' list.")
    _activate_rule_list(base_url, workspace_id, rules)


def _activate_rule_list(base_url: str, workspace_id: str, rules: list[dict]) -> dict:
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    drafted = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/rules/drafts",
        method="POST",
        payload={"rules": rules},
    )
    version = drafted["rules_versions"][-1]
    checked = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/rules/{urllib.parse.quote(version['id'], safe='')}/check",
        method="POST",
    )
    checked_version = next(item for item in checked["rules_versions"] if item["id"] == version["id"])
    if checked_version["problems"]:
        problems = "\n".join(f"- {problem}" for problem in checked_version["problems"])
        raise SystemExit(f"The new policy was saved but not used because it has problems:\n{problems}")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/rules/{urllib.parse.quote(version['id'], safe='')}/use",
        method="POST",
    )
    active = _active_rules(updated)
    print(f"Now using general policy version {active['version']} with {len(active['rules'])} rules.")
    return updated


def _add_rule(
    base_url: str,
    workspace_id: str | None,
    title: str,
    instruction: str,
    category: str,
    when: str,
    scope: str,
    expires_when: str,
    enabled: bool,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    rules = [dict(rule) for rule in _active_rules(_workspace(base_url, workspace_id))["rules"]]
    rule_id = f"custom-{uuid4().hex[:10]}"
    rules.append(
        {
            "id": rule_id,
            "title": title,
            "instruction": instruction,
            "category": category,
            "when": when,
            "scope": scope,
            "expires_when": expires_when,
            "enabled": enabled,
            "cannot_override": False,
        }
    )
    _activate_rule_list(base_url, workspace_id, rules)
    print(f"Added policy rule: {title} [{rule_id}]")


def _update_rule(
    base_url: str,
    workspace_id: str | None,
    rule_id: str,
    title: str | None,
    instruction: str | None,
    category: str | None,
    when: str | None,
    scope: str | None,
    expires_when: str | None,
    enabled: bool | None,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    rules = [dict(rule) for rule in _active_rules(_workspace(base_url, workspace_id))["rules"]]
    rule = next((item for item in rules if item["id"] == rule_id), None)
    if not rule:
        raise SystemExit(f"Policy rule not found: {rule_id}")
    changes = {
        key: value
        for key, value in {
            "title": title,
            "instruction": instruction,
            "category": category,
            "when": when,
            "scope": scope,
            "expires_when": expires_when,
            "enabled": enabled,
        }.items()
        if value is not None
    }
    if not changes:
        raise SystemExit("Nothing changed. Add a policy field or use --on/--off.")
    rule.update(changes)
    _activate_rule_list(base_url, workspace_id, rules)
    print(f"Updated policy rule: {rule['title']} [{rule_id}]")


def _map_nodes(workspace: dict) -> list[dict]:
    return [
        {
            "id": node["id"],
            "kind": node["kind"],
            "title": node["title"],
            "summary": node["summary"],
            "parent_id": node["parent_id"],
            "status": node["status"],
            "promise": node["promise"],
            "evidence_strength": node["evidence_strength"],
            "next_work_kind": node["next_work_kind"],
        }
        for node in workspace.get("nodes", [])
    ]


def _show_map(base_url: str, workspace_id: str | None, as_json: bool) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace = _workspace(base_url, workspace_id)
    nodes = _map_nodes(workspace)
    links = workspace.get("research_links", [])
    if as_json:
        print(json.dumps({"nodes": nodes, "links": links}, indent=2))
        return
    labels = {"question": "Question", "direction": "Idea", "approach": "Work", "finding": "Finding"}
    for kind in ("question", "direction", "approach", "finding"):
        print(f"\n{labels[kind]}s")
        for node in (item for item in nodes if item["kind"] == kind):
            subtype = f", {node['next_work_kind'].replace('-', ' ')}" if kind == "approach" else ""
            print(f"- [{node['id']}] {node['title']} ({node['status']}{subtype})")
            if node["summary"]:
                print(f"  {node['summary']}")
    print("\nRelationships")
    by_id = {node["id"]: node for node in nodes}
    for link in links:
        source = by_id.get(link["source_id"], {"title": link["source_id"]})
        target = by_id.get(link["target_id"], {"title": link["target_id"]})
        print(f"- [{link['id']}] {source['title']} --{link['relationship']}--> {target['title']}")
        if link.get("note"):
            print(f"  {link['note']}")


def _add_map_node(
    base_url: str,
    workspace_id: str | None,
    kind: str,
    title: str,
    summary: str,
    parent_id: str | None,
    work_kind: str = "quick-test",
    relationship: str | None = None,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    before = _workspace(base_url, workspace_id)
    before_ids = {node["id"] for node in before.get("nodes", [])}
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/notes",
        method="POST",
        payload={
            "kind": kind,
            "text": title,
            "summary": summary,
            "parent_id": parent_id,
            "work_kind": work_kind,
            "relationship": relationship,
        },
    )
    created = next(node for node in updated["nodes"] if node["id"] not in before_ids)
    label = {"question": "question", "direction": "idea", "approach": "work", "finding": "finding"}[created["kind"]]
    print(f"Added {label}: {created['title']} [{created['id']}]")


def _connect_map_nodes(
    base_url: str,
    workspace_id: str | None,
    source_id: str,
    target_id: str,
    relationship: str,
    note: str,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/research-links",
        method="POST",
        payload={
            "source_id": source_id,
            "target_id": target_id,
            "relationship": relationship,
            "note": note,
        },
    )
    link = updated["research_links"][-1]
    print(f"Connected map items: {relationship} [{link['id']}]")


def _disconnect_map_nodes(
    base_url: str,
    workspace_id: str | None,
    link_id: str,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    link_path = urllib.parse.quote(link_id, safe="")
    _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/research-links/{link_path}",
        method="DELETE",
    )
    print(f"Removed relationship: {link_id}")


def _update_map_node(
    base_url: str,
    workspace_id: str | None,
    node_id: str,
    title: str | None,
    summary: str | None,
    parent_id: str | None,
    status: str | None,
    promise: str | None,
    reason: str,
) -> None:
    workspace_id, _ = _ids(workspace_id)
    changes = {
        key: value
        for key, value in {
            "title": title,
            "summary": summary,
            "parent_id": parent_id,
            "status": status,
            "promise": promise,
        }.items()
        if value is not None
    }
    if not changes:
        raise SystemExit("Nothing changed. Add a title, summary, parent, status, or potential.")
    changes["reason"] = reason
    workspace_path = urllib.parse.quote(workspace_id, safe="")
    node_path = urllib.parse.quote(node_id, safe="")
    updated = _api_json(
        base_url,
        f"/api/workspaces/{workspace_path}/nodes/{node_path}",
        method="PATCH",
        payload=changes,
    )
    node = _selected_node(updated, node_id)
    print(f"Updated map: {node['title'] if node else node_id}")
