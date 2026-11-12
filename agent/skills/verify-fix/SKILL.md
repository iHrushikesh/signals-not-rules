---
name: verify-fix
description: Safe checks for the verifier. Shows the coder's change and saves a copy of it, runs a test file with and without the fix, and restores the fix if it goes missing. None of the scripts can damage the fix.
---

# verify-fix

Three scripts for checking a fix without ever changing the repository. Run each with
the run_skill_script tool, with skill_name "verify-fix".

| What you need | file_path | args |
|---|---|---|
| See the change and save a copy of it | scripts/check_fix.py | none |
| Find out whether a failing test is caused by the fix | scripts/compare_test.py | {"test": "path/to/test_file.py"} |
| Put the fix back if it is missing | scripts/restore_fix.py | none |

Each script prints one line in capitals that tells you the result. Act on that line.

Never use git checkout, git stash, git reset or sed -i to compare with the original
code. compare_test.py does that comparison on a separate copy.
