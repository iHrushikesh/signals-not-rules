"""Show the coder's change and save a copy of it. Takes no arguments.

Prints the changed files, then one line in capitals that says what to do next, then
the start of the diff. Never changes any file in the repository.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fixlib as lib


def main():
    workspace = lib.find_workspace()
    if workspace is None:
        lib.no_workspace()
        return
    status = lib.status_lines(workspace)
    modified = lib.modified_files(workspace)
    backup = lib.backup_path(workspace)

    print("CHANGED FILES:")
    print("\n".join(status) if status else "(none)")
    print()
    if modified:
        # Only edits to existing files are saved. New files survive a git checkout,
        # and a patch that creates a file cannot be applied while that file exists.
        code, patch, err = lib.git(workspace, "diff", "--binary", "--diff-filter=M")
        if code == 0 and patch:
            with open(backup, "w", encoding="utf-8", errors="replace") as handle:
                handle.write(patch)
            print("SAVED A COPY OF THE FIX")
        else:
            print("COULD NOT SAVE A COPY OF THE FIX: " + (err.strip() or "empty diff"))
    elif os.path.isfile(backup) and os.path.getsize(backup) > 0:
        print("THE FIX IS MISSING. Restore it now: call run_skill_script with file_path scripts/restore_fix.py")
    elif status:
        print("ONLY NEW FILES, NO EDITS TO EXISTING FILES")
    else:
        print("NO EDITS IN WORKSPACE")
    print()
    _, diff, _ = lib.git(workspace, "diff")
    if diff.strip():
        print("DIFF:")
        print(lib.capped(diff))


main()
