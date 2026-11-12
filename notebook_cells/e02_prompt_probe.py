# =============================================================================
# E02: system-prompt probe.  Pre-registration, written 2026-10-26 BEFORE any E02 run.
#
# Question: under fixed limits (12B model, no LoRA, 120 s command timeout, 25 tool
#   calls, 3 minutes, 50 turns), does the revised system prompt change agent
#   behavior on tuning tasks compared with the competition's sample prompt?
# Design: the same 12 tuning tasks, run once with PROMPT_VARIANT = "sample" and once
#   with "revised". 10 tasks are unseen (seeded stratified draw, seed 20261026,
#   from the 40 tuning tasks other than the two traced ones). The last 2 tasks
#   (fastapi_15661, fastapi_15588) inspired the revision, so report them separately.
# Primary metrics (per task, from traces): non-empty source patch; call index of
#   the first source edit; edits aimed at test files; failed edit calls; repeated reads.
# Secondary: resolved count and file-level hit. Not decisive at n = 12.
# Decision rule: adopt "revised" as the working prompt if, on the 10 unseen tasks, it
#   has at least as many non-empty source patches, fewer test-file edits and no more
#   failed edit calls than "sample". Resolved counts are reported, not used to decide.
# Caveats: one run per variant, so sampling noise is not separated and a difference of
#   one or two tasks is not evidence. The revision bundles several changes, so a gain
#   cannot be attributed to one of them. The async/graph fallback line rests on an
#   unverified second-hand report; Cell C checks the graph data directly.
#
# HOW TO USE (Kaggle notebook "Getting Started - Gemma 4 Developer Agent"):
#   1. Delete the cell you added for step 1 (the eval_config one). Cell A replaces it.
#   2. Paste CELL A as a new code cell directly after the cell under
#      "2. Competition Dataset and Sample Submission" (the one that sets MODEL_NAME).
#   3. In the cell under "5. Run Phase 1 Inference and Phase 2 Verification",
#      change one line:   SAMPLE_TASKS = tasks[:2]   ->   SAMPLE_TASKS = RUN_TASKS
#   4. Paste CELL C as the last cell, after the one that creates submission.zip.
#   5. Run 1: leave PROMPT_VARIANT = "sample". Save Version > Save & Run All,
#      name the version "E02-sample".
#   6. Run 2: set PROMPT_VARIANT = "revised". Save & Run All, name it "E02-revised".
#   7. Do not click Submit on these versions. Send me each run's log.
# =============================================================================


# ============================ CELL A ============================
PROMPT_VARIANT = "sample"   # "sample" = competition prompt (baseline); "revised" = agent/prompts/system.md
RUN_TASK_IDS = ["rich_3063", "rich_3521", "rich_3782", "rich_4006", "fastapi_11355", "fastapi_13920", "fastapi_14349", "fastapi_14479", "fastapi_14786", "requests_7433", "fastapi_15661", "fastapi_15588"]

import hashlib

(AGENT_DIR / 'eval_config.yaml').write_text(
    "evaluation:\n"
    "  timeout_seconds: 120\n"
    "  max_tool_calls: 25\n"
    "  max_time_minutes: 3\n"
    "  max_turns: 50\n",
    encoding='utf-8',
)

REVISED_PROMPT = r"""You are an expert software engineer fixing an issue in a repository that is checked out in /workspace. Hidden tests written for the correct fix decide whether you succeed, so the goal is a correct, small change to the library source code, made early.

## What is graded
- Whatever is in /workspace when your budget ends is graded, even if you never call submit_patch. A partial fix in a source file is worth more than a perfect plan with no edit.
- Edits to test files (tests/, test_*.py, *_test.py, conftest.py) and to config files (pytest.ini, pyproject.toml, setup.cfg, tox.ini) are discarded. Never edit them and never add tests to /workspace.
- New files in /workspace become part of your patch. Put scratch scripts in /tmp.

## Budget and milestones
- The task message lists your tool call, time and turn allowances. submit_patch and get_status do not use tool calls, and get_status shows what is left.
- Spend at most the first 40 percent of your tool calls locating the problem. Make your first edit to a source file by then, even if you are not fully sure, and refine it afterwards.
- Never read the same file range twice. read_file returns at most 150 lines, so ask for the exact line range you need.
- Older messages get summarized and you will forget them. Before each tool call, write one line with the target file, the function and your plan.

## Workflow
1. Find the code. Take file names, function names, class names, parameters and error messages from the problem statement. If none are given, use search_similar_code or one targeted grep for a key word. The code graph tools do not know every function: if a symbol is not found, or looks incomplete (async functions especially), use grep with run_command instead of repeating graph queries. If the problem statement is thin, infer the smallest sensible change from its title and the repository conventions, and make it instead of exploring further.
2. Edit the source. Follow the exact error strings, exception types, names and signatures given in the problem statement. Change as little as possible and do not reformat unrelated code. If the task is about example code that the docs include, edit the example source files, not only the prose.
3. Check it. Run only the single most relevant existing test file or test name, for example pytest path/to/test_file.py -k name. Never run bare pytest or a whole test suite. If an unrelated test fails or fixtures are missing, ignore it. If no relevant test exists, check with a short python3 -c command.
4. Finish. Remove any scratch file you put in /workspace, call submit_patch, confirm that patch_size and files_changed are above 0, and reply with a one or two sentence summary.

## Using edit_file correctly
- Copy old_string exactly from the latest read_file output, including indentation. Use one or two short consecutive lines that appear only once in the file.
- Write real line breaks. Never type the two characters backslash and n to mean a new line, and do not add extra escaping to quotes.
- If an edit fails once, do not resend similar text. Read the few lines around the spot with a narrow range and copy them again, or use write_file for a new file.
- To add code after an existing line, use that existing line as old_string, and repeat it at the start of new_string followed by your new code.

## Do not
- Do not search outside /workspace or try to install packages. The environment is offline.
- Do not finish without a non-empty patch to source files. Deciding that nothing needs to change is almost always wrong.
"""

if PROMPT_VARIANT == "revised":
    (AGENT_DIR / 'prompts' / 'system.md').write_text(REVISED_PROMPT, encoding='utf-8')
elif PROMPT_VARIANT != "sample":
    raise ValueError(f"PROMPT_VARIANT must be 'sample' or 'revised', got {PROMPT_VARIANT!r}")

_prompt_now = (AGENT_DIR / 'prompts' / 'system.md').read_text(encoding='utf-8')
print(f"E02 variant={PROMPT_VARIANT} system.md sha256={hashlib.sha256(_prompt_now.encode()).hexdigest()[:12]} chars={len(_prompt_now)}")
print((AGENT_DIR / 'eval_config.yaml').read_text())

_by_id = {t.instance_id: t for t in tasks}
_missing = [i for i in RUN_TASK_IDS if i not in _by_id]
assert not _missing, f"unknown task ids: {_missing}"
RUN_TASKS = [_by_id[i] for i in RUN_TASK_IDS]
print(f"E02 will run {len(RUN_TASKS)} tasks: {', '.join(RUN_TASK_IDS)}")


# ============================ CELL C ============================
# Paste as the LAST cell. Read-only; wrapped so it cannot break the run.
import collections, json, re, traceback
from pathlib import Path

_NINE = {'run_command', 'submit_patch', 'get_status', 'read_file', 'edit_file',
         'write_file', 'get_code_neighbors', 'search_similar_code', 'get_code_subgraph'}
_GRAPH = {'get_code_neighbors', 'search_similar_code', 'get_code_subgraph'}


def _e02_is_test_path(p):
    p = (p or '').replace('\\', '/').lstrip('./')
    name = p.rsplit('/', 1)[-1]
    return (p.startswith(('tests/', 'test/', 'testing/')) or '/tests/' in p or '/test/' in p
            or name.startswith('test_') or name.endswith('_test.py') or name == 'conftest.py')


def _e02_diff_files(diff):
    return {m.group(2) for m in re.finditer(r'^diff --git a/(\S+) b/(\S+)', diff or '', re.M)}


def _e02_trace_metrics(path):
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    calls, prev_pt, compactions = [], None, 0
    for s in d.get('steps', []):
        if s.get('source') != 'agent':
            continue
        pt = (s.get('metrics') or {}).get('prompt_tokens')
        if pt is not None:
            if prev_pt is not None and pt < 0.7 * prev_pt:
                compactions += 1
            prev_pt = pt
        try:
            status = json.loads((s.get('observation') or {}).get('content', '')).get('status')
        except Exception:
            status = None
        for c in s.get('tool_calls') or []:
            calls.append((c.get('function_name'), c.get('arguments') or {}, status))
    first_src_edit, src_ok, src_fail, test_edits, dup_reads, graph, other = None, 0, 0, 0, 0, 0, 0
    seen_reads = set()
    for i, (name, args, status) in enumerate(calls, start=1):
        if name in ('edit_file', 'write_file'):
            if _e02_is_test_path(args.get('filepath')):
                test_edits += 1
            else:
                first_src_edit = first_src_edit or i
                if status == 'ok':
                    src_ok += 1
                else:
                    src_fail += 1
        elif name == 'read_file':
            key = (args.get('filepath'), args.get('start_line'), args.get('end_line'))
            dup_reads += key in seen_reads
            seen_reads.add(key)
        if name in _GRAPH:
            graph += 1
        if name not in _NINE:
            other += 1
    return dict(calls=len(calls), first_src_edit=first_src_edit, src_ok=src_ok, src_fail=src_fail,
                test_edits=test_edits, dup_reads=dup_reads, compactions=compactions,
                graph=graph, other=other)


try:
    _res = WORKING_DIR / 'results'
    print('E02 results/ contains:', sorted(p.name for p in _res.iterdir()))
    _gold = {}
    for _line in open(TASKS_PATH, encoding='utf-8'):
        _r = json.loads(_line)
        _gold[_r['instance_id']] = _e02_diff_files(_r.get('patch', ''))
    _pred = {r['id']: r['prediction'] for r in predictions}
    print(f"E02 variant={PROMPT_VARIANT}")
    print('task | calls first_src_edit src_ok src_fail test_edits dup_reads compactions graph other | patch_chars patch_files hit')
    _tot = collections.Counter()
    for _tid in RUN_TASK_IDS:
        _tp = _res / 'traces' / f'trace_{_tid}.json'
        if not _tp.exists():
            print(f'{_tid} | no trace file')
            continue
        _m = _e02_trace_metrics(_tp)
        _p = _pred.get(_tid, 'NO_PATCH')
        _pf = _e02_diff_files(_p) if _p != 'NO_PATCH' else set()
        _hit = bool(_pf & _gold.get(_tid, set()))
        print(f"{_tid} | {_m['calls']} {_m['first_src_edit']} {_m['src_ok']} {_m['src_fail']} {_m['test_edits']} "
              f"{_m['dup_reads']} {_m['compactions']} {_m['graph']} {_m['other']} | {len(_p) if _p != 'NO_PATCH' else 0} "
              f"{sorted(_pf)} {_hit}")
        _tot['tasks'] += 1
        _tot['nonempty_patch'] += bool(_pf)
        _tot['source_edit_made'] += _m['first_src_edit'] is not None
        _tot['test_edit_calls'] += _m['test_edits']
        _tot['failed_src_edits'] += _m['src_fail']
        _tot['dup_reads'] += _m['dup_reads']
        _tot['hit'] += _hit
    print('E02 totals:', dict(_tot))
    print("E02 resolved per task: see the '-> resolved=' lines printed by the evaluation cell above.")
except Exception:
    traceback.print_exc()

# Graph check: do graph nodes include async functions? (second-hand report, unverified)
try:
    from swegemma import graph as sg
    _seen_repos = set()
    for _t in RUN_TASKS:
        if _t.repo in _seen_repos:
            continue
        _seen_repos.add(_t.repo)
        _g = sg.get_graph(repo_name=_t.repo, graph_dir=GRAPH_DIR, embeddings_dir=EMBEDDINGS_DIR,
                          base_commit=_t.base_commit)
        _keys, _n_def, _n_async = collections.Counter(), 0, 0
        for _, _data in _g.nodes(data=True):
            _keys.update(_data.keys())
            _texts = [v for v in _data.values() if isinstance(v, str)]
            if any(re.match(r'\s*async\s+def\s', x) for x in _texts):
                _n_async += 1
            elif any(re.match(r'\s*def\s', x) for x in _texts):
                _n_def += 1
        print(f"E02 graph {_t.repo}: nodes={_g.number_of_nodes()} sync_def_nodes={_n_def} "
              f"async_def_nodes={_n_async} node_attr_keys={dict(_keys.most_common(8))}")
        if _n_def + _n_async == 0:
            _first = next(iter(_g.nodes(data=True)), None)
            print('   inconclusive: no node attribute starts with def or async def. First node:', str(_first)[:300])
except Exception:
    traceback.print_exc()
