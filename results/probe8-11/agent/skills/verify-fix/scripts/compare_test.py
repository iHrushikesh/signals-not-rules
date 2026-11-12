"""Run one existing test file with the fix and, if it fails, on the original code.

Usage: compare_test.py --test path/to/test_file.py

The original code is a separate copy made with git worktree, so the repository and
the fix are never touched, even if this script is stopped half way.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fixlib as lib

# Each pytest run gets this long. The harness stops a script after at most 120 s,
# and both runs must fit inside that.
RUN_TIMEOUT_SECONDS = 50
TAIL_LINES = 15


def run_pytest(root, test_path):
    """Run pytest on one file with root as the code to import. Returns (label, exit code, output tail)."""
    env = dict(os.environ)
    # Put this copy of the code first, for both a top-level package and a src/ layout.
    # WARNING: without this, python can import an installed copy of the package instead.
    env["PYTHONPATH"] = os.pathsep.join([root, os.path.join(root, "src")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test_path]
    try:
        done = subprocess.run(
            command, cwd=root, env=env, capture_output=True, text=True,
            errors="replace", timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "TIMED OUT", None, f"(no result after {RUN_TIMEOUT_SECONDS} s)"
    except OSError as exc:
        return "COULD NOT RUN", None, str(exc)
    output = (done.stdout + done.stderr).strip().splitlines()
    tail = "\n".join(output[-TAIL_LINES:])
    labels = {0: "PASSED", 1: "FAILED", 2: "ERROR BEFORE THE TESTS RAN", 5: "NO TESTS FOUND"}
    return labels.get(done.returncode, "ERROR"), done.returncode, tail


def original_copy(workspace):
    """Return a folder holding the code as it was before any edit, creating it once."""
    base = os.path.join(lib.shared_tmp(), "agent_original_code")
    if os.path.isdir(base) and os.listdir(base):
        return base, ""
    code, _, err = lib.git(workspace, "worktree", "add", "--detach", "-f", base, "HEAD", timeout=60)
    if code != 0:
        return None, err.strip()[:300]
    return base, ""


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--test", default="")
    args, extra = parser.parse_known_args()
    workspace = lib.find_workspace()
    if workspace is None:
        lib.no_workspace()
        return
    test_path = args.test.strip()
    if not test_path:
        # Also accept the path as a plain argument (positional_args, or args given as a list).
        test_path = next((a.strip() for a in extra if a.strip() and not a.startswith("-")), "")
    for prefix in ("/workspace/", "./"):
        if test_path.startswith(prefix):
            test_path = test_path[len(prefix):]
    if not test_path or os.path.isabs(test_path) or ".." in test_path.split("/"):
        print("ERROR: pass the test file as a path inside the repository, for example args {\"test\": \"tests/test_example.py\"}")
        return
    if not os.path.exists(os.path.join(workspace, test_path.split("::")[0])):
        print(f"ERROR: {test_path} does not exist in the repository")
        return

    label, code, tail = run_pytest(workspace, test_path)
    print(f"WITH THE FIX: {label}" + (f" (pytest exit code {code})" if code is not None else ""))
    print(lib.capped(tail, 1500))
    print()
    if code == 0:
        print("VERDICT: THE TEST FILE PASSES WITH THE FIX")
        return

    base, problem = original_copy(workspace)
    if base is None:
        print("ORIGINAL CODE: COULD NOT MAKE A COPY: " + problem)
        print("VERDICT: UNKNOWN. Judge the failure above yourself. Do not use git checkout.")
        return
    if not os.path.exists(os.path.join(base, test_path.split("::")[0])):
        print("ORIGINAL CODE: this test file does not exist there")
        print("VERDICT: UNKNOWN. Judge the failure above yourself. Do not use git checkout.")
        return
    base_label, base_code, base_tail = run_pytest(base, test_path)
    print(f"ORIGINAL CODE: {base_label}" + (f" (pytest exit code {base_code})" if base_code is not None else ""))
    print(lib.capped(base_tail, 1000))
    print()
    if base_code == 0:
        print("VERDICT: BROKEN BY THE FIX. This test passes on the original code and fails with the fix. The fix is not verified; name this test in the review.")
    elif base_code is None:
        print("VERDICT: UNKNOWN. The run on the original code did not finish. Judge the failure above yourself. Do not use git checkout.")
    else:
        print("VERDICT: FAILS WITH AND WITHOUT THE FIX. The fix did not cause this failure. Ignore it unless it tests the behavior the fix is meant to change.")


main()
