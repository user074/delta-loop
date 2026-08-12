# Delta Loop

Delta Loop imports the useful scientific cycle from `delta-research` and makes that cycle visible, editable, and
versioned. It adds a visual idea map, persistent agent supervision, bounded handoffs, and clearer result review
without replacing the terminal.

## What the POC can do

- Open an existing research project on this computer or an SSH server; import its `STATE.md` when present, or let Codex set it up when no state exists
- Start with the real `user074/delta-research` cycle as an editable default and record its source revision
- Show the editable main question and keep its earlier wording when the question changes
- Present the latest result and review as a compact research-update slide
- Map every test and result back to the idea it examined
- Discuss the research map with an agent that can add, clarify, move, or park ideas and ways to test them
- Show which ideas worked, failed, remain uncertain, or have not been tested
- Start, reopen, or continue one persistent research-supervisor session from the Home page
- Keep detailed agent plans underneath while showing only the method, data, and question to the researcher
- Review the loop as main stages, child steps, or exact details; code, data, hardware, file, and Git instructions appear inside the steps that use them
- See whether an instruction came from `delta-research`, a researcher preference, or a local lab rule
- Set shared checks, temporary limits, and special rules for particular ideas
- Start a focused agent chat from configuration that needs discussion; simple choices stay directly editable
- Run an approved local command and keep its hidden detailed plan, output, and review together
- Choose whether research commands run locally or on one remote server through the user's existing SSH setup
- Check the remote project, Python, Git, and GPUs without starting research work
- Keep remote jobs running when the browser closes, reconnect to their status and recent logs, and show exactly where large output remains
- Limit how many independent approved plans may run at the same time
- Change the agent rules safely through checked, reversible versions
- Open a real terminal tied to the selected idea; hiding the panel does not stop the process
- Review whether a run followed the plan, whether the result is trustworthy, and what to do next

Delta Loop stores its own history in `.delta-loop-data/`, which is ignored by Git. For a local project it generates
two files inside the research project. For a remote project it keeps these files in a small local notes folder, so
the repository on the server is not changed during setup:

- `.delta-loop/LOOP.md` is the complete active research loop used by the agent.
- `.delta-loop/POLICY.md` contains the researcher's active project and idea-specific choices.

An agent started by Delta Loop receives both files before doing research. It does not read or combine another
supervisor prompt at runtime. Its built-in research cycle was adapted from
[user074/delta-research](https://github.com/user074/delta-research), but Delta Loop owns and runs the editable
policy. A local checkout is optional and used only when explicitly comparing upstream changes.

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
delta project inspect-remote --host lab-gpu --project ~/projects/my-research
delta project finish-setup --summary "Short project summary" --reference /path/to/reference --constraint "Do not change the evaluation dataset"
delta compute show
delta compute inspect --local
delta compute inspect --host lab-gpu --project ~/projects/my-research
delta compute set --kind ssh --name "Lab GPU server" --host lab-gpu --project ~/projects/my-research --runs ~/.delta-loop/runs --setup "source .venv/bin/activate" --gpus 0 --max-parallel 1
delta compute check
delta compute reset
delta work start --approach APPROACH_ID --title "Small comparison" --goal "Test the smallest useful difference" --steps "Run the matched comparison once" --measure "Difference in the primary metric" --command "python experiments/quick_test.py --output {output_dir}"
delta work show
delta work cancel RUN_ID
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

## Run research work on a remote server

Delta Loop itself stays on your computer. Its web page, terminal, research map, and policy files remain local. The
Compute page can send only approved research runs to one server over SSH. It uses the same host or alias that works
with `ssh HOST` in your terminal, so Delta Loop never stores SSH passwords or private keys.

On a clean start, choose **Remote server**. Delta Loop creates an empty local notes folder and opens Codex. Give
Codex the SSH host or alias and the existing project folder on the server. Codex makes one bounded read-only pass
over the project and one bounded server check, explains what it found, and asks for the research and server choices
it cannot infer. Nothing is installed or run during this conversation. After you approve the proposal, Codex saves
the remote connection, checks the exact environment, creates the initial local research state, and leaves the remote
repository unchanged.

For each remote run, Delta Loop copies the sealed plan to the configured run-record folder, starts the command as a
background process, and reads its status and recent log over SSH. The job continues if the browser or Delta Loop is
closed. Large artifacts remain in the remote output folder shown on the Compute page; Delta Loop does not copy them
back automatically.

The **Set up with Codex** panel first asks whether work should run on this computer or a remote server, so the agent
starts with the right setup process. The local path inspects the current project and machine. The remote path asks
for an SSH host and project folder before connecting.

Use **Reset setup** on the Compute page, or `delta compute reset`, to clear the saved location and its inspection.
This does not delete run history, output, policy rules, or research files. A new local or remote choice is required
before another run can start.

The remote project and its Python environment should already exist. Codex runs one bounded, read-only
`delta project inspect-remote` and one `delta compute inspect`. Those checks report objective facts such as the
project documentation and Git state, environment candidates, visible GPUs, scheduler, storage, and an existing `INFRA.md`. Codex then asks the
researcher about choices the server cannot reveal: the approved environment, storage policy, GPU and concurrency
limits, login-node restrictions, and lab conventions. It saves compute settings and policy rules only after explicit
confirmation, then proves that the exact environment setup resolves Python with `delta compute check`.

Manual fields remain available as a collapsed fallback for researchers who already know the exact configuration.
Inspection and connection checks do not install software, clone code, move data, change Git, or start research work.

`delta harness update` updates the optional source checkout for comparison. It refuses to overwrite tracked local
changes or update a checkout that points at a different Git remote. It does not silently replace the active loop;
that loop remains a checked, reversible Delta Loop policy version.

The discussion buttons start Codex by default. Its command sandbox allows local connections so it can reach
Delta Loop at `127.0.0.1`, while other internet destinations remain blocked. Set `DELTA_LOOP_AGENT_COMMAND`
before starting Delta Loop to use another interactive agent command.

## Validate

```bash
pytest
npm --prefix web run build
```

The product direction and POC acceptance criteria live in [`docs/POC_PLAN.md`](docs/POC_PLAN.md).
