# =============================================================================
# Gold-patch validation of the dev tasks. No model is used, so run it on CPU.
#
# For each task it runs the harness's own Phase 2 verification twice, in the same
# subprocess sandbox the probe notebook uses:
#   with the reference fix (task.patch): a measurable task must pass;
#   with no patch:                       a measurable task must fail.
# A task that fails with the reference fix cannot be solved in this environment,
# so an agent's failure there says nothing about the agent.
#
# HOW TO USE
#   1. New notebook (no clone needed). Accelerator: None (CPU). Internet: off.
#   2. Add inputs: the competition data and the wheelhouse dataset (as in the starter).
#   3. Cell 1: the starter notebook's section 1 install cell, unchanged.
#   4. Cell 2: this cell. Run all.
#   5. Download /kaggle/working/gold_results.zip into results/gold-1/.
# =============================================================================
import asyncio
import collections
import concurrent.futures
import json
import os
import re
import time
import traceback
import zipfile
from pathlib import Path

import pandas as pd
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.deduplication import resolve_task_snapshot_paths
from swegemma.evaluate import Evaluator
from swegemma.harness.verification import verify_task
from swegemma.models import load_tasks

# ---- Settings ----------------------------------------------------------------------------
# The environment variables exist only for a local test run; on Kaggle the defaults apply.
DATA_DIR = Path(os.environ.get('GOLD_DATA_DIR', '/kaggle/input/competitions/gemma-4-developer-agent'))
WORKING_DIR = Path(os.environ.get('GOLD_WORKING_DIR', '/kaggle/working'))
# 'all' for every dev task, or a list of instance ids.
TASK_IDS = json.loads(os.environ['GOLD_TASK_IDS']) if 'GOLD_TASK_IDS' in os.environ else 'all'
# Also run each task with no patch. Doubles the run time; set False for a quick pass.
CHECK_WITHOUT_FIX = True
VERIFY_TIMEOUT_SECONDS = 300
# ------------------------------------------------------------------------------------------

OUT_DIR = WORKING_DIR / 'gold'
TEST_OUT_DIR = OUT_DIR / 'test_output'
TEST_OUT_DIR.mkdir(parents=True, exist_ok=True)
WHEELS_DIR = DATA_DIR / 'wheels'

MISSING_MODULE = re.compile(r"No module named '([\w.]+)'")
MISSING_FIXTURE = re.compile(r"fixture '(\w+)' not found|recursive dependency involving fixture '(\w+)'")
SUMMARY_LINE = re.compile(r'^=*\s*(\d+ (passed|failed|error|errors|skipped)[^=]*?)\s*=*$', re.M)


def run_sync(coro):
    """Run a coroutine to completion, also inside a notebook's running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def summarize(output):
    """Pull the facts we need out of pytest's output."""
    modules = sorted(set(MISSING_MODULE.findall(output)))
    fixtures = sorted({a or b for a, b in MISSING_FIXTURE.findall(output)})
    summaries = SUMMARY_LINE.findall(output)
    return {
        'missing_modules': ' '.join(modules),
        'missing_fixtures': ' '.join(fixtures),
        'summary': summaries[-1][0] if summaries else '',
    }


def verify_once(evaluator, config, task, patch_text, label):
    snapshot, base, patch_path = resolve_task_snapshot_paths(config.snapshots_dir, task.instance_id, task.repo)
    row = {'id': task.instance_id, 'repo': task.repo, 'run': label}
    if not snapshot.exists():
        row.update(resolved=None, exit_code=None, error=f'snapshot not found: {snapshot.name}', seconds=0.0)
        return row
    start = time.perf_counter()
    try:
        result = run_sync(verify_task(
            evaluator.docker, config, task, snapshot,
            base_snapshot_path=base, patch_path=patch_path,
            agent_patch=patch_text, start_time=start,
        ))
        output = result.test_output or ''
        (TEST_OUT_DIR / f'{task.instance_id}.{label}.txt').write_text(output, encoding='utf-8')
        row.update(resolved=bool(result.resolved), exit_code=result.test_exit_code,
                   error=(result.error or '')[:300], seconds=round(time.perf_counter() - start, 1))
        row.update(summarize(output))
    except Exception as exc:
        row.update(resolved=None, exit_code=None, error=f'{type(exc).__name__}: {exc}'[:300],
                   seconds=round(time.perf_counter() - start, 1))
        traceback.print_exc()
    return row


def classify(gold, none):
    """One verdict per task, from the run with the reference fix and the run without a fix."""
    if gold['resolved'] is None:
        return 'NOT RUN'
    if not gold['resolved']:
        if gold.get('missing_modules') or gold.get('missing_fixtures'):
            return 'UNMEASURABLE: missing test dependency'
        return 'UNMEASURABLE: reference fix fails'
    if none is not None and none['resolved']:
        return 'UNMEASURABLE: passes without a fix'
    return 'MEASURABLE'


config = EvalConfig(
    tasks_path=DATA_DIR / 'tasks.jsonl',
    snapshots_dir=DATA_DIR / 'snapshots',
    results_dir=OUT_DIR / 'results',
    submission_dir=OUT_DIR,          # required by EvalConfig; no agent runs here
    models=ModelRegistry(),
    sandbox='subprocess',
    verification_timeout_seconds=VERIFY_TIMEOUT_SECONDS,
    wheels_dir=WHEELS_DIR if WHEELS_DIR.is_dir() else None,
    display_mode='quiet',
)
evaluator = Evaluator(config)

all_tasks = load_tasks(config.tasks_path)
selected = all_tasks if TASK_IDS == 'all' else [t for t in all_tasks if t.instance_id in set(TASK_IDS)]
print(f'Validating {len(selected)} tasks; runs per task: {2 if CHECK_WITHOUT_FIX else 1}')

rows, verdicts = [], []
for i, task in enumerate(selected, 1):
    gold = verify_once(evaluator, config, task, task.patch, 'gold')
    none = verify_once(evaluator, config, task, '', 'none') if CHECK_WITHOUT_FIX else None
    rows += [r for r in (gold, none) if r is not None]
    verdict = classify(gold, none)
    verdicts.append({'id': task.instance_id, 'repo': task.repo, 'verdict': verdict,
                     'gold_resolved': gold['resolved'], 'none_resolved': none['resolved'] if none else None,
                     'missing_modules': gold.get('missing_modules', ''), 'missing_fixtures': gold.get('missing_fixtures', ''),
                     'gold_summary': gold.get('summary', ''), 'error': gold.get('error', '')})
    print(f"[{i}/{len(selected)}] {task.instance_id}: {verdict} | gold {gold.get('summary') or gold.get('error')}"
          + (f" | no fix {none.get('summary') or none.get('error')}" if none else ''))

runs_df = pd.DataFrame(rows)
verdict_df = pd.DataFrame(verdicts)
runs_df.to_csv(OUT_DIR / 'gold_runs.csv', index=False)
verdict_df.to_csv(OUT_DIR / 'gold_verdicts.csv', index=False)

print('\nVERDICTS BY REPO')
print(verdict_df.groupby(['repo', 'verdict']).size().unstack(fill_value=0).to_string())
missing = collections.Counter(m for s in verdict_df['missing_modules'] for m in s.split())
missing.update(f'fixture:{f}' for s in verdict_df['missing_fixtures'] for f in s.split())
print('\nMISSING TEST DEPENDENCIES (tasks affected):', dict(missing.most_common()))
print('MEASURABLE TASKS:', (verdict_df['verdict'] == 'MEASURABLE').sum(), 'of', len(verdict_df))

zip_path = WORKING_DIR / 'gold_results.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for f in sorted(OUT_DIR.rglob('*')):
        if f.is_file() and 'results' not in f.relative_to(OUT_DIR).parts:
            archive.write(f, Path('gold') / f.relative_to(OUT_DIR))
print(f'Wrote {zip_path} ({zip_path.stat().st_size // 1024} KiB)')
