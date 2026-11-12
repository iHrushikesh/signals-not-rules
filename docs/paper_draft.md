# Signals, Not Rules

*How an Offline Coding Agent Loses Time, Work, and Credit*

## Abstract

A coding agent can spend its entire execution budget investigating a bug without attempting a fix. We investigate how such failures arise, and how different forms of control influence agent behaviour, in an offline coding agent built around a quantised 31B Gemma 4 model. Across nine configurations and 93 task runs under a six-minute task budget, we analyse repeated actions, malformed tool calls, verification failures, and unintended loss of patches. Instructions to monitor budgets, avoid repetition, and preserve work were followed inconsistently. Counting each distinct call once, tools taking several structured arguments were malformed in 6–10% of calls in both evaluation stages, against at most 0.2% for a tool taking one shell command; identical resends inflated the editing tool's raw rate to 47% in the first stage. Tool-result warnings coincided with exits from prolonged loops, while later configurations using protected verification procedures showed no recurrence of patch erasure. Nevertheless, prolonged exploration without edits persisted in runs without long identical-call loops. Interpreting these failures also required validating the evaluation environment: 59 of 129 development tasks failed a check requiring the reference patch to pass and unchanged code to fail. The final configuration resolved 8 of 21 validated tuning tasks.

These observations motivate a design hypothesis: tool feedback, structured responses, and deterministic procedures can provide more effective operational control than prompt rules alone. Although the comparisons do not isolate causal effects, the study identifies concrete mechanisms and failure modes for future controlled experiments.

## 1. Introduction

An autonomous coding agent must do more than identify a plausible repair. It must decide when to stop investigating, express changes through the available tools, and check its work without destroying it, all within a fixed execution budget.

Instructions can state these requirements, but stating them does not establish that an agent follows them. Should operational control instead enter through tool feedback, required response structure, or executable procedures? Answering requires execution traces alongside task outcomes, because a failed evaluation can reflect an incorrect repair, a workflow breakdown, or a problem in the evaluation environment.

We examine these distinctions in a case study on the public development tasks and harness of the Gemma 4 Developer Agent Competition (Markowitz et al., 2026). Our initial question was how to divide a fixed budget among model size, verification retries, and code-navigation tools; recurrent operational failures led instead to an iterative observational study of control and measurement. We contribute:

1. An analysis of operational failures and responses to control mechanisms across nine configurations and 93 task runs.
2. Malformed tool-call counts that separate interface errors from their amplification through repetition.
3. An audit of 129 development tasks, and an evaluation of the final configuration on the 21 tuning tasks that passed.
4. A design hypothesis about placing control in tool feedback, response structure, and deterministic procedures, with competing explanations and counterexamples.

## 2. Experimental setting and study design

**Setting and budget.** The competition allows 12 hours for about 120 tasks, including sandbox setup but excluding grading, and restricts agents to Gemma 4 models. We chose a six-minute task cap from that allowance. The model is the largest variant, Gemma 4 31B with 4-bit weights and 16-bit activations, served by vLLM on four 24 GB L4 GPUs without internet access. At a measured 31 generated tokens per second, six minutes permits about 11,000 tokens before tool execution.

**Agent.** Four roles share the model. The *localizer* identifies where a change belongs; in the final configuration it is told not to modify files or execute code. The *coder* edits the repository. The *verifier* checks the patch with reproductions and existing tests, then submits it or requests another coding round, for at most three rounds; a *finalizer* provides a fallback submission. Each role sees its own instructions and a short handoff from the preceding role. Only the coder generates reasoning tokens, at most 1,024 per call.

**Data and outcomes.** The competition's 129 public development tasks are bug fixes and feature requests from rich, fastapi, requests, and httpx, released with problem statements, repository snapshots, reference patches, and evaluation tests (Markowitz et al., 2026). The agent receives the problem and the repository with its existing tests. A task is resolved when the submitted patch passes all tests the evaluator requires.

**Validation and splits.** Before any comparison we froze a split of 42 tuning and 87 held-out tasks. Later validation required the reference patch to pass and unchanged code to fail in our local evaluation environment. Seventy tasks met both conditions: 21 tuning and 49 held-out.

**Two stages.** Nine configurations each ran once on the same eight tuning tasks, chosen to approximate the development set's patch-size, hunk-count, issue-length, and multi-file distributions. These 72 runs drove iteration. After validation exposed problems in five of those tasks, the final configuration, unchanged, ran on eight validated tuning tasks chosen the same way, then on the remaining thirteen. The study thus contains 93 runs over 26 distinct tasks; the final configuration ran three tasks in both stages. Agents were evaluated only on the tuning split.

**Measurements.** We saved execution traces, patches, test outputs, and role timings. Process checks, written after the first probe and fixed before each later one, required no streak exceeding ten identical calls, verifier reach and source-patch coverage at least matching the reference configuration, no localizer execution, and no turn-cap termination. Time shares sum recorded model and tool durations. Several configurations changed multiple components and each configuration-task pair ran once per stage, so comparisons are descriptive, not isolated treatment effects.

## 3. Evidence across configurations

In Table 1, configuration numbers are build numbers; the repository's result folders are numbered by probe run, so `probe8-1` to `probe8-4` hold configurations 2 to 5 and later folders carry the configuration number. The resolution denominator is three because only three original probe tasks passed our later validation; process measures cover all eight.

**Table 1.** Original probe: eight tasks per configuration. Configurations 1 and 9 were not run on this set. Mean task time includes local grading.

| Configuration | Main change | Resolved (/3) | Reached verifier (/8) | Source patch (/8) | Tasks with >10 consecutive identical calls (/8) | Mean task time |
|---|---|---|---|---|---|---|
| 2 | Initial 31B pipeline | 1 | 4 | 6 | 3 | 270 s |
| 3 | Budget instructions; call cap 400 | 1 | 2 | 3 | 5 | 325 s |
| 4 | Localizer instructions and reply template; call cap 150 | 2 | 6 | 6 | 3 | 323 s |
| 5 | Localizer sampling | 2 | 4 | 6 | 0 | 310 s |
| 6 | Instructions as step lists | 3 | 5 | 7 | 2 | 293 s |
| 7 | Coder sampling | 2 | 6 | 7 | 1 | 240 s |
| 8 | Tool-call recovery instructions | 2 | 8 | 7 | 2 | 314 s |
| 10 | Protected verification commands | 3 | 5 | 8 | 1 | 298 s |
| 11 | Verification scripts | 3 | 6 | 8 | 1 | 304 s |

No configuration met every process check. For external context, configurations 2 and 10 received public leaderboard scores of 0.12 and 0.15, which were not used to select configurations or infer treatment effects. Configuration 10 was submitted despite exceeding the repetition threshold because its verifier preserved patches, an explicit exception to the submission rule.

## 4. Control failures and observed responses

### 4.1 Instructions, feedback, and response structure

Telling the agent to monitor its budget did not reliably produce monitoring. With budget instructions and a 400-call cap, the free `get_status` tool was used once in eight tasks. Five tasks repeated an identical call 30–135 times consecutively. One localizer made 221 calls, only 12 distinct; three created files despite a prohibition.

A different pattern appeared near the tool-call limit. With a 150-call cap, the harness appended a warning after call 140: only ten calls remained, and the agent should finalise its work. Two localizers that had repeated one search 84 and 58 times gave their final reply immediately after this warning; two others stopped at calls 147 and 148.

Response structure also changed alongside behaviour. Removing a REPRODUCE field from the localizer's reply template, while instructing it not to execute code, was followed by no localizer execution in that probe. Both changed together, and the earlier instructions had requested reproduction, so we cannot attribute the outcome to the template alone.

Neither mechanism guaranteed compliance. In the final evaluation, `fastapi_14873` received two verifier reviews reporting that no edits existed, yet produced no patch, although the same configuration had resolved the task in the original probe. The warning evidence rests on four runs, and an instruction in the latest tool result differs from the initial prompt in recency as well as channel. These observations motivate testing where and when instructions are presented; they do not establish reliable control through tool feedback.

### 4.2 Repetition and exploration without progress

Repetition consumed much of the early budget. Roles without reasoning tokens, sampled at temperature 0.2, often emitted successive calls without intervening text. Raising the call cap from 80 to 400 allowed longer loops; verifier reach fell from four to two tasks.

After the localizer switched to temperature 1.0, top-p 0.95, and top-k 64, its longest identical-call streak fell from 84 to two and its total calls from 665 to 250. A similar change for the coder was followed by a drop in failed edit calls from 42/54 to 2/17. These single-run comparisons suggest sensitivity to sampling, with a tradeoff: localizers still sometimes violated their execution restrictions.

The final evaluation exposed a limit of the repetition metric. Across all 21 tasks, no identical-call streak exceeded two, yet six tasks ended without a task-relevant edit. Localizers executed code on five tasks despite their instructions; one issued 140 shell commands exploring escape sequences, and other runs repeatedly inspected code or tried small Python examples. Activity can remain unproductive while individual calls differ, so a progress measure should also record workspace changes and time to the first edit.

### 4.3 Interface errors and their amplification

We classify a call as malformed if a required argument is missing, an unexpected argument name appears, or line-number arguments are embedded in a file path. Raw counts include every repeated attempt; distinct counts treat identical calls by one role within a run as one.

**Table 2.** Malformed calls in 40 runs of configurations 6, 7, 8, 10, and 11 on the original probe.

| Tool (arguments) | Calls | Malformed | Distinct calls | Distinct malformed |
|---|---|---|---|---|
| `run_command` (one free-text command) | 1,197 | 2 (0.2%) | 902 | 2 (0.2%) |
| `read_file` (path, two line numbers) | 599 | 75 (12.5%) | 526 | 35 (6.7%) |
| `edit_file` (path, two blocks of code) | 153 | 72 (47.1%) | 90 | 9 (10.0%) |

A recurring edit error closed one code block with a backtick instead of a string delimiter, turning the remaining code into invalid argument keys. The tool reported a missing parameter, but the coder sometimes resent the call dozens of times despite an instruction prohibiting this.

On the 21 validated tasks, where such loops did not occur, raw rates were 0/564 for commands, 20/211 for reads (9.5%), and 3/33 for edits (9.1%); distinct-call rates were 0/514, 18/193 (9.3%), and 2/32 (6.2%). The 47% edit rate was therefore largely repetition. What recurred in both stages was a distinct-call rate of 6–10% for the two tools with several structured arguments, against at most 0.2% for the single-command tool. The tools differ in argument structure and generated content, and the samples in task mix, so a controlled interface comparison is needed to test whether simpler argument boundaries reduce errors.

### 4.4 Verification can destroy the work it checks

Verification sometimes erased the patch it was meant to assess. In configurations 7 and 8, the verifier used `git checkout` to compare against original code, removing the fix in three of the fourteen runs that reached verification, although its instructions prohibited this command and explained the risk.

Protected comparison commands saved the patch and tested a separate copy of the code. In the next probe, the verifier copied a 371-character command correctly in seven uses, and no verifier changed the workspace in the five tasks it reached. However, it also adapted a comparison command into a broken script and repeated it 34 times.

Packaging the procedures as three executable scripts reduced the text the model had to reproduce. In the following probe, one comparison-script call returned the correct verdict, the loop did not recur, and mean verifier calls per invocation fell from 12.5 to 10.7. Again no verifier changed the workspace, in six tasks.

These are distinct outcomes: protected commands preceded the disappearance of patch erasure; scripts then simplified execution. Neither establishes that the verifier selected adequate tests or judged every repair correctly.

### 4.5 Where the budget went

Across the 40 runs underlying Table 2, the coder consumed 69% of recorded agent time, the localizer 17%, and the verifier 14%; on the 21 validated tasks, the shares were 70%, 22%, and 8%. In the 40 runs, coder steps averaged 11.7 seconds and 400 generated tokens, and thirteen runs hit the six-minute cap, twelve with an edit already made.

Above 14,336 tokens the harness also truncated conversation history; the three earliest probed configurations experienced 9–15 localizer history resets per probe, followed by repeated searches.

These measurements identify generation time, exploration, and context retention as candidates for intervention. They do not establish that reducing reasoning tokens would improve resolution: faster decisions could also produce less complete repairs.

## 5. Evaluation validity and final outcomes

### 5.1 What the validation audit established

Before a score can describe an agent's repair ability, the environment must accept a known solution. We applied each reference patch and, separately, ran the same evaluation tests on unchanged code, both in the probes' local Kaggle subprocess sandbox, which sees the notebook's installed packages.

Seventy of 129 tasks passed: 41/48 rich, 29/67 fastapi, 0/13 requests, and 0/1 httpx. Of the remaining 59, 42 lacked test dependencies, 14 failed with the reference patch for other reasons, and three passed without a patch. The missing dependencies were `inline_snapshot` in 28 tasks, `dirty_equals` in nine, and `pytest-httpbin` fixtures in eight; three tasks required both of the first two. Of the fourteen other reference failures, thirteen suggest package-version or import-resolution differences, without confirming every cause; the last skipped a required test, which the evaluator correctly rejected.

Five original probe tasks failed validation. In one, the agent produced a patch substantively matching the reference in eight configurations, yet every evaluation rejected it. These findings concern the tested development environment and do not establish a corresponding failure in the private scoring environment.

### 5.2 Outcomes on validated tuning tasks

The final configuration resolved 8/21 tasks (38.1%; 95% Wilson interval 20.8–59.1%). These are tuning results from one run per task, not a held-out estimate or a comparison against earlier configurations. Three of the 21 tasks had also been run by this configuration in the original probe, which resolved all three; here it resolved one, producing a different patch for `rich_3718` and none for `fastapi_14873`. This is the study's only repeat-run evidence, and it shows the variation that single runs conceal.

**Table 3.** Observed outcomes across all 21 validated tuning tasks.

| Outcome | Tasks | Evidence |
|---|---|---|
| Passed evaluation | 8 | Required tests passed |
| No task-relevant edit | 6 | Five empty patches; one containing only a reproduction script |
| Incorrect or incomplete implementation | 4 | Behavioural failures or a timeout |
| Tests require text or names absent from the problem statement | 3 | An exact error message in two tasks; an unnamed module and class in one |

Of the six tasks without a relevant edit, four spent their coder budgets exploring; one of these also repeatedly supplied malformed read arguments and emitted tool-call syntax as ordinary text. The other two lost substantial time in localisation or reproductions; in `rich_4006`, both the localizer and coder hit 120-second command timeouts.

Among the four implementation failures, one was submitted as verified, one regression was detected late, and two never reached verification. The approved patch styled a panel's title but not its subtitle, a case absent from the verifier's checks. On `rich_3470`, an existing test exposed the regression with about 23 seconds remaining; the comparison script confirmed it with 17 seconds left.

The last three failures illustrate a further limit of reference validation. For `fastapi_14479`, the agent implemented the problem statement's example, "Query param … must be of one of the supported types"; tests required "Query parameter … must be one of the supported types". For `fastapi_15588`, the statement gives no message; the patch rejected line feeds in `id` and `event` values, but four of six failing cases failed only because tests match the phrase "must be a single line", and two because a bare carriage return was accepted. For `rich_3930`, tests import a module and a class that the statement never names, and the patch was also far from a complete implementation. The verifier approved the first two patches. We retain the failed benchmark outcomes while distinguishing them from behavioural defects alone. Reference validation shows that a task can be measured, not that its tests follow from the supplied specification.

## 6. Related work

**Interfaces and control.** SWE-agent (Yang et al., 2024) established the importance of the agent-computer interface. Sigdel and Baral (2026) examine tool schemas under interaction budgets, separating reduced misuse from task completion, as our call counts and traces do. Wang and Huang (2026) study a local agent harness with mechanisms against repetition and premature completion, and report substantial repeat-run variation.

**Procedures and compute.** Agentless (Xia et al., 2024) motivates structured workflows alongside open-ended agents. SWE-Gym (Pan et al., 2024) trains software engineering agents on trajectories, and Snell et al. (2024) study inference-time compute allocation. Our observations identify operational failures that such optimisation must account for.

**Evaluation.** SWE-bench (Jimenez et al., 2024) provides the issue-to-patch framework underlying our validation. Our contribution is an empirical account connecting control failures, repeated interface errors, and evaluation limits within one constrained agent system, not a new validation method.

## 7. Discussion and limitations

The observations motivate a hypothesis: tool feedback, response structure, and deterministic procedures may provide more effective control than prompt rules alone. Their roles differ: feedback can prompt a transition and a procedure can preserve a patch, but neither guarantees a correct implementation.

A controlled follow-up should vary instruction placement while holding content and timing fixed, compare alternative interfaces for the same edit, and test whether reserving time for editing and verification improves outcomes, measuring progress, patch preservation, and test resolution separately.

All observations come from one quantised model in one harness, so they cannot show whether the effects depend on model size. Several changes were bundled, each stage used single runs per configuration-task pair, and repeated calls are not independent error events. Validation reduced the eligible pool to 21 tuning and 49 held-out tasks from two repositories. The final evaluation used the tuning pool, and we cannot rule out pre-training exposure to the public repositories. An exploratory power simulation (`analysis/power_simulation.py`) motivates repeated runs for future paired comparisons.

## 8. Conclusion

This case study identifies three obstacles to effective coding agents: making progress within a budget, preserving work during verification, and measuring repairs correctly. Explicit instructions did not reliably prevent unproductive activity or destructive actions. Tool feedback and protected procedures were associated with useful changes in behaviour, but guaranteed neither progress nor correctness. These observations motivate controlled comparisons of prompt rules, tool feedback, response structure, and executable safeguards on validated tasks.

**Reproducibility.** Configuration snapshots, per-task results and patches, validation outcomes, notebook cells, analysis code, trace-derived metrics, and dated decision rules are in [the project repository](https://github.com/iHrushikesh/signals-not-rules). Traces, tasks, and test output contain competition data and are not redistributed.

## References

Jimenez, C. E., et al. (2024). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? ICLR 2024. arXiv:2310.06770.

Markowitz, E., et al. (2026). [Google - The Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent). Kaggle. [Dataset documentation](https://www.kaggle.com/competitions/gemma-4-developer-agent/data).

Pan, J., et al. (2024). Training Software Engineering Agents and Verifiers with SWE-Gym. arXiv:2412.21139.

Snell, C., et al. (2024). Scaling LLM Test-Time Compute Optimally Can Be More Effective than Scaling Model Parameters. arXiv:2408.03314.

Sigdel, A., Baral, R. (2026). Schema First Tool APIs for LLM Agents: A Controlled Study of Tool Misuse, Recovery, and Budgeted Performance. arXiv:2603.13404.

Wang, H., Huang, T. (2026). Mingbird: A Local-First Agent Harness Enabling Small Open Models to Complete Real Tasks. arXiv:2610.02001.

Xia, C. S., et al. (2024). Agentless: Demystifying LLM-based Software Engineering Agents. arXiv:2407.01489.

Yang, J., et al. (2024). SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024. arXiv:2405.15793.
