# Signals, Not Rules

Code, agent and results behind the paper *Signals, Not Rules* (docs/paper_draft.md), written for the paper track of Google DeepMind's Gemma 4 Developer Agent competition on Kaggle. The agent is a four-role Google ADK pipeline (localizer, coder, verifier, finalizer) that runs one Gemma 4 31B model offline on hidden Python bug-fix tasks under a fixed time budget. The paper asks which controls on such an agent's behaviour actually bind, and reports eleven builds probed on development tasks.

## Layout

| Path | What |
|---|---|
| `docs/paper_draft.md` | The paper |
| `docs/agent_design.md` | Design document; sections 11.x log each probe and build |
| `PLAN.md` | The working plan: pre-registered decision rules with their dates, the study design, and the log of what was submitted and why |
| `agent/` | Build 11 of the submission: `agent.yaml`, sub-agent configs, prompts, and the `verify-fix` skill (standard library only) |
| `results/probe8-<n>/`, `results/probe8m-<n>/` | One folder per probe run: per-task table, agent patches, version banner, and a snapshot of the agent build that ran. Traces and test output are not included |
| `results/gold-1/` | Gold-patch validation of the 129 development tasks: reference fix and no fix, per task |
| `splits/` | Task-id lists: the pre-registered dev split, the measurable tasks, the two probe sets |
| `analysis/` | Standard-library statistics, the split, the power simulation cited in the paper's limitations, unit tests |
| `notebook_cells/` | Cells for the Kaggle probe and gold-validation notebooks (the notebooks derive from the competition's starter and are not included) |
| `scripts/build_submission.py` | Compiles `agent/` with the competition compiler into `dist/submission.zip` |
| `tests/` | Tests for the skill scripts, run through ADK's own script wrapper |
| `data/` | Competition files; not included (see `data/README.md`) |

Builds are identified by the first eight hex digits of the SHA-256 over the files in the submission zip; `results/<run>/probe8/version.txt` records which build each probe ran.

## Commands

```bash
uv sync                                                                  # Python 3.12 environment from uv.lock
uv run python -m unittest discover -s . -p "test_*.py" -v               # all tests
uv run --with pytest python -m unittest tests.test_verify_fix_skill -v   # skill script tests (two need pytest)
uv run --with numpy python analysis/power_simulation.py                  # power simulation from the limitations section
```

Building the submission zip needs the competition's `adk_submission` wheel, distributed with the competition data.
