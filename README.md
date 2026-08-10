# Delta Loop

`delta-research`, plus the human control and visibility needed for day-to-day research. Delta Loop keeps the
upstream scientific loop as its base, then adds a visual idea map, editable policy, persistent agent supervision,
bounded handoffs, and clearer result review without replacing the terminal.

## What the POC can do

- Import an existing `delta-research` project from `STATE.md`
- Connect each project to the real `user074/delta-research` harness and record the exact local revision
- Show the editable main question and keep its earlier wording when the question changes
- Present the latest result and review as a compact research-update slide
- Map every test and result back to the idea it examined
- Discuss the research map with an agent that can add, clarify, move, or park ideas and ways to test them
- Show which ideas worked, failed, remain uncertain, or have not been tested
- Keep detailed agent plans underneath while showing only the method, data, and question to the researcher
- See the normal research loop, the extra checks that can pause it, and project-wide limits in one visual
- Set project-wide policy and special rules for particular ideas
- Start a focused agent chat from configuration that needs discussion; simple choices stay directly editable
- Run an approved local command and keep its hidden detailed plan, output, and review together
- Run up to two independent approved plans at the same time
- Change the agent rules safely through checked, reversible versions
- Open a real terminal tied to the selected idea; hiding the panel does not stop the process
- Review whether a run followed the plan, whether the result is trustworthy, and what to do next

Delta Loop stores its own history in `.delta-loop-data/`, which is ignored by Git. It does not rewrite
`STATE.md`, `INFRA.md`, or the upstream harness. It generates two small files inside the research project:

- `.delta-loop/LOOP.md` explains how the agent combines the upstream loop with Delta Loop's added behavior.
- `.delta-loop/POLICY.md` contains the researcher's active project and idea-specific choices.

An agent started by Delta Loop receives both files and the exact upstream supervisor path before doing research.
The official harness source is [user074/delta-research](https://github.com/user074/delta-research). Delta Loop
prefers a `delta-research/` checkout inside the research project, then `DELTA_RESEARCH_HOME`, then a neighboring
development checkout.

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

An agent working in the embedded terminal can read the selected research context and update the same policy shown
in the UI:

```bash
delta context
delta policy show
delta policy set --kind quick-test --guidance "Run the matched comparison first."
delta question set "Updated research question" --reason "The recent result narrowed the scope."
delta map show
delta map add-idea "A possible explanation" --summary "Why it may matter"
delta map add-test "Smallest useful test" --under IDEA_ID
delta map update NODE_ID --status dormant
delta rules show
delta rules sync
delta rules add "Use GPU 0" --category temporary --when "Running this batch" --expires "When the batch finishes" --instruction "Use GPU 0 only."
delta rules update RULE_ID --off
delta rules apply UPDATED_RULES.json
delta harness show
delta harness update
```

`delta harness update` fetches the official repository and performs only a fast-forward update. It refuses to
overwrite tracked local changes or update a checkout that points at a different Git remote. Delta Loop's added
behavior remains in Delta Loop, so the base checkout can stay clean and update normally.

The discussion buttons start Codex by default. Its command sandbox allows local connections so it can reach
Delta Loop at `127.0.0.1`, while other internet destinations remain blocked. Set `DELTA_LOOP_AGENT_COMMAND`
before starting Delta Loop to use another interactive agent command.

## Validate

```bash
pytest
npm --prefix web run build
```

The product direction and POC acceptance criteria live in [`docs/POC_PLAN.md`](docs/POC_PLAN.md).
