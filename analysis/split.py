"""Pre-registered, repo-stratified split of the dev tasks into tuning and held-out sets.

Run once, commit the output, and never re-draw it after looking at results:

    python -m analysis.split --tasks data/tasks.jsonl --seed 20261023 --out splits/dev_split.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import defaultdict
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


def load_task_ids(path: str) -> Dict[str, List[str]]:
    """Read tasks.jsonl and group instance ids by their `repo` field."""
    ids_by_repo: Dict[str, List[str]] = defaultdict(list)
    seen = set()
    with open(path) as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            iid = task["instance_id"]
            if iid in seen:
                raise ValueError(f"{path}:{lineno}: duplicate instance_id {iid}")
            seen.add(iid)
            ids_by_repo[task["repo"]].append(iid)
    return dict(ids_by_repo)


def stratified_split(
    ids_by_repo: Mapping[str, Sequence[str]], tune_frac: float, seed: int
) -> Tuple[List[str], List[str]]:
    """Shuffle each repo's ids with a seeded RNG and take round(len * tune_frac) for tuning."""
    if not 0 < tune_frac < 1:
        raise ValueError("tune_frac must be between 0 and 1")
    rng = random.Random(seed)
    tune: List[str] = []
    held: List[str] = []
    for repo in sorted(ids_by_repo):
        ids = sorted(ids_by_repo[repo])
        rng.shuffle(ids)
        k = round(len(ids) * tune_frac)
        tune.extend(ids[:k])
        held.extend(ids[k:])
    return sorted(tune), sorted(held)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Repo-stratified tuning/held-out split")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--tune-frac", type=float, default=1 / 3)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    ids_by_repo = load_task_ids(args.tasks)
    tune, held = stratified_split(ids_by_repo, args.tune_frac, args.seed)
    tune_set = set(tune)
    counts = {
        repo: {
            "total": len(ids),
            "tune": sum(1 for i in ids if i in tune_set),
            "heldout": sum(1 for i in ids if i not in tune_set),
        }
        for repo, ids in sorted(ids_by_repo.items())
    }
    payload = {
        "seed": args.seed,
        "tune_frac": args.tune_frac,
        "n_tune": len(tune),
        "n_heldout": len(held),
        "counts_by_repo": counts,
        "tune": tune,
        "heldout": held,
    }
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"wrote {args.out}: {len(tune)} tuning, {len(held)} held-out")
    for repo, c in counts.items():
        print(f"  {repo}: {c['tune']} tuning / {c['heldout']} held-out (of {c['total']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
