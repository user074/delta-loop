# Delta Loop

A local dashboard for `delta-research`. It helps you see your ideas, choose what to test, tell an agent exactly
what to do, and review what happened without replacing the terminal.

## What the POC can do

- Import an existing `delta-research` project from `STATE.md`
- Show the main question, idea branches, ways to test them, and past evidence
- Add a quick idea or lab note without editing Markdown by hand
- Mark which ideas look promising, weak, active, or paused
- Choose a testing style for each approach, including “start small” or “repeat the original first”
- Turn a selected way of testing into a detailed plan and approve it before work starts
- Run an approved local command and keep its plan, output, and review together
- Run up to two independent approved plans at the same time
- Change the agent rules safely through checked, reversible versions
- Open a real terminal tied to the selected idea; hiding the panel does not stop the process
- Review whether a run followed the plan, whether the result is trustworthy, and what to do next

Delta Loop stores its own state in `.delta-loop-data/`, which is ignored by Git. It does not modify the
imported `delta-research` files in this POC.

## Run locally

You need Python 3.11 or newer and Node.js 20 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
npm --prefix web install
./scripts/dev.sh
```

Then open `http://127.0.0.1:4317`. The API runs on `http://127.0.0.1:4318`.

If you hide the terminal in the web page, it keeps running. You can show it again in the page or attach
from another local terminal:

```bash
delta terminal attach TERMINAL_ID
```

Press `Ctrl-]` to detach without ending the shell.

## Validate

```bash
pytest
npm --prefix web run build
```

The product direction and POC acceptance criteria live in [`docs/POC_PLAN.md`](docs/POC_PLAN.md).
