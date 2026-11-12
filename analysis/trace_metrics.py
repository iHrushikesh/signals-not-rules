"""Trace-derived numbers behind docs/paper_draft.md.

Standard library only. Two subcommands:

    python -m analysis.trace_metrics extract [--root results] [--out results/trace_metrics.csv]
    python -m analysis.trace_metrics report  [--root results] [--metrics results/trace_metrics.csv]

`extract` reads the execution traces (results/<run>/results/traces/trace_<task>.json) for the
tasks listed in each run's probe8/probe_tasks.csv and writes one row of counts per
(run, task, role), plus one row per task with role ALL. The traces are not in the public
repository because they contain competition task text; the metrics file holds only run names,
task ids, role names and integers, so it can be published.

`report` needs only the metrics file and the committed probe tables
(results/<run>/probe8/probe_tasks.csv, probe_agents.csv, predictions.csv). It prints every
trace-derived number in the paper, grouped by section, so a reader without the traces can
check them.

WARNING: the trace folders of probe8m-1 and probe13m-1 also hold stale traces from earlier
probe sets. Only tasks listed in a run's probe_tasks.csv are counted; do not glob the folder.

Definitions (the paper's wording in brackets):
- A call is malformed if a required argument is missing, an argument name the tool does not
  accept appears, or read_file's path carries line-number text [Section 4.3].
- Distinct calls count identical calls (same tool and arguments) by one role in one run once.
- The longest identical run is the longest stretch of consecutive identical calls in a task,
  across roles [Table 1, "Tasks with >10 consecutive identical calls"].
- An edit fails if the edit_file result does not report status ok [Section 4.2].
- An invocation is a contiguous stretch of steps by one role [Section 4.4, "per invocation"].
- A history reset is a drop in the localizer's prompt to under half its previous size from
  above 12,000 tokens, the harness compacting at 14,336 [Section 4.5].
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

csv.field_size_limit(sys.maxsize)

# Result folder -> (configuration, stage). Folders probe8-1 to probe8-4 predate the version
# banner; PLAN.md logs which build each ran. The others carry a fingerprint in version.txt.
RUNS: Dict[str, Tuple[int, str]] = {
    "probe8-1": (2, "original"),
    "probe8-2": (3, "original"),
    "probe8-3": (4, "original"),
    "probe8-4": (5, "original"),
    "probe8-6": (6, "original"),
    "probe8-7": (7, "original"),
    "probe8-8": (8, "original"),
    "probe8-10": (10, "original"),
    "probe8-11": (11, "original"),
    "probe8m-1": (11, "validated"),
    "probe13m-1": (11, "validated"),
}

ROLES = ("localizer", "coder", "verifier", "finalizer")

# Tool -> (required argument names, accepted argument names), from the harness tool schemas.
SCHEMAS: Dict[str, Tuple[frozenset, frozenset]] = {
    "run_command": (frozenset({"command"}), frozenset({"command"})),
    "read_file": (frozenset({"filepath"}), frozenset({"filepath", "start_line", "end_line"})),
    "edit_file": (
        frozenset({"filepath", "old_string", "new_string"}),
        frozenset({"filepath", "old_string", "new_string"}),
    ),
}
SHORT = {"run_command": "cmd", "read_file": "read", "edit_file": "edit"}

LINE_TEXT_IN_PATH = re.compile(r"start_line|end_line|[`,:]\s*\d")
PYTHON_RUN = re.compile(r"(^|[\s;&|(])(python3?|pytest)\b")
GIT_REVERT = re.compile(r"\bgit\s+(checkout|stash|reset|restore|clean)\b")
BUDGET_WARNING = "budget_warning"

COLUMNS = [
    "run", "configuration", "stage", "task", "role",
    "tool_calls", "distinct_calls", "longest_identical_run", "invocations",
    "first_call_at", "last_call_at", "budget_warning_at",
    "cmd_calls", "cmd_malformed", "cmd_distinct", "cmd_distinct_malformed",
    "read_calls", "read_malformed", "read_distinct", "read_distinct_malformed",
    "edit_calls", "edit_malformed", "edit_distinct", "edit_distinct_malformed",
    "edit_ok", "edit_failed", "get_status_calls", "python_runs", "git_revert_commands",
    "history_resets",
]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def is_malformed(tool: str, args: object) -> bool:
    """True if a call to one of the three file and shell tools is malformed (see module doc)."""
    if tool not in SCHEMAS:
        raise ValueError(f"no schema for {tool}")
    if not isinstance(args, dict):
        return True
    required, accepted = SCHEMAS[tool]
    keys = set(args)
    if not required <= keys or keys - accepted:
        return True
    return tool == "read_file" and bool(LINE_TEXT_IN_PATH.search(str(args.get("filepath", ""))))


def call_key(tool: str, args: object) -> str:
    return tool + " " + json.dumps(args, sort_keys=True)


def longest_identical_run(keys: Sequence[str]) -> int:
    best = run = 0
    prev = None
    for k in keys:
        run = run + 1 if k == prev else 1
        prev = k
        best = max(best, run)
    return best


def result_status(observation: str) -> Optional[str]:
    m = re.search(r'\\?"status\\?":\s*\\?"(\w+)', observation)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Extraction from traces
# ---------------------------------------------------------------------------


def _prompt_tokens(step: dict) -> Optional[int]:
    for tc in step.get("tool_calls", []) or []:
        usage = (tc.get("extra") or {}).get("usage") or {}
        if usage.get("prompt_tokens"):
            return int(usage["prompt_tokens"])
    metrics = step.get("metrics") or {}
    return int(metrics["prompt_tokens"]) if metrics.get("prompt_tokens") else None


def task_rows(run: str, task: str, steps: List[dict]) -> List[Dict[str, object]]:
    """One row per role that acted, plus a role ALL row, for one task's trace steps."""
    configuration, stage = RUNS[run]
    calls = []  # (index, role, tool, args, observation)
    invocations: Dict[str, int] = defaultdict(int)
    prompts: Dict[str, List[int]] = defaultdict(list)
    prev_role = None
    for step in steps:
        role = (step.get("extra") or {}).get("author")
        if role not in ROLES:
            continue
        if role != prev_role:
            invocations[role] += 1
        prev_role = role
        tokens = _prompt_tokens(step)
        if tokens is not None:
            prompts[role].append(tokens)
        for tc in step.get("tool_calls", []) or []:
            calls.append((len(calls) + 1, role, tc.get("function_name"), tc.get("arguments"),
                          str(step.get("observation", ""))))

    warning_at = next((i for i, _, _, _, obs in calls if BUDGET_WARNING in obs), "")

    def summarise(role: str, subset: list) -> Dict[str, object]:
        row: Dict[str, object] = {c: 0 for c in COLUMNS}
        row.update(run=run, configuration=configuration, stage=stage, task=task, role=role)
        keys = [call_key(tool, args) for _, _, tool, args, _ in subset]
        row["tool_calls"] = len(subset)
        row["distinct_calls"] = len(set(keys))
        row["longest_identical_run"] = longest_identical_run(keys)
        row["invocations"] = sum(invocations.values()) if role == "ALL" else invocations[role]
        row["first_call_at"] = subset[0][0] if subset else ""
        row["last_call_at"] = subset[-1][0] if subset else ""
        row["budget_warning_at"] = warning_at
        seen = {}
        for (_, _, tool, args, obs), key in zip(subset, keys):
            if tool in SCHEMAS:
                p = SHORT[tool]
                bad = is_malformed(tool, args)
                row[f"{p}_calls"] += 1
                row[f"{p}_malformed"] += bad
                if key not in seen:
                    seen[key] = bad
                    row[f"{p}_distinct"] += 1
                    row[f"{p}_distinct_malformed"] += bad
                if tool == "edit_file":
                    ok = result_status(obs) == "ok"
                    row["edit_ok"] += ok
                    row["edit_failed"] += not ok
                if tool == "run_command" and isinstance(args, dict):
                    command = str(args.get("command", ""))
                    row["python_runs"] += bool(PYTHON_RUN.search(command))
                    row["git_revert_commands"] += bool(GIT_REVERT.search(command))
            elif tool == "get_status":
                row["get_status_calls"] += 1
        if role in ("localizer", "ALL"):
            series = prompts["localizer"]
            row["history_resets"] = sum(
                1 for a, b in zip(series, series[1:]) if a > 12000 and b < a * 0.5)
        return row

    rows = [summarise("ALL", calls)]
    for role in ROLES:
        subset = [c for c in calls if c[1] == role]
        if subset or invocations[role]:
            rows.append(summarise(role, subset))
    return rows


def run_tasks(root: str, run: str) -> List[str]:
    with open(os.path.join(root, run, "probe8", "probe_tasks.csv"), newline="") as f:
        return [r["id"] for r in csv.DictReader(f)]


def extract(root: str, out: str) -> int:
    rows: List[Dict[str, object]] = []
    for run in RUNS:
        for task in run_tasks(root, run):
            path = os.path.join(root, run, "results", "traces", f"trace_{task}.json")
            with open(path) as f:
                rows.extend(task_rows(run, task, json.load(f)["steps"]))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows for {len({(r['run'], r['task']) for r in rows})} task runs to {out}")
    return 0


# ---------------------------------------------------------------------------
# Report from the metrics file and the committed probe tables
# ---------------------------------------------------------------------------


def load_metrics(path: str) -> List[Dict[str, object]]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in COLUMNS:
            if c not in ("run", "stage", "task", "role") and r[c] != "":
                r[c] = int(r[c])
    return rows


def _table(root: str, run: str, name: str) -> List[Dict[str, str]]:
    with open(os.path.join(root, run, "probe8", name), newline="") as f:
        return list(csv.DictReader(f))


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else f"{a}/0"


def report(root: str, metrics_path: str) -> int:
    m = load_metrics(metrics_path)

    def rows(runs: Iterable[str], role: str) -> List[Dict[str, object]]:
        runs = set(runs)
        return [r for r in m if r["run"] in runs and r["role"] == role]

    def by_config(config: int, role: str, stage: str = "original") -> List[Dict[str, object]]:
        return [r for r in m if r["configuration"] == config and r["stage"] == stage and r["role"] == role]

    original = [run for run, (_, s) in RUNS.items() if s == "original"]
    validated = [run for run, (_, s) in RUNS.items() if s == "validated"]
    table2 = ["probe8-6", "probe8-7", "probe8-8", "probe8-10", "probe8-11"]
    out = []
    p = out.append

    p(f"Task runs in the metrics file: {len({(r['run'], r['task']) for r in m})} "
      f"({len(rows(original, 'ALL'))} original, {len(rows(validated, 'ALL'))} validated); "
      f"distinct tasks: {len({r['task'] for r in m})}")

    p("\nTable 1, tasks with a run of more than 10 identical calls (/8), and the longest run:")
    for run in original:
        a = rows([run], "ALL")
        p(f"  configuration {RUNS[run][0]:2d}: {sum(r['longest_identical_run'] > 10 for r in a)}"
          f"   longest {max(r['longest_identical_run'] for r in a)}")

    p("\nSection 4.1, configuration 3:")
    a3, l3 = by_config(3, "ALL"), by_config(3, "localizer")
    p(f"  get_status calls in 8 tasks: {sum(r['get_status_calls'] for r in a3)}")
    p(f"  longest identical runs per task: {sorted(r['longest_identical_run'] for r in a3)}")
    big = max(l3, key=lambda r: r["tool_calls"])
    p(f"  largest localizer: {big['tool_calls']} calls, {big['distinct_calls']} distinct ({big['task']})")
    created = []
    for r in _table(root, "probe8-2", "predictions.csv"):
        if re.search(r"^new file mode", r["prediction"], re.M):
            created.append(r["id"])
    p(f"  patches holding new files the agent created: {len(created)} {created}")

    p("\nSection 4.1, configuration 4, localizers that received the budget warning:")
    for r in by_config(4, "localizer"):
        if r["budget_warning_at"] != "" and r["first_call_at"] != "" and r["first_call_at"] <= r["budget_warning_at"] <= r["last_call_at"]:
            p(f"  {r['task']:15s} longest identical run {r['longest_identical_run']:3d}  warning at call {r['budget_warning_at']}"
              f"  localizer's last call {r['last_call_at']}")
    p(f"  localizer python runs: {sum(r['python_runs'] for r in by_config(4, 'localizer'))}")

    p("\nSection 4.2, sampling:")
    for c in (4, 5):
        loc = by_config(c, "localizer")
        p(f"  configuration {c}: localizer calls {sum(r['tool_calls'] for r in loc)}, "
          f"longest localizer run {max(r['longest_identical_run'] for r in loc)}")
    for c in (6, 7):
        cod = by_config(c, "coder")
        failed, total = sum(r["edit_failed"] for r in cod), sum(r["edit_calls"] for r in cod)
        p(f"  configuration {c}: failed coder edit calls {failed}/{total}")
    av = rows(validated, "ALL")
    lv = rows(validated, "localizer")
    p(f"  validated stage: longest identical run {max(r['longest_identical_run'] for r in av)}; "
      f"tasks where the localizer ran python or pytest: {sum(r['python_runs'] > 0 for r in lv)}; "
      f"most localizer shell commands in one task: {max(r['cmd_calls'] for r in lv)}")

    for label, runs in (("Table 2, original probe, configurations 6, 7, 8, 10, 11", table2),
                        ("Section 4.3, validated stage", validated)):
        # Role rows, not ALL rows: distinct calls are counted per role within a run.
        a = [r for r in m if r["run"] in set(runs) and r["role"] != "ALL"]
        p(f"\n{label}: {len(rows(runs, 'ALL'))} runs")
        for tool, short in SHORT.items():
            raw = _pct(sum(r[f"{short}_malformed"] for r in a), sum(r[f"{short}_calls"] for r in a))
            dist = _pct(sum(r[f"{short}_distinct_malformed"] for r in a),
                        sum(r[f"{short}_distinct"] for r in a))
            p(f"  {tool:12s} raw {raw:20s} distinct {dist}")

    p("\nSection 4.4, verifier:")
    for c in (7, 8, 10, 11):
        v = by_config(c, "verifier")
        reached = [r for r in v if r["invocations"] > 0]
        reverted = [r["task"] for r in reached if r["git_revert_commands"] > 0]
        calls = sum(r["tool_calls"] for r in reached)
        inv = sum(r["invocations"] for r in reached)
        p(f"  configuration {c:2d}: reached {len(reached)} tasks, git revert commands in {len(reverted)} {reverted}; "
          f"calls per invocation {calls / inv:.1f}; longest verifier run {max((r['longest_identical_run'] for r in reached), default=0)}")

    p("\nSection 4.5, time and caps (probe_agents.csv, probe_tasks.csv):")
    for label, runs in (("40 original runs", table2), ("21 validated tasks", validated)):
        secs: Dict[str, float] = defaultdict(float)
        for run in runs:
            keep = {t for t in run_tasks(root, run)}
            for r in _table(root, run, "probe_agents.csv"):
                if r["id"] in keep:
                    secs[r["agent"]] += float(r["model_s"]) + float(r["tool_s"])
        total = sum(secs.values())
        p(f"  {label}: " + ", ".join(f"{k} {100 * v / total:.0f}%" for k, v in
                                     sorted(secs.items(), key=lambda kv: -kv[1]) if v))
    model = tool_s = events = tokens = 0.0
    for run in table2:
        for r in _table(root, run, "probe_agents.csv"):
            if r["agent"] == "coder":
                model += float(r["model_s"]); tool_s += float(r["tool_s"])
                events += int(r["llm_events"]); tokens += int(r["completion_tokens"])
    p(f"  coder, per model call: {model / events:.2f} s generating, {(model + tool_s) / events:.2f} s with tool time, "
      f"{tokens / events:.0f} generated tokens")
    capped = edited = 0
    coder_ok = {(r["run"], r["task"]): r["edit_ok"] for r in rows(table2, "coder")}
    for run in table2:
        for r in _table(root, run, "probe_tasks.csv"):
            if "session timeout" in r["error"]:
                capped += 1
                edited += coder_ok.get((run, r["id"]), 0) > 0
    p(f"  runs that hit the six-minute cap: {capped}, with a successful edit before it: {edited}")
    p("  localizer history resets per probe: " + ", ".join(
        f"configuration {RUNS[run][0]} {sum(r['history_resets'] for r in rows([run], 'localizer'))}"
        for run in ("probe8-1", "probe8-2", "probe8-3")))
    speed = _table(root, "probe8-1", "probe_agents.csv")
    p(f"  Section 2, generation speed, configuration 2: "
      f"{sum(int(r['completion_tokens']) for r in speed) / sum(float(r['model_s']) for r in speed):.1f} tokens/s")

    print("\n".join(out))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="traces -> metrics CSV (needs the unpublished traces)")
    e.add_argument("--root", default="results")
    e.add_argument("--out", default=os.path.join("results", "trace_metrics.csv"))
    r = sub.add_parser("report", help="metrics CSV + committed probe tables -> the paper's numbers")
    r.add_argument("--root", default="results")
    r.add_argument("--metrics", default=os.path.join("results", "trace_metrics.csv"))
    args = parser.parse_args(argv)
    if args.cmd == "extract":
        return extract(args.root, args.out)
    return report(args.root, args.metrics)


if __name__ == "__main__":
    sys.exit(main())
