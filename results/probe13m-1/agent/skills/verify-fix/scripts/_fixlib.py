"""Shared helpers for the verify-fix skill scripts. Standard library only.

How these scripts run (google-adk 1.36.1 and the competition harness):
ADK copies the skill's files into a temporary folder, changes into it and runs the
script there. The harness executes that wrapper inside the task sandbox as
python3 <workspace>/.adk_exec_<id>.py, started from the workspace.

WARNING: the script's own working directory is therefore NOT the repository, and in
the notebook's subprocess sandbox the repository is not at /workspace either. Always
take the repository path from find_workspace().
WARNING: print results to stdout only and exit normally. Anything on stderr turns the
tool result into a warning or an error, and a non-zero exit hides the output.
"""

import os
import subprocess
import sys
import tempfile

# Characters of diff or test output to print. The harness does not cap skill output,
# so the scripts cap it themselves to protect the model's context window.
OUTPUT_LIMIT = 3500

# The wrapper file the harness writes into the workspace while a script runs.
WRAPPER_PREFIX = ".adk_exec_"


def is_repo(path):
    return bool(path) and os.path.exists(os.path.join(path, ".git"))


def find_workspace():
    """Return the repository under test, or None if it cannot be found."""
    # 1. ADK's wrapper keeps the directory it was started from in a local variable
    #    named _orig_cwd before it changes directory. That is the workspace.
    frame = sys._getframe()
    while frame is not None:
        value = frame.f_locals.get("_orig_cwd")
        if isinstance(value, str) and is_repo(value):
            return value
        frame = frame.f_back
    # 2. Fallbacks, in case a later ADK version changes the wrapper.
    candidates = [
        os.environ.get("PWD"),
        (os.environ.get("PYTHONPATH") or "").split(os.pathsep)[0],
        "/workspace",
        os.getcwd(),
    ]
    for candidate in candidates:
        if is_repo(candidate):
            return candidate
    return None


def git(workspace, *args, timeout=30):
    """Run git in the workspace. Returns (exit code, stdout, stderr); never raises."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=workspace, capture_output=True, text=True,
            errors="replace", timeout=timeout,
        )
        return done.returncode, done.stdout, done.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def state_dir(workspace):
    """A folder inside .git for the saved copy of the fix. Git never lists it as a change."""
    code, out, _ = git(workspace, "rev-parse", "--git-dir")
    git_dir = out.strip() if code == 0 and out.strip() else ".git"
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(workspace, git_dir)
    path = os.path.join(git_dir, "agent_state")
    os.makedirs(path, exist_ok=True)
    return path


def backup_path(workspace):
    return os.path.join(state_dir(workspace), "coder_fix.patch")


def status_lines(workspace):
    """git status --short without the harness's own wrapper file."""
    _, out, _ = git(workspace, "status", "--short")
    return [line for line in out.splitlines() if line.strip() and WRAPPER_PREFIX not in line]


def modified_files(workspace):
    """Existing files that were edited. These are what a git checkout would erase."""
    _, out, _ = git(workspace, "diff", "--diff-filter=M", "--name-only")
    return [line for line in out.splitlines() if line.strip()]


def capped(text, limit=OUTPUT_LIMIT):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (cut: {len(text) - limit} more characters not shown)"


def shared_tmp():
    """The folder that commands see as /tmp (the harness sets TMPDIR to it)."""
    return tempfile.gettempdir()


def no_workspace():
    print("ERROR: THE REPOSITORY WAS NOT FOUND. Use run_command with git status and git diff instead.")
