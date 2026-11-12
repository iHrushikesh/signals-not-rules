# Signals, Not Rules

Code, agent and results behind the paper *Signals, Not Rules* (docs/paper_draft.md), written for the paper track of Google DeepMind's Gemma 4 Developer Agent competition on Kaggle. The agent is a four-role Google ADK pipeline (localizer, coder, verifier, finalizer) that runs one Gemma 4 31B model offline on hidden Python bug-fix tasks under a fixed time budget. The paper asks which controls on such an agent's behaviour actually bind. It reports 93 task runs: nine builds (the paper's "configurations") on an original set of eight development tasks, then the final build on all 21 validated tuning tasks.

## Layout

| Path | What |
|---|---|
| `docs/paper_draft.md` | The paper |
| `docs/agent_design.md` | Design document; sections 11.x log each probe and build |
| `PLAN.md` | The working plan: pre-registered decision rules with their dates, the study design, and the log of what was submitted and why |
| `agent/` | Build 11 of the submission: `agent.yaml`, sub-agent configs, prompts, and the `verify-fix` skill (standard library only) |
| `results/probe8-<n>/`, `results/probe8m-1/`, `results/probe13m-1/` | One folder per probe run: per-task table (`probe_tasks.csv`), per-role timings (`probe_agents.csv`), agent patches (`predictions.csv`), version banner, and a snapshot of the agent build that ran. Folder-to-build mapping below |
| `results/trace_metrics.csv` | Counts derived from the execution traces, one row per run, task and role: calls, distinct calls, identical-call runs, malformed calls by tool, failed edits, budget-warning position, git reverts, history resets. Task ids and integers only |
| `results/gold-1/` | Gold-patch validation of the 129 development tasks: reference fix and no fix, per task |
| `splits/` | Task-id lists: the pre-registered dev split, the measurable tasks, the two probe sets |
| `analysis/` | Standard-library statistics, the split, `trace_metrics.py` (traces to `trace_metrics.csv`, and a report of every trace-derived number in the paper), the power simulation cited in the paper's limitations, unit tests |
| `notebook_cells/` | Cells for the Kaggle probe and gold-validation notebooks (the notebooks derive from the competition's starter and are not included) |
| `scripts/build_submission.py` | Compiles `agent/` with the competition compiler into `dist/submission.zip` |
| `tests/` | Tests for the skill scripts, run through ADK's own script wrapper |
| `data/` | Competition files; not included (see `data/README.md`) |

Builds are identified by the first eight hex digits of the SHA-256 over the files in the submission zip; `results/<run>/probe8/version.txt` records which build each probe ran. Folders `probe8-1` to `probe8-4` predate that banner, and `PLAN.md` (items 8 to 11 under Next actions) logs which build each ran.

| Folder | Build (paper's configuration) | Task set |
|---|---|---|
| `probe8-1`, `probe8-2`, `probe8-3`, `probe8-4` | 2, 3, 4, 5 | Original eight |
| `probe8-6`, `probe8-7`, `probe8-8`, `probe8-10`, `probe8-11` | 6, 7, 8, 10, 11 (no `probe8-5`; build 9 was never probed) | Original eight |
| `probe8m-1` | 11 | Eight validated tuning tasks |
| `probe13m-1` | 11 | The other 13 validated tuning tasks |

## What is not included, and how the paper's numbers can be checked

The competition rules forbid redistributing its data, so the execution traces, the hidden tests' output, the task statements and the repository snapshots are not here. Traces and test output contain task text.

- **From committed tables.** Table 1 except its repetition column, the validation counts in Section 5.1, the 8 of 21 result and the first two rows of Table 3, time shares, and cap hits come from `results/*/probe8/*.csv`, `results/gold-1/` and `splits/`.
- **From the trace metrics.** Every other count in Sections 2 to 4 (repetition, malformed calls, budget warnings, sampling effects, verifier reverts, history resets) is printed, with its section, by `analysis/trace_metrics.py report`, which reads only `trace_metrics.csv` and the committed tables. `extract` rebuilds the CSV from traces.
- **Trace-only details.** A few single observations quote traces or test output directly and cannot be checked here. These are the 371-character verifier command, the seconds remaining in `rich_3470`, the exact assertion messages in Section 5.2, and the content of individual tool calls. The tests quoted in Section 5.2 are in the upstream rich and fastapi repositories at the task commits.

## Commands

```bash
uv sync                                                                  # Python 3.12 environment from uv.lock
uv run python -m unittest discover -s . -p "test_*.py" -v               # all tests
uv run --with pytest python -m unittest tests.test_verify_fix_skill -v   # skill script tests (two need pytest)
uv run --with numpy python analysis/power_simulation.py                  # power simulation from the limitations section
uv run python -m analysis.trace_metrics report                           # every trace-derived number in the paper
uv run python -m analysis.trace_metrics extract                          # rebuild trace_metrics.csv (needs the traces)
```

Building the submission zip needs the competition's `adk_submission` wheel, distributed with the competition data.
