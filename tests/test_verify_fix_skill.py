"""Tests for agent/skills/verify-fix, run the way the competition harness runs a skill script.

ADK (1.36.1) wraps a skill script in a self-extracting program, and the harness writes
that program to <workspace>/.adk_exec_<id>.py and runs it with python3 from the
workspace, with TMPDIR pointing at the sandbox's tmp folder. These tests do the same
against scratch repositories, so they cover the parts that differ from running a
script directly: the working directory, the wrapper file in the workspace, and the
argument passing.

The compare_test.py cases need pytest, which is not a project dependency. Run them with:
    uv run --with pytest python -m unittest tests.test_verify_fix_skill -v
Without pytest they are skipped.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from google.adk.skills import load_skill_from_dir
# Private ADK class: it builds the exact wrapper program the harness executes.
from google.adk.tools.skill_toolset import _SkillScriptCodeExecutor

SKILL_DIR = Path(__file__).resolve().parents[1] / "agent" / "skills" / "verify-fix"
HAS_PYTEST = importlib.util.find_spec("pytest") is not None


class Sandbox:
    """A scratch repository plus the tmp folder a harness sandbox would give it."""

    def __init__(self, root: Path, layout: str):
        self.workspace = root / "workspace"
        self.tmp = root / "tmp"
        self.package = self.workspace / ("src/pkg" if layout == "src" else "pkg")
        self.package.mkdir(parents=True)
        (self.workspace / "tests").mkdir()
        self.tmp.mkdir()
        (self.package / "__init__.py").write_text("")
        self.module = self.package / "m.py"
        self.module.write_text("def f():\n    return 1\n\n\ndef g():\n    return 10\n")
        # test_f needs the fix; test_g passes only on the original code; test_bad always fails.
        (self.workspace / "tests" / "test_f.py").write_text("from pkg.m import f\n\n\ndef test_f():\n    assert f() == 2\n")
        (self.workspace / "tests" / "test_g.py").write_text("from pkg.m import g\n\n\ndef test_g():\n    assert g() == 10\n")
        (self.workspace / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n")
        (self.workspace / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "baseline")
        self.skill = load_skill_from_dir(SKILL_DIR)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.workspace, capture_output=True, text=True, check=False)

    def status(self):
        return self.git("status", "--short").stdout

    def apply_fix(self, breaks_g=False):
        g_value = 11 if breaks_g else 10
        self.module.write_text(f"def f():\n    return 2\n\n\ndef g():\n    return {g_value}\n")

    def run_script(self, file_path, args=None):
        """Run one skill script exactly as the harness does. Returns (stdout, stderr, exit code)."""
        code = _SkillScriptCodeExecutor(None, 120)._build_wrapper_code(self.skill, file_path, args, None, None)
        wrapper = self.workspace / ".adk_exec_test1234.py"
        wrapper.write_text(code)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.tmp), "TMPDIR": str(self.tmp), "TEST_TMPDIR": str(self.tmp),
            "PYTHONNOUSERSITE": "1", "PYTHONPATH": str(self.workspace),
        }
        try:
            done = subprocess.run([sys.executable, str(wrapper)], cwd=self.workspace, env=env,
                                  capture_output=True, text=True, timeout=180)
        finally:
            wrapper.unlink()
        return done.stdout, done.stderr, done.returncode


def capital_lines(stdout):
    """The result lines: those that start with a word in capitals, as the prompt describes."""
    keys = ("SAVED", "THE FIX", "NO EDITS", "ONLY NEW", "FIX RESTORED", "NO SAVED", "RESTORE FAILED", "VERDICT", "ERROR")
    return [line for line in stdout.splitlines() if line.startswith(keys)]


class SkillScriptTests(unittest.TestCase):
    layouts = ("flat", "src")

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="verify_fix_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def sandbox(self, layout):
        return Sandbox(self.root / layout, layout)

    def check(self, box, file_path, args=None):
        out, err, code = box.run_script(file_path, args)
        self.assertEqual(code, 0, f"{file_path} exited {code}: {err}")
        self.assertEqual(err, "", f"{file_path} wrote to stderr")
        return out

    def test_nothing_edited(self):
        for layout in self.layouts:
            with self.subTest(layout=layout):
                out = self.check(self.sandbox(layout), "scripts/check_fix.py")
                self.assertEqual(capital_lines(out), ["NO EDITS IN WORKSPACE"])
                self.assertIn("(none)", out)

    def test_edit_is_saved_and_wrapper_file_is_not_listed(self):
        for layout in self.layouts:
            with self.subTest(layout=layout):
                box = self.sandbox(layout)
                box.apply_fix()
                out = self.check(box, "scripts/check_fix.py")
                self.assertEqual(capital_lines(out), ["SAVED A COPY OF THE FIX"])
                self.assertIn("+    return 2", out)
                self.assertNotIn(".adk_exec_", out)
                # Saving must not show up as a change, and must not touch the fix.
                self.assertEqual(box.status().split(), ["M", str(box.module.relative_to(box.workspace))])

    def test_fix_erased_by_git_checkout_is_reported_and_restored(self):
        for layout in self.layouts:
            with self.subTest(layout=layout):
                box = self.sandbox(layout)
                box.apply_fix()
                self.check(box, "scripts/check_fix.py")
                fixed = box.module.read_text()
                box.git("checkout", "-q", ".")
                out = self.check(box, "scripts/check_fix.py")
                self.assertEqual(len(capital_lines(out)), 1)
                self.assertTrue(capital_lines(out)[0].startswith("THE FIX IS MISSING. Restore it now"))
                out = self.check(box, "scripts/restore_fix.py")
                self.assertIn("FIX RESTORED", capital_lines(out))
                self.assertEqual(box.module.read_text(), fixed)
                self.assertEqual(capital_lines(self.check(box, "scripts/check_fix.py")), ["SAVED A COPY OF THE FIX"])

    def test_restore_after_a_half_edit_gives_the_exact_fix(self):
        box = self.sandbox("flat")
        box.apply_fix()
        self.check(box, "scripts/check_fix.py")
        fixed = box.module.read_text()
        box.module.write_text("def f():\n    return 99  # damaged by hand\n")
        self.assertIn("FIX RESTORED", capital_lines(self.check(box, "scripts/restore_fix.py")))
        self.assertEqual(box.module.read_text(), fixed)
        # Restoring when the fix is already in place changes nothing.
        self.assertIn("FIX RESTORED", capital_lines(self.check(box, "scripts/restore_fix.py")))
        self.assertEqual(box.module.read_text(), fixed)

    def test_restore_without_a_saved_copy(self):
        out = self.check(self.sandbox("flat"), "scripts/restore_fix.py")
        self.assertTrue(capital_lines(out)[0].startswith("NO SAVED COPY"))

    def test_new_file_only(self):
        box = self.sandbox("flat")
        (box.package / "extra.py").write_text("x = 1\n")
        out = self.check(box, "scripts/check_fix.py")
        self.assertEqual(capital_lines(out), ["ONLY NEW FILES, NO EDITS TO EXISTING FILES"])
        self.assertIn("extra.py", out)

    def test_large_diff_is_capped_and_result_line_comes_first(self):
        box = self.sandbox("flat")
        box.module.write_text("def f():\n    return 2\n" + "".join(f"# filler line {i}\n" for i in range(2000)))
        out = self.check(box, "scripts/check_fix.py")
        self.assertLess(len(out), 4200)
        self.assertLess(out.index("SAVED A COPY OF THE FIX"), out.index("DIFF:"))
        self.assertIn("more characters not shown", out)

    @unittest.skipUnless(HAS_PYTEST, "pytest is not installed")
    def test_compare_verdicts(self):
        for layout in self.layouts:
            with self.subTest(layout=layout):
                box = self.sandbox(layout)
                box.apply_fix(breaks_g=True)
                before = box.status()
                fixed = box.module.read_text()

                out = self.check(box, "scripts/compare_test.py", {"test": "tests/test_f.py"})
                self.assertIn("WITH THE FIX: PASSED", out)
                self.assertTrue(capital_lines(out)[-1].startswith("VERDICT: THE TEST FILE PASSES WITH THE FIX"))

                out = self.check(box, "scripts/compare_test.py", {"test": "tests/test_g.py"})
                self.assertIn("WITH THE FIX: FAILED", out)
                self.assertIn("ORIGINAL CODE: PASSED", out)
                self.assertTrue(capital_lines(out)[-1].startswith("VERDICT: BROKEN BY THE FIX"))

                out = self.check(box, "scripts/compare_test.py", ["--test", "tests/test_bad.py"])
                self.assertIn("ORIGINAL CODE: FAILED", out)
                self.assertTrue(capital_lines(out)[-1].startswith("VERDICT: FAILS WITH AND WITHOUT THE FIX"))

                # The repository and the fix are untouched by any number of comparisons.
                self.assertEqual(box.status(), before)
                self.assertEqual(box.module.read_text(), fixed)

    @unittest.skipUnless(HAS_PYTEST, "pytest is not installed")
    def test_compare_rejects_bad_paths(self):
        box = self.sandbox("flat")
        for args in (None, {"test": "../outside.py"}, {"test": "/etc/passwd"}, {"test": "tests/missing.py"}):
            out = self.check(box, "scripts/compare_test.py", args)
            self.assertTrue(capital_lines(out)[0].startswith("ERROR"), out)
        out = self.check(box, "scripts/compare_test.py", {"test": "/workspace/tests/test_g.py"})
        self.assertIn("WITH THE FIX: PASSED", out)
        # The path as a plain argument, as when the model sends args as a list.
        out = self.check(box, "scripts/compare_test.py", ["tests/test_g.py"])
        self.assertIn("WITH THE FIX: PASSED", out)


if __name__ == "__main__":
    unittest.main()
