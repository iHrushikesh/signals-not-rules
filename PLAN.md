# Gemma 4 Developer Agent: project plan

Last updated: 2026-11-11 late (Pacific). Status: first scaffold submitted. Both competitions joined; harness guide read; dev split frozen; S0 anchor scored 0.03 public; first S2 pipeline (12B, loop cap 3, 5-minute task cap) scored 0.03 public on Nov 10, equal to the anchor; the time model in the Nov 10 refinement step predicted this (thinking budgets alone exceed the cap).

**Sourcing rule (set Oct 23):** this plan rests only on organizer material (competition pages, `HARNESS_README.md`, the starter notebook, the data files), our own measurements, and arithmetic. We do not read other participants' leaderboard notebooks or repos. Papers from the paper track are allowed once they are public. Claims that came from participants earlier are quarantined in "Outside reports (unverified)" near the end and are not used for any decision.

## Goal

- **Main track:** an offline coding agent (Gemma 4 plus an ADK agent config) scored on the private half of about 120 hidden Python bug-fix tasks. Final submission Dec 2.
- **Paper track:** a writeup of at most 3,000 words, due Nov 12. Judged on novelty, quality (generality beyond the competition), relevance, verifiability and clarity.
- **Research question:** under the fixed 12-hour budget on the scoring hardware (4×L4), where should compute go: a larger model, verify-and-retry iterations, or code-graph navigation tools?
- **How the two connect:** every leaderboard change is run as a controlled comparison, so the leaderboard work produces the paper's evidence.

## Deadlines

All deadlines are 23:59 UTC, which is 3:59 PM Pacific after DST ends on Nov 1.

| Date | What |
|---|---|
| Done Oct 22 | Joined both competitions and accepted the rules |
| Sun Nov 8 | Freeze paper results |
| Wed Nov 11 | Submit the paper (one day of buffer) |
| Thu Nov 12 | Paper deadline |
| Wed Nov 25 | Main track entry and team-merger deadline |
| Wed Dec 2 | Final submission; select 2 |

## Schedule

**Week 0 (Fri Oct 23 to Sun Oct 25): setup**
- Rishi: run the official starter notebook unchanged on L4×4 and submit; download `sample_submission/` into `data/`; check Kaggle quota; choose dev compute.
- Claude: done Oct 22: read the harness guide and starter notebook, froze the dev split. Next: scaffold S1, machine setup script, results collector.

**Week 1 (Mon Oct 26 to Sun Nov 1): baselines and scaffolds**
- Reproduce the official baseline on GCP 4×L4 and compare per-task timing with the Kaggle run (hardware calibration).
- Baseline S0 for 31B, 12B and E4B on the tuning split.
- Build S1 and S2 (below) and iterate on the tuning split only.

**Week 2 (Mon Nov 2 to Sun Nov 8): main experiments**
- Main grid on the held-out split, graph-tool ablation, cap validation, repeats.
- One Kaggle submission per day of the strongest configs, as a packaging and time-budget check. The public score is a noisy sanity check, not a selection signal.
- Freeze results Nov 8.

**Week 3 (Mon Nov 9 to Thu Nov 12): paper**
- Draft, figures, related work, limitations. Submit Nov 11.

**Weeks 4 to 6 (Fri Nov 13 to Wed Dec 2): leaderboard push**
- Tune the per-task cap and retry policy on held-out evidence.
- Fine-tuning (LoRA on rejection-sampled, test-passing trajectories) only if a held-out comparison shows a gain.
- An E4B entry for the small-model bonus, if it is competitive (confirm the bonus and its terms on the Rules tab).
- Final selection of 2 submissions on Dec 2.

## What the harness established (Oct 22)

From `data/HARNESS_README.md` and the starter notebook unless marked otherwise.

- **Per-task budgets live in `eval_config.yaml`:** `max_time_minutes`, `max_tool_calls`, `max_turns`, `timeout_seconds`. The sample submission sets 1 minute, 10 tool calls and 50 turns, and the starter notebook packages it unchanged. Our unchanged S0 submission scored 0.03 public (Oct 23). Whether the caps explain that is untested; the first config experiment isolates it.
- **Time accounting:** sandbox setup is outside the per-task agent clock but inside the 12 hours. Phase 2 verification is outside both.
- **Time budget:** the 12-hour total is official. Arithmetic: 12 h over about 120 tasks is 6 minutes per task including sandbox setup and model startup, so the working assumption until we measure is an average under about 5 minutes. What happens if the total is exceeded, and whether tasks run one at a time, are not confirmed by an organizer source; check the Rules tab and our own timing.
- **Context:** 32,768 tokens for prompt plus output. Compaction starts at 14,336 tokens for the main agent. Prompt plus output must fit in that window, and the default `max_output_tokens` is 16,384, so as a precaution we set it to 8,192 or less and count context-overflow errors in every run.
- **Patches:** edits to test files and test-runner config are stripped. Untracked files in `/workspace` are included, so scratch scripts belong in `/tmp`.
- **Sandbox:** Kaggle runs the harness's subprocess sandbox, so dev machines don't need Docker.
- **Graph data (Kaggle file listing):** graph and embedding files are per commit, and `swegemma.graph.get_graph` takes `base_commit`, even though the harness guide shows `data/graphs/<repo>.json`. Whether they exist for the hidden repos is not stated.
- **Scoring:** a task resolves only if pytest exits 0 and every required test passed (none skipped).
- **Off-Kaggle runs need three downloads:** the harness and vLLM wheelhouse (`metric/gemma-4-developer-agent-wheelhouse` dataset), the model weights (Kaggle Models `google/gemma-4`), and the competition data (about 22 GB).

**Dev set:** 129 tasks: fastapi 67, rich 48, requests 13, httpx 1. No task has hints. The median problem statement is 418 characters. 71% of reference fixes touch one file, and the median fix changes 12 lines. Gemma 4's pre-training data has a January 2025 cutoff (model card), so only the 31 tasks dated before 2025 could have been memorized; the other 98 are dated later. `created_at` is documented as the PR creation date, but some old PR numbers (`fastapi_5077`, `fastapi_9555`) carry December 2025 dates, so the field may be a merge or commit date instead. The dev repos are popular public projects, so dev results are probably optimistic relative to private repos: use dev numbers for comparisons, not as forecasts.

## Experimental design

Revised Oct 22 after reading the harness guide and starter notebook. Still provisional until we see the sample submission.

**Factors**
- **Model:** E4B, 12B, 31B (the QAT w4a16 variants the competition allows).
- **Scaffold:**
  - S0: the official sample configuration.
  - S1: a structured single pass (localize, reproduce, patch, run targeted tests, submit), with time checks through `get_status`.
  - S2: S1 plus verify-and-retry until the tests pass or the per-task cap is reached.
- **Graph tools:** on or off (`search_similar_code`, `get_code_neighbors`, `get_code_subgraph`).
- **Per-task cap:** not a separate factor. Each config runs once with a generous cap, and the curves for smaller caps are derived from that run (next section). Real capped runs of the top two configs check the derived numbers.

**Budget analysis (the paper's core method)**
- From each generous-cap run, record every task's time to submit and whether it resolved.
- Resolution at cap c is estimated as the share of tasks resolved within c. This is approximate in both directions: the prompt shows the budget, which can change behavior, and a capped task's partial patch can still pass.
- Scorer time at cap c is vLLM startup plus the sum over about 120 tasks of setup + min(time to submit, c). Resampling tasks gives the chance of going over 12 hours; pick the largest cap that keeps that chance under 1%.
- Hidden tasks are probably harder than dev, so they likely take longer. The conservative case uses the time distribution of unresolved dev tasks.

**Runs** (each is one pass over the 87-task held-out split)

| Block | Configs | Passes |
|---|---|---|
| Baselines | S0 × 3 models | 3 |
| Main grid | {S1, S2} × 3 models, graph tools on | 6 |
| Graph ablation | best 2 configs, graph tools off | 2 |
| Cap validation | best 2 configs at the chosen cap | 2 |
| Repeats | best 2 configs × 2 extra seeds | 4 |
| **Total** | | **17** |

**Data hygiene**
- The 129 dev tasks are split once, stratified by repo (seed 20261023): 42 for tuning prompts and skills, 87 held out for reported comparisons. Frozen Oct 22 in `splits/dev_split.json` (SHA-256 `cb3bcdca…`); commit it before running any comparison. Against Gemma 4's January 2025 pre-training cutoff, 18 held-out and 13 tuning tasks are dated earlier; comparing the 18 held-out pre-cutoff tasks with the 69 later ones is an exploratory contamination check.
- The dev repos (fastapi, rich, requests, httpx) are popular public projects and were probably seen in pretraining. The hidden test set comes from private repos, so dev numbers are optimistic. No prompt or skill may mention those repos specifically.
- The test set has about 120 tasks from private repos, split evenly into public and private leaderboard halves; both halves run in every submission, and the private half decides prizes ([Data tab](https://www.kaggle.com/competitions/gemma-4-developer-agent/data), checked 2026-11-05). It was filtered harder than the dev set: issues "lacking reproducible acceptance criteria" were excluded, and for the test set "a larger frontier model can pass the case or get within a single test case of passing". The page describes the frontier check for the test set only, so the dev set likely holds more tasks no agent can pass (for example, up to 13 fastapi tasks whose tests match message text the description never gives; a rough automatic count, not yet hand-checked).
- Don't choose configurations by public leaderboard score. The public split has about 60 tasks, so a Wilson 95% interval is roughly ±10 points at a 20% solve rate, and one task is about 1.7 points.

**Metrics**
- **Primary:** resolution rate (the task's tests pass after the patch).
- **Secondary:** file-level localization recall and precision against the reference patch, which gives more signal per task than pass/fail; time to submit per task; generated tokens; timeouts; context-overflow errors; empty patches.
- **Statistics:** per-task paired comparisons, exact McNemar test, paired bootstrap 95% CI on the difference, Wilson CI for single rates, Holm correction across the pre-registered comparisons, run-to-run variance from repeats (`analysis/stats.py`).

**Pre-registered hypotheses** (to be tested, not assumed)
- **H1:** at the chosen cap, a smaller model with verify-and-retry (S2) resolves at least as many tasks as 31B with a single pass (S1).
- **H2:** verify-and-retry (S2 vs S1) improves resolution at a fixed cap for each model size.
- **H3:** graph tools raise file-level localization recall, and their effect on resolution is smaller.
- **H4:** run-to-run variation alone moves resolution on a 60-task split by more than 5 points.

## Paper outline (at most 3,000 words)

1. **Abstract.**
2. **Introduction:** offline agents on consumer-class hardware; the budget-allocation question; contributions.
3. **Setup:** task, harness, hardware, 12-hour budget, dev split, metrics, statistics.
4. **Agent configurations:** S0 to S2, graph tools, models.
5. **Results:**
   - resolution vs time per task for each model and scaffold;
   - ablations;
   - localization;
   - run-to-run variance and what it implies for the leaderboard.
6. **Related work:** SWE-bench, SWE-agent, Agentless, SWE-Gym, test-time compute scaling.
7. **Limitations and conclusion.** The pre-registered plan and the code back verifiability.

## Compute

- **Kaggle:** the official baseline and all submissions.
  - Weekly GPU quota is not published. Users report about 30 hours, and L4×4 counts double, so expect about 15 L4×4 hours a week. Check yours in Settings.
  - Unknown whether submission scoring counts against it.
- **GCP `g2-standard-48`** (4×L4, the same as the scoring hardware) for dev runs.
  - Spot is about $2.13 to $2.39 per hour in us-east4, us-central1 and us-west1. On-demand is about $3.99 to $4.00.
  - Source: a third-party price tracker updated Oct 18, 2026. Confirm in the GCP console.
- **RunPod is also an option:** scoring uses the subprocess sandbox, so Docker isn't required. At RunPod's listed $0.59 per L4-hour, four L4s cost about $2.36/h on-demand, with no quota request and no preemption. Not yet checked: whether one pod can have four L4s.
- **Cost envelope** (time per task is the main unknown; generous-cap runs will average more than the final cap):

| Average per task | One held-out pass | 17 passes on GCP spot |
|---|---|---|
| 3 min | 4.3 h | $157 to $177 |
| 5 min | 7.2 h | $262 to $295 |
| 7 min | 10.2 h | $367 to $413 |

  Tuning passes on 42 tasks cost about half as much each. Running several tasks at once on one machine and converting generated tokens to scorer time would cut machine-hours several-fold; it needs one throughput calibration per model and a sequential run to check it.

## How we work

- **Repo:** this folder (`~/workspaces/kaggle/gemma`, a uv project), later pushed to a private GitHub repo holding code only. Competition data stays in the gitignored `data/` folder and is never committed (rule 2.4 forbids redistributing it). If we win, the code must be released under an OSI license.
- **Loop:** Claude writes configs, prompts, skills, runners and analysis directly into this folder. Rishi runs them on GCP or Kaggle and puts the results CSV and traces under `results/`. Claude reads them there, analyzes them and updates this plan.

**Results CSV format** (one row per task attempt):

```
config,run,instance_id,resolved,wall_seconds
s1-12b-g1-cap6,r1,fastapi_11194,1,212.4
```

## Rules that can silently kill an entry

- Scoring is offline: no pip installs or downloads at scoring time, and the agent cannot open issue links in a problem statement. The competition Overview ("Upgraded Accelerators") says "All L4 sessions must have internet disabled", and scoring runs on those L4×4 sessions ([Overview](https://www.kaggle.com/competitions/gemma-4-developer-agent/overview), checked 2026-11-05). This holds for either sandbox backend: Docker adds `network_mode="none"`, while `subprocess` has no network isolation of its own.
- No `../` paths or symlinks in the zip; the zip is at most 3 GiB; `agent.yaml` sits at the root.
- One base model per submission. Different LoRA adapters per agent are fine.
- No private sharing of code or data outside the team.
- 12-hour total budget: set per-task caps in `eval_config.yaml`.

## Risks

| Risk | Mitigation |
|---|---|
| GCP GPU quota approval is slow | Use RunPod, or fall back to a Kaggle-only design with fewer configs |
| Spot preemption | The runner resumes and skips finished tasks |
| Dev-machine timing differs from Kaggle | Run the same tasks in both places and calibrate |
| Exceeding the 12 hours (consequence unconfirmed) | Pick the cap by resampled overrun risk; keep an hour of margin |
| Context overflow (effect on the patch unconfirmed) | `max_output_tokens` at 8,192 or less; check overflow counts in every run |
| Dev set far easier than hidden set | Treat dev results as comparisons; analyze unresolved and post-release tasks separately |
| Overfitting to the dev repos | Tune on 42 tasks, report on 87; no repo-specific content |
| Fine-tuning hurts | Only after Nov 12, and only with a held-out gain |
| Paper deadline precedes the final | Freeze results Nov 8 |

## Fast feedback loop

**Status (Nov 6):** no code yet; build it only on an explicit request. Step 1 is partly done (downloads for one task, harness wheels). Backend decision: Ollama only. `vllm-metal` and a rented NVIDIA GPU were compared and not chosen.

### Context

A full Kaggle submission covers about 120 tasks. Each E02 change also means pasting notebook cells and sending logs back. That is too slow with paper results freezing on Nov 8.

The goal is to test agent changes on this Mac in seconds to minutes, using the real harness and a local Gemma 4 12B in place of vLLM. Decisions already made: target 12B first, stay local only (nothing goes to a hosted API), and calibrate against both E02 Kaggle runs, whose logs are available.

Build time is capped at one day. Time spent here comes out of the main experiments.

### Approach

Run the **unmodified** `swegemma` harness in a Linux container and point it at Ollama on the Mac. The notebook passes a `models=` registry into `EvalConfig`, so the endpoint should be swappable without patching the harness. This is unconfirmed until the wheel is inspected in step 2.

| Level | Question it answers | Speed | Model |
|---|---|---|---|
| L0 check | Will this submission compile and package correctly? | Seconds | None |
| L1 fake model | What does the harness do in edge cases? | Seconds per scenario | Scripted responses |
| L2 live | Does this change alter agent behavior? | Unknown; rough guess 3 to 5 min per task, measured in step 2 | 12B on Ollama |
| Real vLLM | Timing and all reported results | Slow | QAT 12B, 31B, E4B on L4 |

The main speed gain is testing one task instead of a whole run, not a faster model. L2 per-task speed may not beat the L4s, and that is fine.

**What the loop can test.** Agent design without LoRA (prompts, skills, sub-agents, which tools to declare, budgets) is what L2 is for. LoRA is outside it for now: training is a separate GPU pipeline, and serving a Gemma 4 adapter through Ollama is unverified (see Known differences). Until a spike shows Ollama can load one, LoRA comparisons run on real vLLM.

### Steps

#### 1. Prepare (needs your go-ahead on the system items)
- Add `.DS_Store` to `.gitignore`.
- Download into the gitignored `data/` folder: the three first-party wheels (`swegemma`, `adk_submission`, `adk_eval_core`), `docker/`, `sandbox/setup.py`, `wheels/`, and the graphs, embeddings and snapshots for tuning tasks only. Measured from Kaggle's file listing: 7.35 GB for all 42 tuning tasks (snapshots 7.03 GB, graphs 0.14 GB, embeddings 0.16 GB, `wheels/` 28 MB). Held-out snapshots are deliberately left out.
  - Done Nov 6: the three harness wheels, in `data/harness_wheels/` (pure Python `py3-none-any`, so they install on the Mac too), and the snapshot, graph and embeddings for `fastapi_11194`. All sizes match Kaggle's listing to the byte.
  - Naming: snapshots are per task (`snapshots/<instance_id>.tgz`, 129 files). Graphs and embeddings are per repo and commit (`graphs/<repo_short>_<base_commit>.json`, 127 files, because two task pairs share a commit). The task-named copies the Data tab mentions return 404.
  - Use `-p data` for competition files: the CLI keeps the folder in the file name, so `-p data/snapshots` creates `data/snapshots/snapshots/`.
- `ollama pull gemma4:12b-it-qat` (7.2 GB). Not pulled yet; Ollama is now 0.40.15.
- Serve with `OLLAMA_CONTEXT_LENGTH=32768`. The default measured on this Mac is 4,096, which would badly distort results. Confirm with `/api/ps`.
- Start Docker Desktop (Docker 29.9.2 is installed; the Mac is arm64).

#### 2. Spike: one task end to end (half a day at most)
- Build a `linux/amd64` Python 3.12 image starting from the competition's `docker/Dockerfile.public`. This matches the `cp312` Linux wheels and keeps harness installs out of the project's own env (also 3.12 since Nov 5).
- Read the wheel metadata, then install the three wheels plus dependencies pinned to the wheelhouse versions. Skip vLLM and torch if the imports allow it.
- Read the tool code first: `swegemma/tools/execution.py` (`run_command`, `submit_patch`), `swegemma/tools/workspace.py` (file tools), `swegemma/tools/graph.py` (the three graph tools), and the sandbox backends in `adk_eval_core/sandbox/`.
- Register alias `gemma-4-12b-it-qat-w4a16-ct` as `LiteLlm(model="openai/gemma4:12b-it-qat", api_base="http://host.docker.internal:11434/v1", api_key="EMPTY", num_retries=3)`, the fallback shape described in README section 3.3. `agent.yaml` stays unchanged.
- Run a sandbox-only check, then one real tuning task through Phase 1 and Phase 2.
- Measure 12B generation speed, prompt processing speed and seconds per task.

If amd64 emulation is too slow or needs Rosetta installed (a system change, so I will ask first), fall back to an `arm64` container with a copy of `wheels/` that swaps in aarch64 builds of the four binary packages: `pydantic_core`, `sqlalchemy`, `markupsafe`, `charset_normalizer`. Confirmed from the listing: these are the only platform-specific wheels in `wheels/`, 8 files (a `cp312` and a `cp313` build of each, all `manylinux` x86_64), so a native subprocess sandbox on the Mac cannot install fastapi's dependencies.

**Stop rule:** if one task can't finish end to end by the end of the spike, stop. Do not patch or rewrite the harness. Move to a rented GPU running real vLLM instead.

#### 3. L2 runner: `sim/run.py`
- Derive it from notebook cells 4, 8 and 10, with the same `EvalConfig` values, including compaction and context cache settings, and replace `VllmServer` with the Ollama registry.
- Pass `snapshots_dir`, `graph_dir`, `embeddings_dir` and `wheels_dir` pointing into `data/`, as the notebook does with `/kaggle/input/...`. Prefer this Python route to the `swegemma eval` CLI: the CLI documents no graph flag, and the README's `data/graphs/<repo>.json` path is out of date.
- Arguments: submission dir, task IDs or a named set such as `e02`, run name.
- Refuse any task ID not in `tune` from `splits/dev_split.json`.
- Skip finished tasks so runs can resume.
- Write the standard `results/<run>/` layout.

#### 4. Fidelity gate (pre-registered here, before any local run)
Put the Kaggle E02 logs in `results/e02-kaggle/`. Run the same 12 E02 tasks locally with both prompts and the same limits.

The time limit needs adjusting because the two machines run at different speeds. Scale `max_time_minutes` by the measured speed ratio, and record which budget ended each task.

Trust L2 for prompt work only if all of these hold:
- Sample vs revised moves in the same direction as Kaggle on E02's decision metrics: non-empty source patches, test-file edits, failed edit calls.
- Non-empty patch count for each variant is within 2 of Kaggle's, out of 12.
- Median generated tokens per task is between 0.5× and 2× Kaggle's. If the Kaggle logs lack token counts, this check is skipped and noted.
- No run shows context truncation.

With 12 tasks this is a coarse sanity check and cannot prove equivalence. If it fails, keep L0 and L1, use L2 only for crash testing, and tune on real vLLM.

#### 5. Trace metrics: `analysis/traces.py`
- Move `_e02_trace_metrics`, `_e02_is_test_path` and `_e02_diff_files` out of `notebook_cells/e02_prompt_probe.py` Cell C and add unit tests.
- Add token totals and the reason each session ended.
- Add a collector that writes the results CSV format from "How we work". Keep it stdlib only, like the rest of `analysis/`.

#### 6. L0 check: `sim/check.py`
Use the real `compile_submission`, `discover_declared_models` and `build_submission_limits`, then add these repo rules:
- `agent.yaml` at the zip root
- `eval_config.yaml` present
- `max_output_tokens` at 8,192 or less
- No `{...}` placeholders unless intended
- No dev repo names in prompts or skills
- Per-task time cap × 120 under 11 hours

#### 7. L1 fake model: `sim/fake_llm.py`
A small OpenAI-compatible server that plays scripted responses through the real harness. It tests claims this plan lists as unverified, using our own measurements:
- Context overflow error before and after `submit_patch`: is the patch kept?
- Time budget ending with edits on disk
- Tool call cut off at the token limit, and the nudge sequence

It cannot settle what happens if the 12-hour total is exceeded. That needs Kaggle.

#### 8. Update docs
Add commands to `CLAUDE.md` and record the gate result in this section.

### Not building now
A one-turn probe that replays a saved trace and re-samples only the next decision would be the fastest signal for prompt wording. Add it only if L2 turns out to be the bottleneck.

### Known differences from scoring

| Area | Scoring | Local loop | Handling |
|---|---|---|---|
| Weights | QAT w4a16 compressed-tensors | Ollama `12b-it-qat` | Close but not identical; the gate tests this |
| Parsing | vLLM `gemma4` parsers | Ollama's own | Spike checks tool calls and reasoning through LiteLLM |
| Thinking budget | Token budget enforced in vLLM | Ollama offers on/off only, as far as I know | Track thinking tokens; expect longer thoughts |
| Context limit | 32,768, overflow behavior unconfirmed | Set to 32,768; overflow behavior undocumented | Flag runs near the limit |
| Speed | 4×L4 | M5 Pro | Treat tokens and tool calls as portable; never report local times |
| LoRA adapters | vLLM serves PEFT adapters, a different one per agent if wanted | Ollama's adapter docs list Gemma 1 and 2 only, and require the adapter's exact base model | Unverified for Gemma 4; LoRA comparisons stay on real vLLM unless a spike proves otherwise |

### Guardrails
- Tuning split only, enforced by the runner. The 12 E02 tasks are already used, which leaves 30 unused tuning tasks. Eight of those 30 are fixed as the quick-experiment subset in `splits/probe_subset.json` (chosen Nov 10 to match all 129 dev tasks on repo mix, patch size, hunks, problem length and multi-file share), which leaves 22 untouched. `notebook_cells/probe8_run.ipynb` (built Nov 10 from the starter notebook) runs the uploaded agent on these eight tasks and reports per-task and per-agent timing, generation speed and how many tasks reached the cap; the task rows are also in `data/probe8_tasks.jsonl`. Only a clone of the official notebook gets L4 x4, so the same cells are in `notebook_cells/probe8_cells.py` for pasting into a clone. First Kaggle attempt (Nov 11) ran no agent: all 8 tasks failed in seconds at `App(...)` with a pydantic `model_type` error on `events_compaction_config`, while `context_cache_config` passed. That means the class imported from `google.adk.apps._configs` was not the class `App` validates against in that session, which does not happen on the local 1.36.1 install. Open question: the ADK version actually installed on Kaggle. Importing the class from `google.adk.apps.app` failed the same way, and the error does not reproduce locally on ADK 1.36.1 with pydantic 2.12.0, 2.12.5 or 2.14.3, so the cause is still unknown. The run cell now passes a plain dict (which `App` validates into its own class) and prints diagnostics on the ADK version and class identity; record them here after the next run.
- Local results never go into the paper. All reported numbers stay on real vLLM.
- No competition data goes to any hosted API. Check rule 2.4 before revisiting that.
- No edits to harness wheels.

### Verification
- `uv run python -m unittest discover -s . -p "test_*.py" -v` passes, including the new trace tests.
- L0 passes on `sample_submission/` and rejects a deliberately broken copy.
- Each L1 scenario gives a repeatable result, recorded in this section.
- One L2 task produces `summary.json`, `task_results.jsonl`, `patches/`, `traces/` and a Phase 2 verdict. `/api/ps` shows a context length of 32768.
- The fidelity gate is run and its outcome recorded, pass or fail.

### Critical files
- New: `sim/Dockerfile`, `sim/run.py`, `sim/check.py`, `sim/fake_llm.py`, `analysis/traces.py`
- Changed: `.gitignore`, `analysis/test_analysis.py`, `CLAUDE.md`, `PLAN.md`
- Reused: notebook cells 4, 8 and 10; `notebook_cells/e02_prompt_probe.py` Cell C; `splits/dev_split.json`; `agent/prompts/system.md`; `analysis/stats.py`

## Next actions

**Rishi (next)**
1. Done: `sample_submission/` is in `data/sample_submission/`.
2. Done Oct 23: the unchanged official notebook scored 0.03 public (the S0 anchor, 12B model with the sample's 1-minute caps). Still useful: whatever the notebook printed for its two local tasks (time per task) and anything the submission page shows about runtime.
3. Check your Kaggle GPU quota in Settings.
4. Choose dev compute: RunPod (no quota wait) or GCP (request L4 quota of at least 4 in one US region, plus Spot quota if listed). Don't start anything yet.
5. Done Nov 10: submitted the first `agent/` pipeline (S2: 12B, no LoRA, loop cap 3, 5 minutes, 80 tool calls, 150 turns) from the starter notebook with section 5 removed and section 6 building its own limits. Scored 0.03 public (Nov 10), equal to the anchor. Reading the score: the public half is about 60 tasks, so one task is about 0.017, and the anchor's 2 of 60 has a 95 percent Wilson interval of 0.009 to 0.114 (`analysis/stats.py`). A score under about 0.11 is not distinguishable from the anchor on the public half alone. Run time was 13 hours, so nearly every task ran to the 5-minute cap. The Nov 10 lean config (docs/agent_design.md section 11.2) cuts thinking and tool calls to fit.

6. Done Nov 10: second submission sent (build 2: 31B, lean config, 6-minute cap). **Scored 0.12 public (reported Nov 11).** The run time was not captured, so it gives no evidence on whether a run over 12 hours is punished. Reading the score: about 7 of the roughly 60 public tasks, 95 percent Wilson interval 0.058 to 0.222, against the anchor's 2 of 60 (0.009 to 0.114). It is just above the 0.11 line set in item 5, so it is the first score that the public half can tell apart from the anchor, though only barely. For the next submission, note the start time and read the run time from the notebook version's log.
7. In progress Nov 11: probe run of that same build on the eight-task subset, in a clone of the official notebook. Provisional findings from the live console (tables and traces pending; details in `docs/agent_design.md` section 11.3): a tool call takes about 3 seconds, so the 80-call cap bound before the 6-minute cap; the verifier's submit-and-exit path works; two of the first six tasks were lost to an agent repeating one identical tool call dozens of times; in one of them the localizer used the whole shared tool budget and the coder could not edit; in a third task 79 calls went by without an edit (the traces show 71 were the localizer's, not the coder's); no agent followed the call limits written in its prompt.
8. Done Nov 11: probe finished on the Nov 10 build (31B, lean config, 6-minute cap, 80 tool calls, 150 turns). Resolved 1 of 8 (`rich_3894`); with n = 8 this is not a solve-rate estimate.

   | Task | Resolved | Task s | Ended by | Localizer calls | Coder calls | Patch chars |
   |---|---|---|---|---|---|---|
   | fastapi_14361 | no | 140 | verifier submit | 6 | 4 | 543 |
   | requests_6589 | no | 210 | verifier submit | 6 | 7 | 438 |
   | rich_3894 | yes | 191 | verifier submit | 4 | 9 | 594 |
   | rich_3718 | no | 247 | verifier submit | 15 | 16 | 493 |
   | rich_3064 | no | 364 | time cap | 56 | 9 | 505 |
   | fastapi_14873 | no | 281 | turn cap (150) | 80 | 69 (all refused) | 0 |
   | fastapi_14962 | no | 362 | time cap | 71 | 8 | 0 |
   | fastapi_14262 | no | 365 | time cap | 60 | 51 | 331 |

   Readings: (a) mean task time 270 s, so about 9 hours of agent time over 120 tasks at this build; (b) generation speed at least 31 tokens per second overall, about 35 for the coder; a localizer call takes about 2.5 s and a coder call about 16 s because the coder thinks; (c) the localizer overran in 4 of 8 tasks (56 to 80 calls against a prompt limit of 6) and none of those four reached the verifier; (d) the verifier passed the fix on its first look in all 4 tasks that reached it, and 3 of those 4 failed the hidden tests, so the retry loop never ran a second round; the traces show 2 of those 3 patches match the reference fix in substance, so their failures are more likely the probe's test environment or the whole-file pass rule (design doc section 11.4); (e) largest prompt 15,647 tokens, inside the 32,768 window. The probe cell's "tasks at the cap" line undercounts (it printed 1; the error column shows 3 time caps and 1 turn cap). The results zip is in `results/probe8-1/`.
9. Done Nov 11: probe of build 3 on the same eight tasks (`results/probe8-2/`, design doc section 11.5). **Outcome: build 3 fails the rule below on (a), (b) and (c) and passes (d). Not submitted; build 2 stays the best build.** (a) five tasks repeat one identical call 30 to 135 times in a row, all in the localizer; (b) 2 of 8 tasks reach the verifier, against 4; (c) 3 of 8 end with a source patch, against 6 (two more patches hold only reproduction scripts the localizer wrote into /workspace); (d) every task ends by submit_patch (2) or the time cap (6). Resolved 1 of 8, as in probe 1. Mean task time 325 s, against 270.
   **Decision rule, written before the build 3 probe results (Nov 11).** Submit build 3 when the window opens if all of these hold against probe 1 (build 2): (a) no task spends more than 10 consecutive tool calls on one identical call; (b) at least as many tasks reach the verifier (probe 1: 4 of 8); (c) at least as many tasks end with a non-empty patch (probe 1: 6 of 8); (d) no task ends from a turn or tool-call cap, only from submit_patch or the time cap. Resolved counts are reported but do not decide, since 8 tasks cannot separate the builds and the probe's test environment differs from the scorer's. If (a) or (d) fails, fix that first and do not submit build 3.
10. Done Nov 11: probe of build 4 on the same eight tasks (`results/probe8-3/`, design doc section 11.6). **Outcome: build 4 fails (a) and passes (b) to (e). Not submitted under the rule.** (a) three tasks repeat one identical grep 39 to 84 times in a row, all in the localizer; (b) 6 of 8 reach the verifier; (c) 6 of 8 patches change a source file; (d) the localizer ran no python and created no files; (e) no turn cap. Resolved 2 of 8 (rich_3894, rich_3718). Mean task time 323 s. Build 2 would also fail (a), and build 4 beats it on (b).
11. Done Nov 11: probe of build 5 (`results/probe8-4/`, design doc section 11.8; run on the old notebook, before the test-dependency fix). **Outcome: build 5 passes (a), (b), (c) and (e) and fails (d). Not submitted under the rule.** (a) longest identical run is 3, against 84 for build 4; (b) 4 of 8 reach the verifier; (c) 6 of 8 patches change a source file; (d) in rich_3894 the localizer wrote and ran a reproduction script 13 times and the file is in the patch; (e) no turn cap. Resolved 2 of 8 (rich_3894, rich_3718). Mean task time 310 s. Malformed calls: localizer 2.4%, coder 6.7%.
   **Decision rule, written before the build 5 probe (Nov 11).** The same five rules as item 10, unchanged: (a) no identical call more than 10 times in a row; (b) at least 4 of 8 reach the verifier; (c) at least 6 of 8 patches change a source file; (d) no localizer-created file in a patch and no python run by the localizer; (e) no turn cap. Submit build 5 if all hold. Reported but not deciding: resolved count; the share of malformed tool calls among the localizer's file and command calls (1.4% in probes 2 and 3 at temperature 0.2; if it passes 5%, try temperature 0.7 next); two-call cycles such as the coder's in fastapi_14361, which (a) does not count. If build 5 fails (a) again, the open choice is whether to submit build 4 as a recorded deviation.
12. Done Nov 11: probe of build 6 (`results/probe8-6/`, design doc section 11.9; there is no probe8-5 folder). **Outcome: build 6 passes (b), (c) and (e) and fails (a) and (d). Not submitted under the rule.** (a) two tasks: in fastapi_14262 the coder resent one malformed edit_file call 31 times, and in rich_3064 the localizer ran one python command 14 times in a row; (b) 5 of 8 reach the verifier; (c) 7 of 8 patches change a source file; (d) the rich_3064 localizer ran python 19 times; (e) no turn cap. Resolved 3 of 8 (rich_3894, rich_3718, fastapi_14873), which is every task the notebook can judge. Mean task time 293 s. The test-dependency fix did not take effect in this run (cause unknown).
13. Done Nov 11: probe of build 7 (`results/probe8-7/`). From the console tables, before the traces were read: fails (a), because in fastapi_14873 the verifier reran `git status --short && git diff` about 125 times on an empty result; passes (b) with 6 of 8 and (e). Resolved 2 of 8 (rich_3894, rich_3718). Mean task time 240 s, against 293 s for build 6; two tasks hit the time cap, against four. **From the traces (design doc section 11.10): build 7 fails (a) only; it passes (b) 6 of 8, (c) 7 of 8, (d) and (e).** The coder's failed edits fell from 42 of 54 to 2 of 17. New finding: in two tasks the verifier reverted the coder's fix with `git checkout` to test the unfixed code. The test-dependency fix cannot work as built: the competition wheels folder holds neither package.
   **Decision rule, written before the build 7 probe (Nov 11).** The same five rules (a) to (e), unchanged. Reported but not deciding: resolved count; the coder's malformed-call share counted over distinct calls; failed edit_file calls; localizer python use. If no build has passed all five rules when the submission window opens, the choice of what to submit, if anything, is Rishi's and is recorded as a deviation from the rule.
14. Done Nov 11: probe of build 8 (`results/probe8-8/`, fingerprint `94a538c3`, design doc section 11.11). **Outcome: fails (a) and (d); passes (b) with 8 of 8, (c) with 7 of 8, and (e).** (a) rich_3064: the localizer resent one garbled read_file 33 times; rich_3894: the verifier reverted the coder's fix and then ran `git checkout -q .` 55 times; (d) the rich_3064 localizer ran python 22 times. Resolved 2 of 8 (rich_3718, fastapi_14873); rich_3894, resolved by every build since build 4, was lost to the verifier's revert. Mean task time 314 s.
   **Fallback by the rule in this item, since no build passed all five:** tasks with an identical run above 10: build 6 two, build 7 one, build 8 two. So the rule picks **build 7** (`dist/submission_v7_nov11.zip`, fingerprint `a2ce0f1a`). Resolved counts (3, 2, 2) are within noise and did not decide. Submitting it is a deviation from the five-rule bar and must be reported as one.
15. Next, the last probe of Nov 11: probe **build 10** (results into `results/probe8-10/`, fingerprint `1c756b85`). Build 9 (`2032e653`) was replaced before it was probed, after an outside review of the prompts found defects in its new verifier commands (Claude item 16). The rule below applies to build 10 in place of build 9.
   **Decision rule, written before the build 9 probe (Nov 11).** The same five rules (a) to (e). If build 9 passes all five, submit it. If not, the fallback is chosen among the probed builds 6, 7, 8 and 9 by the ranking of item 14, unchanged: fewest tasks with an identical run above 10, then most tasks reaching the verifier, then most patches that change a source file, then lowest mean task time. Reported but not deciding: resolved count; verifier commands that change /workspace outside the sanctioned compare command (git checkout, stash, reset, sed -i); tasks that end with the coder's fix missing.
    **Outcome of the build 10 probe (`results/probe8-10/`, fingerprint `1c756b85`, design doc section 11.12): fails (a) only; passes (b) with 5 of 8, (c) with 8 of 8, (d) and (e).** (a) rich_3718: the verifier resent one failing command 34 times (its own check script had a syntax error; the workspace was not touched). Resolved 3 of 8 (rich_3894, rich_3718, fastapi_14873), every task the notebook can judge. Mean task time 298 s. The verifier ran no command that changes /workspace in any task, and copied the 371-character first command exactly in 7 of 7 runs.
    **Fallback ranking, applied as written:** tasks with an identical run above 10: build 6 two, build 7 one, build 8 two, build 10 one. Builds 7 and 10 tie; on the second criterion build 7 reaches the verifier in 6 tasks and build 10 in 5, so **the ranking picks build 7**. Claude's recommendation differs and is build 10, because the second criterion separates them by one task, which is within run-to-run noise, while build 10 removes the verifier's reverting of fixes that cost a resolved task in build 8's probe. That recommendation is a departure from the written ranking. The choice is Rishi's and is recorded here once made.
    **Submitted Nov 11: build 10** (`dist/submission_v10_nov11.zip`, fingerprint `1c756b85`, 6-minute cap), Rishi's choice. This departs from the written ranking, which picked build 7, and no build passed all five rules, so the paper reports it as a deviation on both counts. **Scored 0.15 public (reported Nov 12 morning)**, against 0.12 for build 2. About 9 of roughly 60 public tasks; 95 percent Wilson interval 0.081 to 0.261, overlapping build 2's 0.058 to 0.222, so not a statistically significant change. Run time not captured again.
16. Decided Nov 11: the per-task cap stays at 6 minutes for tonight's submission. The 8-minute cap is the first experiment for Nov 12, once tonight's submission has a score and a run time, and it is tested as a single change.
17. Done Nov 11: probe of build 11 (`results/probe8-11/`, fingerprint `54f950e7`, design doc section 11.14). **Outcome: fails (a) and (d); passes (b) with 6 of 8, (c) with 8 of 8, and (e). Resolved 3 of 8, as build 10. Mean task time 304 s.** Neither failure involves the changed part: (a) is the coder resending one edit_file with old_string missing, 24 times, in fastapi_14262 (the same failure as in builds 2, 5 and 6); (d) is the rich_3064 localizer running the test file and a python one-liner 3 times. On the change itself: the verifier called check_fix.py first in 6 of 6 runs, compare_test.py once with the right verdict, never called load_skill, and ran no command that changes /workspace; the 34-call compare loop of build 10 did not recur, and verifier calls per run fell from 12.5 to 10.7. Not submitted; the next leaderboard result is build 10's.
18. Done Nov 11: gold-patch validation of all 129 dev tasks (`results/gold-1/`, `splits/measurable_tasks.json`). **70 measurable: 21 tuning (12 rich, 9 fastapi), 49 held-out (29 rich, 20 fastapi); requests 0 of 13.** Unmeasurable: 42 need `inline_snapshot`, `dirty_equals` or `pytest-httpbin`; 14 fail the reference fix on version mismatches (Pygments, starlette, and the notebook's installed requests/httpx shadowing the checkout); 3 pass without a fix (fastapi_14851, fastapi_14077, requests_6644: never training labels). New probe set `splits/probe_subset_m.json` (probe8m: rich_3061, rich_3470, rich_3521, rich_3894, rich_4006, fastapi_13920, fastapi_14372, fastapi_14458), notebook v5, results into `results/probe8m-<n>/`. Only rich_3894 survives from probe8, so probe8m numbers do not compare with probes 1 to 11.
19. Done Nov 11: paper draft in `docs/paper_draft.md`, 2,991 words including tables and references, citations verified with arXiv ids. Two placeholders: build 10's public score (leaderboard table) and the repository link (reproducibility note). Due Nov 12 at 23:59 UTC.
20. Overnight Nov 11 to 12: build 11 probe on probe8m (results into `results/probe8m-1/`; new baseline, not comparable with probes 1 to 11) and build 10 scoring on the leaderboard. **Morning Nov 12, in order:** (1) record build 10's score and run time in PLAN item 6 and the paper table; (2) run the check script on probe8m-1 and log it; (3) push the repository and add the link; (4) final read of the paper and submit it with margin before 23:59 UTC. Steps (1) and (2) done Nov 12 morning.
    - Keep `CHECK_WITHOUT_FIX = True`: tasks whose tests pass without a fix would label bad trajectories as successes in LoRA training.
    - Tag environment-broken tasks rather than dropping them: they cannot confirm a fix, but they can teach the behaviour in the next point.
    - Candidate agent change (not built): when `compare_test.py` reports a failure with and without the fix because of a missing module, the verifier submits at once instead of continuing to verify. If the scorer kept only tasks whose reference fix passes (the `FAIL_TO_PASS` lists suggest it), a missing package never blocks a scored task, so the agent must never end without a patch; it should only stop fighting the environment.
21. Done Nov 12: build 11 on probe8m (`results/probe8m-1/`, notebook v5, fingerprint `54f950e7`, design doc section 11.16). **Outcome: passes (a), (b) with 5 of 8 and (e); fails (c) with 5 of 8 and (d). Resolved 4 of 8 (rich_3521, rich_3894, fastapi_14372, fastapi_14458). Mean task time 326 s; five tasks hit the cap.** This is the baseline for every later build and does not compare with probes 1 to 11. The four failures are the coder's or cost it its time: in rich_3061 and fastapi_13920 it ran 20 and 15 python one-liners and never edited; in rich_3470 its fix broke an existing test, which `compare_test.py` reported correctly with 25 s left; in rich_4006 the localizer's and then the coder's reproduction each hit the bug's infinite loop and the 120 s command timeout. Coder time share 74%. Next single-change candidates, one build each: (i) no run_command by the coder before its first edit; (ii) `timeout 30` in front of every python command in the localizer and coder prompts; (iii) the 8-minute cap (item 16). Order to be chosen after the paper is submitted.
   **Decision rule, written before the build 8 probe (Nov 11).** The same five rules (a) to (e). If build 8 passes all five, submit it. If it does not, the fallback is chosen among the probed builds 6, 7 and 8 by: fewest tasks with an identical run above 10, then most tasks reaching the verifier, then most patches that change a source file, then lowest mean task time; that submission is recorded as a deviation from the rule. The decision is Rishi's.
   **Decision rule, written before the build 6 probe (Nov 11).** The same five rules (a) to (e) as item 10, unchanged. If both builds pass, submit build 6 only if it also reaches the verifier in at least as many tasks as build 5 and has a lower mean task time; otherwise submit build 5. Reported but not deciding: resolved count, malformed-call share, two-call cycles, seconds the coder runs after its first edit, and any git command by the verifier other than status, diff and show.
   **Probe environment changed on Nov 11 (design doc section 11.7).** From this probe on, the run cell installs `inline-snapshot` and `pytest-httpbin` for the sandbox. Before that, 5 of the 8 tasks could not pass in the notebook whatever the patch (not 3 as written in item 10), so resolved counts from probes 1 to 3 are out of 3 tasks. Agents now also see working tests in those tasks, so process numbers are not strictly comparable with probes 1 to 3.
   **Decision rule, written before the build 4 probe (Nov 11).** Submit build 4 when the window opens if all of these hold: (a) no task repeats one identical call more than 10 times in a row; (b) at least 4 of 8 tasks reach the verifier (probe 1); (c) at least 6 of 8 tasks end with a patch that changes a source file (probe 1); (d) no patch contains a file the localizer created, and the localizer runs no python or pytest; (e) no task ends from the turn cap. A task ending from the 150 tool-call cap is allowed by (e) but means a loop, which (a) already counts. Resolved counts are reported but do not decide: 8 tasks cannot separate builds, and 3 of the 8 cannot pass in the notebook at all (design doc section 11.5).

**Claude**
1. Done Oct 22: read the harness guide and starter notebook; froze the dev split.
2. Done Nov 10: `agent/` implements the S1 and S2 scaffolds of `docs/agent_design.md` (the loop cap is the only difference) with `eval_config.yaml`; `scripts/build_submission.py` compiles it with the competition compiler and writes `dist/submission.zip`.
3. Once compute is chosen: write the machine setup script and the run script.
4. Once a first `task_results.jsonl` exists: write the collector that turns it into the results CSV.
5. Done Nov 11: third build of `agent/` in `dist/submission.zip` (probed Nov 11, failed the decision rule in Rishi item 9, not submitted): `max_tool_calls` 400 and `max_turns` 500 so that only time binds; prompt call counts replaced by a time rule through get_status; a no-repeat rule in three prompts; a rule for malformed tool calls in the same three prompts (do not resend; read ranges with sed; keep edits to one or two lines). The build submitted on Nov 10 is kept as `dist/submission_v2_submitted_nov10.zip`.
6. Done Nov 11: read the probe traces (design doc section 11.4). The localizer overruns have three causes: plain repetition, malformed tool arguments (19% of file and command calls), and open-ended exploration. Two of the three verifier-approved failures match the reference fix. The malformed-call rule is now in build 3. Still to decide after the build 3 probe: thinking budget, temperature and a repetition penalty.
7. Done Nov 11: fourth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed). Two changes on top of build 3: the localizer no longer reproduces the bug (it runs only read-only commands, its reply has no REPRODUCE section, and the verifier writes its own reproduction under /tmp); `max_tool_calls` goes from 400 to 150 as a loop backstop. Build 3 is kept as `dist/submission_v3_probed_nov11.zip`.
8. Done Nov 11: fifth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed). Two config changes on top of build 4, no prompt changes: the localizer samples at the Gemma 4 model card's standard setting (temperature 1.0, top_p 0.95, top_k 64; was 0.2 and 0.95); the coder's `max_output_tokens` goes from 4096 to 2560. Build 4 is kept as `dist/submission_v4_probed_nov11.zip`.
9. Done Nov 11: sixth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed): build 5's configs plus rewritten localizer, coder and verifier prompts (design doc section 11.7). Build 5 is kept as `dist/submission_v5_nov11.zip`. After the build 5 probe, two lines were added before build 6 was probed: the coder is told that write_file cannot write to /tmp and how to make a scratch script instead; the verifier is told that submit_patch is its last tool call.
11. Done Nov 11: seventh build of `agent/` in `dist/submission.zip` (not submitted, not yet probed): build 6 with one config change, the coder sampling at the model card's setting (temperature 1.0, top_p 0.95, top_k 64; was 0.2 and 0.95). Build 6 is kept as `dist/submission_v6_probed_nov11.zip`.
13. Done Nov 11: eighth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed): build 7 plus three prompt fixes for the chain failure seen in fastapi_14873. The verifier's first command prints `NO CHANGES IN WORKSPACE` when nothing was edited, and the prompt sends it straight to NOT VERIFIED; every shell example names `run_command`, and all three prompts say that grep, sed, git and python are shell commands, not tools; the coder ignores a localization that is empty or not in the LOCATIONS layout. Build 7 is kept as `dist/submission_v7_nov11.zip`.
14. Done Nov 11: build 8 is kept as `dist/submission_v8_probed_nov11.zip`.
15. Done Nov 11: ninth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed; fingerprint `2032e653`): build 8 with `prompts/verifier.md` changed and nothing else. The verifier's first command saves the coder's change to `/tmp/coder_fix.patch` and its output says what to do next (go on, restore the fix, or reply NOT VERIFIED); the prompt gives one sanctioned command for comparing a test with and without the fix, which puts the fix back in the same command; a submit_patch result of patch_size 0 now means restore and resubmit. All commands were tested locally on a scratch repository.
16. Done Nov 11: tenth build of `agent/` in `dist/submission.zip` (not submitted, not yet probed; fingerprint `1c756b85`): build 9 with fixes from an outside prompt review, each checked against the harness source or a trace first. Build 9 is kept as `dist/submission_v9_nov11.zip`.
    - Fixed (review items 1, 3, 4): the compare command no longer removes the fix; it runs the test on a separate copy of the original code (`git worktree` under /tmp/base), so a command timeout cannot leave the workspace reverted. The harness limits a command to the smaller of 120 s and the task's remaining time and kills it on timeout, which the build 9 command did not survive. The first command now prints its status line before a diff capped at 3,500 characters, because the harness keeps only the first 5,000 characters of output. A fix made only of new files is no longer reported as no edits.
    - Fixed (review item 2): python examples in the coder and verifier prompts start with `PYTHONPATH=/workspace:/workspace/src`. In the probe sandbox a plain `import` of a src-layout package loads the notebook's installed copy, not the checkout (seen in the requests task in probes 2 and 8).
    - Not changed (review items 5 and 6): preserving pytest's exit code through `tail`, and tighter stopping rules for the localizer and coder. Both change what the model sees or is asked to do, so they need a probe of their own.
    - All commands are run from the built prompt text by a check script on flat and src layouts; 28 of 28 expected fixes are present in the zip.
17. Done Nov 11: eleventh build of `agent/` in `dist/submission.zip` (not submitted, not yet probed; fingerprint `1c756b85` became `54f950e7`): build 10 with the verifier's save, compare and restore commands moved into the skill `agent/skills/verify-fix` (design doc section 11.13). Only `sub_agents/verifier.yaml`, `prompts/verifier.md` and the new skill changed. Build 10 is kept as `dist/submission_v10_nov11.zip`.
12. Done Nov 11: the probe notebook prints a version banner (now `probe8 notebook v4`) with a fingerprint of the attached agent build, in section 2 and at the top of the run cell, and saves it as `probe8/version.txt` in the results zip. Build fingerprints: build 2 `b84b04cc`, build 3 `fa95a4a1`, build 4 `11349a20`, build 5 `797faff7`, build 6 `517d0471`, build 7 `a2ce0f1a`, build 8 `94a538c3`, build 9 `2032e653` (never probed), build 10 `1c756b85`, build 11 `54f950e7`. The fingerprint is a hash of the files in `dist/submission.zip`, so uploading the raw `agent/` folder (which also holds `prompts/system.md`) gives a different value.
10. Done Nov 11: the probe run cell installs the two missing test dependencies for the subprocess sandbox (`notebook_cells/probe8_cells.py`, `probe8_run.ipynb`). Not tested on Kaggle yet; it prints `PROBE test dep` lines and cannot stop the run.

## To confirm on Kaggle's own pages

Confirmed 2026-11-05 on the Overview and Data tabs:

- About 120 test tasks from private repos, split evenly between public and private leaderboard halves; the private half decides prizes.
- Deadlines: paper Nov 12; main-track entry and team merger Nov 25; final submission Dec 2; all at 23:59 UTC.
- Small-model bonus: $10,000 to the highest-ranking submission that uses Gemma E2B or E4B as its base model; it must be one of the team's two selected final submissions, and LoRA is allowed.
- Allowed base models are the four QAT w4a16 variants (31B, 12B, E4B, E2B). Every agent shares one base model, and each agent may use a different LoRA adapter.
- All L4 sessions must have internet disabled.

Partly answered Nov 10: the first pipeline submission ran 13 hours and was still scored (0.03), so a run over 12 hours did not fail outright. Rishi also reports an earlier run that took over 18 hours. Working hypothesis (Nov 10): the 12-hour limit counts agent time only, not sandbox setup, so the per-task cap may go up to 6 minutes (120 tasks at 6 minutes is exactly 12 hours of agent time); an alternative is that the limit is not enforced on the scoring run. Neither can be confirmed without exceeding it. The second submission (Nov 10, lean config, first 31B run) uses a 6-minute cap on that hypothesis. Setup overhead measured from the 13-hour run: about 1.3 minutes per task.

## Outside reports (unverified, not used for decisions)

Collected from participant repos and search snippets before the Oct 23 sourcing rule. Kept only so that if our own runs hit the same behavior, we recognize it. Each one is a hypothesis to test with our own data, never a premise.

| Report | What to check in our own runs |
|---|---|
| Tasks run one at a time, and an overrun fails the entire submission | Total wall time of our Kaggle submissions vs the 12 hours; any submission that errors near the limit |
| Prompt plus `max_output_tokens` over 32,768 raises an error and loses the task's patch, even one already submitted | Context-overflow error counts and empty patches in every run |
| Sub-agent (AgentTool) sessions are never compacted | Context growth in traces if we use sub-agents |
| About 25.5 tokens per second on 4×L4 | Our own throughput calibration per model |
| 31B with no LoRA scored 0.12 public in one team's first submission | Our own 31B result, if we run it |
| A first LoRA pilot scored 2/11 against 4/11 for the baseline | Any LoRA comparison on the held-out split, with paired statistics |
| The sample config solved 4 of 5 dev tasks | Our own S0 pass over the dev split |
| Top public score 0.24 as of Oct 2 | Current leaderboard, read directly on Kaggle |

## Sources

- Main competition: https://www.kaggle.com/competitions/gemma-4-developer-agent
- Paper track: https://www.kaggle.com/competitions/gemma-4-developer-agent-paper
- Competition Overview (deadlines, models, bonus, no internet on L4): https://www.kaggle.com/competitions/gemma-4-developer-agent/overview
- Competition Data tab (test set size and curation pipeline): https://www.kaggle.com/competitions/gemma-4-developer-agent/data
- Gemma 4 model card (January 2025 pre-training cutoff): https://ai.google.dev/gemma/docs/core/model_card_4
- Harness guide and starter notebook: `data/HARNESS_README.md` and `data/getting-started-gemma-4-developer-agent.ipynb` (competition files, not committed)
- GCP g2-standard-48 prices (third-party, updated Oct 18, 2026): https://gcloud-compute.com/g2-standard-48.html
- RunPod prices: https://www.runpod.io/gpu-cloud/pricing
- Ollama Gemma 4 tags: https://ollama.com/library/gemma4/tags
- Ollama context length: https://docs.ollama.com/context-length
- Kaggle GPU quota (user reports, not official): https://gpuperhour.com/blog/free-cloud-gpus-and-credits
