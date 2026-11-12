"""Paired statistics and localization metrics for comparing agent configurations.

Standard library only, so it runs on Kaggle, a GCP VM or a laptop.

Results CSV, one row per task attempt:

    config,run,instance_id,resolved[,wall_seconds,...]

`resolved` is 1/0 (true/false, pass/fail also accepted).

Usage:

    python -m analysis.stats summary results.csv
    python -m analysis.stats compare results.csv --a s1-12b --b s2-12b [--run-a r1 --run-b r1]
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import re
import sys
from collections import defaultdict
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

Z95 = 1.959963984540054

# ---------------------------------------------------------------------------
# Rates and paired comparisons
# ---------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = Z95) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    # At 0/n and n/n the bound is exactly 0 or 1; set it directly to avoid rounding error.
    lo = 0.0 if successes == 0 else max(0.0, center - half)
    hi = 1.0 if successes == n else min(1.0, center + half)
    return lo, hi


def mcnemar_exact(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts.

    a_only: tasks config A solved and config B did not.
    b_only: tasks config B solved and config A did not.
    """
    if a_only < 0 or b_only < 0:
        raise ValueError("counts must be non-negative")
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1))  # exact integers
    return min(1.0, 2 * tail / (2 ** n))


def paired_outcomes(a: Mapping[str, bool], b: Mapping[str, bool]) -> List[Tuple[str, bool, bool]]:
    """Align two per-task outcome maps on their common instance ids."""
    common = sorted(set(a) & set(b))
    if not common:
        raise ValueError("the two runs share no instance ids")
    return [(i, bool(a[i]), bool(b[i])) for i in common]


def paired_bootstrap_ci(
    pairs: Sequence[Tuple[str, bool, bool]],
    reps: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Percentile bootstrap CI for (rate_B - rate_A), resampling tasks with their pairs intact."""
    if not pairs:
        raise ValueError("no pairs")
    rng = random.Random(seed)
    per_task = [int(y) - int(x) for _, x, y in pairs]
    n = len(per_task)
    stats = []
    for _ in range(reps):
        total = 0
        for _ in range(n):
            total += per_task[rng.randrange(n)]
        stats.append(total / n)
    stats.sort()
    lo_idx = int(math.floor((alpha / 2) * reps))
    hi_idx = int(math.ceil((1 - alpha / 2) * reps)) - 1
    return stats[lo_idx], stats[hi_idx]


def compare(
    a: Mapping[str, bool],
    b: Mapping[str, bool],
    reps: int = 10000,
    seed: int = 0,
) -> Dict[str, object]:
    """Paired comparison of config B against config A on their shared tasks."""
    pairs = paired_outcomes(a, b)
    n = len(pairs)
    solved_a = sum(1 for _, x, _ in pairs if x)
    solved_b = sum(1 for _, _, y in pairs if y)
    a_only = sum(1 for _, x, y in pairs if x and not y)
    b_only = sum(1 for _, x, y in pairs if y and not x)
    return {
        "n": n,
        "solved_a": solved_a,
        "solved_b": solved_b,
        "rate_a": solved_a / n,
        "rate_b": solved_b / n,
        "wilson_a": wilson_interval(solved_a, n),
        "wilson_b": wilson_interval(solved_b, n),
        "diff_b_minus_a": (solved_b - solved_a) / n,
        "ci95_diff": paired_bootstrap_ci(pairs, reps=reps, seed=seed),
        "a_only": a_only,
        "b_only": b_only,
        "mcnemar_p": mcnemar_exact(a_only, b_only),
        "only_in_a": len(set(a) - set(b)),
        "only_in_b": len(set(b) - set(a)),
    }


def holm(pvalues: Mapping[str, float]) -> Dict[str, float]:
    """Holm step-down adjusted p-values for a family of pre-registered comparisons."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: Dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted


# ---------------------------------------------------------------------------
# Localization: which files a diff touches
# ---------------------------------------------------------------------------

_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _clean_path(raw: str) -> Optional[str]:
    path = raw.split("\t", 1)[0].strip()
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1]
    if path == "/dev/null" or not path:
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path


def files_in_diff(diff_text: Optional[str]) -> Set[str]:
    """Return the set of file paths a unified git diff touches.

    Tracks hunk line counts, so removed lines that start with '--' or added lines
    that start with '++' are not mistaken for file headers. Renames and mode-only
    changes without ---/+++ headers fall back to the path in the `diff --git` line.
    """
    files: Set[str] = set()
    if not diff_text or diff_text.strip() == "NO_PATCH":
        return files
    old_left = new_left = 0
    git_target: Optional[str] = None
    headers_seen = False

    def flush() -> None:
        if git_target is not None and not headers_seen:
            files.add(git_target)

    for line in diff_text.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("\\"):  # "\ No newline at end of file"
                continue
            tag = line[:1] if line else " "
            if tag == " ":
                old_left -= 1
                new_left -= 1
                continue
            if tag == "-":
                old_left -= 1
                continue
            if tag == "+":
                new_left -= 1
                continue
            old_left = new_left = 0  # malformed hunk: fall through and parse as a header
        m = _HUNK.match(line)
        if m:
            old_left = int(m.group(2)) if m.group(2) is not None else 1
            new_left = int(m.group(4)) if m.group(4) is not None else 1
            continue
        m = _DIFF_GIT.match(line)
        if m:
            flush()
            git_target = m.group(2)
            headers_seen = False
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            headers_seen = True
            path = _clean_path(line[4:])
            if path is not None:
                files.add(path)
    flush()
    return files


def localization(pred_diff: Optional[str], gold_patch: Optional[str]) -> Dict[str, object]:
    """File-level localization of a predicted diff against the reference patch."""
    gold = files_in_diff(gold_patch)
    pred = files_in_diff(pred_diff)
    hit = pred & gold
    return {
        "gold_files": len(gold),
        "pred_files": len(pred),
        "recall": (len(hit) / len(gold)) if gold else None,
        "precision": (len(hit) / len(pred)) if pred else None,
        "hit": bool(hit),
        "extra_files": len(pred - gold),
    }


# ---------------------------------------------------------------------------
# Results loading and CLI
# ---------------------------------------------------------------------------

_TRUE = {"1", "true", "yes", "pass", "passed", "resolved"}
_FALSE = {"0", "false", "no", "fail", "failed", "unresolved"}

Results = Dict[str, Dict[str, Dict[str, bool]]]  # config -> run -> instance_id -> resolved


def load_results(path: str) -> Results:
    out: Dict[str, Dict[str, Dict[str, bool]]] = defaultdict(lambda: defaultdict(dict))
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"config", "run", "instance_id", "resolved"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for lineno, row in enumerate(reader, start=2):
            value = (row["resolved"] or "").strip().lower()
            if value in _TRUE:
                resolved = True
            elif value in _FALSE:
                resolved = False
            else:
                raise ValueError(f"{path}:{lineno}: unrecognized resolved value {row['resolved']!r}")
            runs = out[row["config"]][row["run"]]
            if row["instance_id"] in runs:
                raise ValueError(f"{path}:{lineno}: duplicate {row['config']}/{row['run']}/{row['instance_id']}")
            runs[row["instance_id"]] = resolved
    return {cfg: dict(runs) for cfg, runs in out.items()}


def _pick_run(results: Results, config: str, run: Optional[str]) -> Tuple[str, Dict[str, bool]]:
    if config not in results:
        raise SystemExit(f"config {config!r} not found; have {sorted(results)}")
    runs = results[config]
    if run is None:
        if len(runs) != 1:
            raise SystemExit(f"config {config!r} has runs {sorted(runs)}; pass --run-a/--run-b")
        run = next(iter(runs))
    if run not in runs:
        raise SystemExit(f"run {run!r} not found for {config!r}; have {sorted(runs)}")
    return run, runs[run]


def _fmt_ci(ci: Tuple[float, float]) -> str:
    return f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    # argparse treats '%' in help text as a format character, so it must be written '%%'.
    p_sum = sub.add_parser("summary", help="per config/run resolution rate with Wilson 95%% CI")
    p_sum.add_argument("results")

    p_cmp = sub.add_parser("compare", help="paired comparison of two configs")
    p_cmp.add_argument("results")
    p_cmp.add_argument("--a", required=True)
    p_cmp.add_argument("--b", required=True)
    p_cmp.add_argument("--run-a")
    p_cmp.add_argument("--run-b")
    p_cmp.add_argument("--reps", type=int, default=10000)
    p_cmp.add_argument("--seed", type=int, default=0)

    args = parser.parse_args(argv)
    results = load_results(args.results)

    if args.cmd == "summary":
        print(f"{'config':<28} {'run':<8} {'n':>4} {'solved':>6} {'rate':>6}  wilson95")
        for cfg in sorted(results):
            for run in sorted(results[cfg]):
                outcomes = results[cfg][run]
                n = len(outcomes)
                k = sum(outcomes.values())
                lo, hi = wilson_interval(k, n)
                print(f"{cfg:<28} {run:<8} {n:>4} {k:>6} {k / n:>6.3f}  [{lo:.3f}, {hi:.3f}]")
        return 0

    run_a, a = _pick_run(results, args.a, args.run_a)
    run_b, b = _pick_run(results, args.b, args.run_b)
    r = compare(a, b, reps=args.reps, seed=args.seed)
    print(f"A = {args.a}/{run_a}   B = {args.b}/{run_b}   shared tasks n = {r['n']}")
    if r["only_in_a"] or r["only_in_b"]:
        print(f"  warning: {r['only_in_a']} tasks only in A, {r['only_in_b']} only in B (excluded)")
    print(f"  A solved {r['solved_a']} ({r['rate_a']:.3f}), B solved {r['solved_b']} ({r['rate_b']:.3f})")
    print(f"  B - A = {r['diff_b_minus_a']:+.3f}, paired bootstrap 95% CI {_fmt_ci(r['ci95_diff'])}")
    print(f"  discordant: A-only {r['a_only']}, B-only {r['b_only']}; exact McNemar p = {r['mcnemar_p']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
