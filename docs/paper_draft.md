# Signals, Not Rules

*What nine builds of an offline Gemma 4 coding agent taught us about controlling a small model, and about trusting the benchmark*

## Abstract

Can a small open model fix real bugs on its own, offline, under a strict time budget? We studied this in a competition where one quantised Gemma 4 model, running locally, must repair about 120 unseen Python bugs within 12 hours. We built a four-role agent (locate, fix, verify, submit), ran nine versions of it on a fixed set of development tasks, and read every execution log.

Three results stand out. First, the model mostly ignored rules written in its instructions, such as budget limits and bans on risky commands, but tended to follow feedback that arrived in tool responses and the structure of the reply it was asked to produce. Second, malformed tool calls depended on the tool's argument structure: 47% of calls to an editing tool that takes two blocks of code were malformed, against 0.2% for a tool that takes one free-text command. Third, when we checked the development tasks with their official fixes, 59 of 129 could not be measured in our evaluation environment at all, mostly because of missing test packages; five of our eight original test tasks were among them, so earlier results had under-counted correct fixes.

The implication for building agents on small models is to put control where the model looks: in tool outputs, reply templates and deterministic scripts rather than in prompt rules, and to validate the evaluation environment before trusting any score.

## 1. Introduction

This competition requires one quantised Gemma 4 model, served locally by vLLM on four 24 GB L4 GPUs, to fix about 120 unseen bugs in 12 hours with no internet. At our measured 31 tokens per second, that is roughly six minutes and 11,000 generated tokens per task.

We planned a controlled comparison of where to spend that budget, but within a few runs the agent was losing most tasks to loops, malformed tool calls and self-inflicted damage. We switched to an iterative protocol: change one thing, probe it on a fixed task subset, read every log, and decide by rules written before the results.

Contributions:

1. A validation of the 129 development tasks showing that 59 cannot be measured in our evaluation environment, with the causes.
2. An account, from execution logs, of how a 31B open model fails as a multi-role coding agent under a tight budget, across nine builds and 72 task runs.
3. Observations that prompt rules about budgets and behaviour did not bind while tool-result text and reply structure did, and a design conjecture that follows.
4. Counts of malformed tool calls by interface, showing a strong association between argument structure and failure rate.

## 2. Setup

**Task and scoring.** Each task is a GitHub issue in a Python repository at a fixed commit. The agent works in a sandboxed checkout and submits a patch; a clean container then applies the patch and the hidden tests, and the task counts as resolved only if every test in those files passes. Scoring uses about 120 tasks from private repositories.

**Budget.** The 12-hour total is fixed; per-task caps on time, tool calls and turns are ours to choose. Our builds use a 6-minute cap, the total divided by the task count.

**Agent.** The agent is built with the Google Agent Development Kit (ADK) and runs four roles in a fixed order, all served by the same model. The *localizer* searches the code, read-only, and names the places to change. The *coder* edits the code. The *verifier* reproduces the issue, runs existing tests, and either submits the patch or sends it back with a review. The coder and verifier alternate for at most three rounds; if no round ends in a submission, the *finalizer* submits whatever is in the working tree. Each role sees only its own instructions and a short summary from the previous role. Reasoning-token generation is enabled for the coder only, with a budget of 1,024 tokens per call; the other roles answer directly.

**Development data.** The organisers provide 129 tasks from four public repositories. We froze a split before any comparison: 42 tasks for tuning, 87 held out. For fast iteration we chose a fixed *probe set* of 8 tuning tasks representative of the full set in patch size, hunk count, issue length and multi-file share.

**Probe protocol.** We call each agent version a *build*, numbered in the order we made them. Each build ran once on the probe set on the competition hardware, saving a full execution log (a *trace*) per task. Because 8 tasks cannot separate builds statistically, decisions used process measures under a rule written before each run. A build was eligible for submission only if: (a) no task repeated one identical tool call more than 10 times in a row; (b) at least as many tasks reached the verifier as in the reference build; (c) at least as many tasks ended with a patch that changed source code; (d) the localizer ran no code; and (e) no task ended from the turn cap.

## 3. Results across builds

One fact is needed to read the table: in 5 of the 8 probe tasks even the official reference fix fails in our evaluation environment (Section 4.6), so the resolution column counts only the 3 tasks that can be passed, while the process columns use all 8.

**Table 1.** One probe run per build, 8 tasks each; builds 1 and 9 were never probed on this set. Section 4 describes each change.

| Build | Main change | Resolved (/3) | Reached verifier (/8) | Source patch (/8) | Tasks with a call repeated over 10 times (/8) | Mean task time |
|---|---|---|---|---|---|---|
| 2 | First 31B build | 1 | 4 | 6 | 3 | 270 s |
| 3 | Budget rules in prompts, cap 400 | 1 | 2 | 3 | 5 | 325 s |
| 4 | Localizer stops running code | 2 | 6 | 6 | 3 | 323 s |
| 5 | Localizer sampling | 2 | 4 | 6 | 0 | 310 s |
| 6 | Prompts as step lists | 3 | 5 | 7 | 2 | 293 s |
| 7 | Coder sampling | 2 | 6 | 7 | 1 | 240 s |
| 8 | Broken-call fixes | 2 | 8 | 7 | 2 | 314 s |
| 10 | Verifier protects the fix | 3 | 5 | 8 | 1 | 298 s |
| 11 | Verifier scripts | 3 | 6 | 8 | 1 | 304 s |

The longest identical run was 135 calls (build 3).

No build passed all five rules. We submitted build 2 and, departing from our own rule, build 10 (Section 5).

## 4. Findings

### 4.1 Prompt rules did not bind; feedback in tool responses did

We first tried the obvious way to control a budget: tell the model (build 3). Its prompts asked every role to check remaining time with a free `get_status` tool, never to repeat a call, and to stop reproducing a bug after one failed attempt. `get_status` was called once in 8 tasks. Five tasks repeated a single call 30 to 135 times in a row; one localizer made 221 calls, 12 of them distinct. The rule against creating files in the repository was broken in three tasks, and those files entered the submitted patches.

Two other mechanisms did work. The harness appends "Only 10 tool calls remaining" to tool results near the end of the call budget; with a 150-call cap (build 4), two looping localizers stopped at exactly 140 calls, when that text appeared, and the other two at 147 and 148. And the localizer stopped running code entirely after a change (build 4) that both removed the REPRODUCE section from its reply template and told it not to run code. The earlier prompt had asked for reproduction, so this comparison cannot say which of the two changes mattered; we note only that the template changed what the role was asked to deliver, not just what it was told to avoid.

The pattern held throughout: self-monitoring rules were followed inconsistently or not at all; tool-result text and reply-template fields were followed reliably. Since the supporting builds changed more than one thing at a time, we state the conclusion as a conjecture that later builds were designed on: **put control where the model looks, in tool outputs and reply structure, not in instructions.**

### 4.2 Loops: a sampling problem with a budget backstop

The loops had a clear signature: roles without reasoning tokens, sampled at temperature 0.2, wrote no text between calls, so after one repeat the context held only identical call and result pairs, which the model continued.

A tool-call cap is a backstop, not a fix: raising it from 80 to 400 (build 3) let loops run to the time cap, and tasks reaching the verifier fell from 4 to 2 of 8. Switching the localizer to the model card's standard sampling, temperature 1.0 with top-p 0.95 and top-k 64 (build 5), cut the longest identical run from 84 to 3 and its calls from 665 to 250. The same change for the coder (build 7) cut failed edits from 42 of 54 to 2 of 17. The cost: at temperature 1.0 the localizer broke its read-only rule in about one task per run.

### 4.3 Which calls break, by tool

Across the 40 task runs of builds 6, 7, 8, 10 and 11, malformed calls were concentrated by tool. We count every tool call in the saved traces, and call it malformed if a required argument is missing, an unexpected argument name appears, or line-number text is folded into the file path.

**Table 2.** Malformed calls, builds 6, 7, 8, 10 and 11.

| Tool (arguments) | Calls | Malformed |
|---|---|---|
| `run_command` (one free-text command) | 1,197 | 2 (0.2%) |
| `read_file` (path, two line numbers) | 599 | 75 (12.5%) |
| `edit_file` (path, two blocks of code) | 153 | 72 (47.1%) |

This is an association: the tools differ in what the model must produce as well as in argument structure, and we did not vary the interface with the task fixed. The `edit_file` failures came from only 9 distinct broken calls, resent repeatedly. In one task, across four builds, the coder closed the first code block with a backtick instead of the string delimiter; the second block was parsed into nonsense keys, the tool reported a missing parameter, and the coder resent the identical call up to 47 times. A call with one free-text argument has no boundary between arguments to get wrong, so our untested hypothesis for the next editing interface is to keep code in one argument and give its position as numbers.

### 4.4 Moving procedures into code

The verifier must compare behaviour with and without the fix. Left to itself (builds 7 and 8) it did so with `git checkout`, which erased the fix it was checking. This happened in 3 of the 14 tasks that reached the verifier, despite a prompt rule forbidding the command and explaining why, and once it cost a task that every build since build 4 had solved.

We then gave the verifier a sanctioned shell command that saved a copy of the fix and compared on a separate copy of the code (build 10). The model copied the 371-character command exactly in 7 of 7 uses, though once it adapted the comparison command into a broken script and resent it 34 times. That alone stopped the erasure: no verifier run changed the workspace (0 of 5). Finally we moved the same procedures into three small scripts, packaged as an ADK skill, which the verifier calls by name with at most one argument (build 11). Its separate result: the comparison loop did not recur (one script call with the correct verdict, against 41 comparison commands before), verifier calls per run fell from 12.5 to 10.7, and again no run changed the workspace (0 of 6).

An operation the model must get right every time belongs in deterministic code that reports one result line, not in a rule or a long command to retype.

### 4.5 Where the time goes

Pooling builds 6, 7, 8, 10 and 11, the coder used 69% of agent time, the localizer 17% and the verifier 14%. On the new measurable probe set the coder's share was 74%. Coder calls averaged 11.7 seconds and 400 generated tokens, mostly reasoning. Thirteen of 40 runs hit the 6-minute cap, 12 with an edit already in place, almost all on the two multi-file tasks. The harness also truncates the conversation history past 14,336 tokens; in builds 2, 3 and 4 this reset the localizer's history 9 to 15 times per probe, after which it repeated searches it could no longer see.

For our original budget question, this suggests the binding resource is the coder's generation time, and the largest available gain is fewer tokens per coder call rather than more model capacity or retries.

### 4.6 Most probe tasks could not be measured

Before interpreting agent scores, we checked whether each task's hidden tests accept the reference fix (the official fix from the original pull request) and reject the unchanged code. This check, standard in SWE-bench-style benchmarks, ran in the probes' evaluation environment: a Kaggle notebook running the harness's subprocess sandbox, which sees the notebook's installed packages.

Seventy of the 129 tasks met both conditions: 41 of 48 rich, 29 of 67 fastapi, 0 of 13 requests, 0 of 1 httpx. Of the 59 that did not, 42 need a test package the competition's wheels do not provide (`inline_snapshot` in 28 tasks, `dirty_equals` in 9, `pytest-httpbin` in 8; three tasks need both of the first two, so the counts sum to 45 over 42 tasks), 14 fail their own reference fix with no package missing, and 3 pass with no fix at all.

For the 14 we read the test output. In 13 we diagnose, without certainty, version differences between the notebook's installed packages and the repository's (Pygments-dependent tests in rich, starlette-dependent tests in fastapi, the installed `requests` and `httpx` shadowing the checkout); in the last, a required new test is skipped, which the harness rightly refuses to count as a pass.

Five of our eight original probe tasks were among the 59; in one, our agent's patch matched the reference fix in substance in eight builds and was counted as a failure each time. We have replaced the probe set with 8 measurable tasks chosen by the same criterion. Build 11's first run on the new set resolved 4 of 8. All four failures came down to the coder's time: in two it ran 15 and 20 exploratory python commands and never edited; in one, reproductions by the localizer and then the coder each hit the bug's infinite loop and the 120-second command timeout; in the last, its fix broke an existing test, which the compare script reported correctly with 25 seconds left before the cap.

We cannot test the official scoring environment directly, but its image installs only pytest and build tools, and its 124 provided wheels (41 packages) do not include the three missing ones. Whether the hidden tasks were validated against their reference fixes before scoring is not stated; if they were, as is standard, this affects development measurement rather than the leaderboard.

## 5. Leaderboard

| Submission | Model and build | Per-task cap | Public score |
|---|---|---|---|
| Organisers' sample configuration | 12B | 1 min | 0.03 |
| Our first pipeline | 12B, three-role loop | 5 min | 0.03 |
| Build 2 | 31B | 6 min | 0.12 |
| Build 10 | 31B | 6 min | 0.15 |

The public leaderboard covers about 60 tasks, so 0.12 and 0.15 are roughly 7 and 9 resolved (95% Wilson intervals 0.058 to 0.222 and 0.081 to 0.261) against roughly 2 (0.009 to 0.114) for the earlier submissions. These scores do not establish a statistically significant improvement between any two submissions, and we never chose between builds by them.

Build 10 was submitted despite failing rule (a). Its one long loop left the workspace intact, and its verifier no longer erased fixes, which had cost a task in the build before it.

## 6. Related work

SWE-bench (Jimenez et al., 2024) defined issue-to-patch evaluation with hidden tests, and Section 4.6 uses its validation logic. SWE-agent (Yang et al., 2024) showed that the agent-computer interface strongly affects performance; Section 4.3 is an instance at the level of argument structure. Agentless (Xia et al., 2024) argued that fixed pipelines can match open-ended agents, which motivated our design. SWE-Gym (Pan et al., 2024) trains open models on agent trajectories, our next direction. Snell et al. (2024) frame our original budget question.

Two recent preprints are closer to what we ended up studying. Sigdel and Baral (2026) compare tool-interface designs for one local model under interaction budgets and find that schemas reduce misuse while task completion stays at zero; our process measures rely on the same separation of contract adherence from task outcome. Wang and Huang (2026) build a local-first harness with mechanisms against repeated actions and premature completion, and caution that repeat-run variation matches their ablation effects, a limit our comparisons share.

What we add: for one production harness and model, where control had to sit to be obeyed, which argument structures broke, and how much of a public development set could be measured at all.

## 7. Limitations

Each build ran once on 8 tasks, of which only 3 could be passed, so no resolution difference in Table 1 is statistically meaningful. The validation in Section 4.6 also shrank the pool for future comparisons: 70 measurable tasks, 49 held out and 21 for tuning, all from two repositories (rich and fastapi), with requests contributing none.

How much that pool can detect we estimated by simulation (`analysis/power_simulation.py`): per-task success rates drawn from a Beta distribution with mean 0.15 and concentration 2, a uniform shift on the logit scale, and a paired sign-flip test at alpha 0.05. Power to detect a 10-point gain is 46% with 87 tasks and one run per arm and 93% with three runs; with 49 tasks it is 22% and 70%. Held-out comparisons will therefore need repeated runs or recovered tasks.

Several builds changed more than one thing, so some attributions in Section 4 are to a group of changes. The dev repositories are popular and were probably in the model's pre-training data. We did not test our pre-registered hypotheses on model size, retries and navigation tools; the reliability problems came first.

## 8. Conclusion

For a small open model under a fixed budget, the first problem is not where to spend compute but whether the agent can spend it at all. The controls that worked were the ones the model sees as data: tool results, reply templates, and scripts that do the fragile work and report one line. Next: validated tasks for every comparison, an editing interface that keeps code in one argument, and fine-tuning aimed at the coder's generation cost.

**Reproducibility.** The agent configuration of every probed build, the per-task results and patches of every probe, the gold validation, the notebook cells, the analysis scripts and the decision rules with their dates are at https://github.com/iHrushikesh/signals-not-rules; competition data is not, per the rules.

## References

Jimenez, C. E., et al. (2024). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? ICLR 2024. arXiv:2310.06770.
Pan, J., et al. (2024). Training Software Engineering Agents and Verifiers with SWE-Gym. arXiv:2412.21139.
Snell, C., et al. (2024). Scaling LLM Test-Time Compute Optimally Can Be More Effective than Scaling Model Parameters. arXiv:2408.03314.
Sigdel, A., Baral, R. (2026). Schema First Tool APIs for LLM Agents: A Controlled Study of Tool Misuse, Recovery, and Budgeted Performance. arXiv:2603.13404.
Wang, H., Huang, T. (2026). Mingbird: A Local-First Agent Harness Enabling Small Open Models to Complete Real Tasks. arXiv:2610.02001.
Xia, C. S., et al. (2024). Agentless: Demystifying LLM-based Software Engineering Agents. arXiv:2407.01489.
Yang, J., et al. (2024). SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024. arXiv:2405.15793.
