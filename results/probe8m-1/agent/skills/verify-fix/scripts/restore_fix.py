"""Put the saved copy of the coder's fix back. Takes no arguments.

Use it when check_fix.py reports that the fix is missing, or when submit_patch
reports patch_size 0. Only files named in the saved copy are touched.
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
    backup = lib.backup_path(workspace)
    if not (os.path.isfile(backup) and os.path.getsize(backup) > 0):
        print("NO SAVED COPY OF THE FIX EXISTS. Nothing was changed.")
        return

    code, _, _ = lib.git(workspace, "apply", "--check", backup)
    if code != 0:
        # The files are not in their original state (already fixed, or half edited).
        # Reset exactly the files named in the saved copy, then apply it.
        _, names, _ = lib.git(workspace, "apply", "--numstat", backup)
        files = [line.split("\t")[-1] for line in names.splitlines() if line.strip()]
        if files:
            lib.git(workspace, "checkout", "--", *files)
    code, _, err = lib.git(workspace, "apply", backup)
    if code != 0:
        print("RESTORE FAILED: " + err.strip()[:400])
        return
    _, stat, _ = lib.git(workspace, "diff", "--stat")
    print("FIX RESTORED")
    print(stat.strip())


main()
