"""Rough power for a paired comparison of two agent builds on the same tasks.

Used for the power figures in docs/paper_draft.md (Limitations). Run with:
    uv run --with numpy python analysis/power_simulation.py
It needs numpy, which is not a project dependency. Runs in about a minute.

Assumptions (stated, not measured): each task has its own success probability, drawn from a
Beta distribution with mean 0.15 and concentration 2, so many tasks are nearly always or
nearly never solved (matches the probes, where the same tasks were solved in every build).
The adapter adds `delta` to every task's probability on the logit scale, scaled so the average
gain equals `delta`. Each arm runs `r` times per task; the test is a two-sided sign-flip
permutation test on per-task mean differences, alpha 0.05.
"""
import numpy as np
rng = np.random.default_rng(0)

def logit(p): return np.log(p / (1 - p))
def expit(x): return 1 / (1 + np.exp(-x))

def shift_for(base, delta):
    lo, hi = 0.0, 5.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if expit(logit(base) + mid).mean() - base.mean() < delta: lo = mid
        else: hi = mid
    return mid

def power(n, r, delta, mean=0.15, conc=2.0, sims=600, perms=400):
    a, b = mean * conc, (1 - mean) * conc
    hits = 0
    for _ in range(sims):
        base = np.clip(rng.beta(a, b, n), 1e-4, 1 - 1e-4)
        treat = expit(logit(base) + shift_for(base, delta))
        d = rng.binomial(r, treat) / r - rng.binomial(r, base) / r
        obs = abs(d.mean())
        signs = rng.choice([-1, 1], size=(perms, n))
        hits += (np.abs((signs * d).mean(axis=1)) >= obs).mean() <= 0.05
    return hits / sims

print(f"{'tasks':>6} {'runs/arm':>8} | {'+5 pts':>7} {'+10 pts':>8} {'+15 pts':>8}")
for n in (32, 49, 87, 129, 300):
    for r in (1, 3):
        print(f"{n:6d} {r:8d} | " + " ".join(f"{power(n, r, d):8.2f}" for d in (0.05, 0.10, 0.15)))
