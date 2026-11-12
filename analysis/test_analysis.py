"""Unit tests for analysis.stats and analysis.split (stdlib unittest).

Run from the repo root:  uv run python -m unittest discover -s . -p "test_*.py" -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from analysis import split, stats

TRICKY_DIFF = """\
diff --git a/src/mod.py b/src/mod.py
index 1111111..2222222 100644
--- a/src/mod.py
+++ b/src/mod.py
@@ -1,3 +1,3 @@
 def f():
--- not a header, removed line starting with two dashes
+++ not a header, added line starting with two pluses
     return 1
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+x = 1
diff --git a/old.py b/old.py
deleted file mode 100644
index 4444444..0000000
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-y = 2
diff --git a/r1.py b/r2.py
similarity index 100%
rename from r1.py
rename to r2.py
"""

GOLD_PATCH = """\
diff --git a/src/mod.py b/src/mod.py
--- a/src/mod.py
+++ b/src/mod.py
@@ -1 +1 @@
-a = 1
+a = 2
diff --git a/src/other.py b/src/other.py
--- a/src/other.py
+++ b/src/other.py
@@ -1 +1 @@
-b = 1
+b = 2
"""

PRED_PATCH = """\
diff --git a/src/mod.py b/src/mod.py
--- a/src/mod.py
+++ b/src/mod.py
@@ -1 +1 @@
-a = 1
+a = 3
diff --git a/reproduce.py b/reproduce.py
new file mode 100644
--- /dev/null
+++ b/reproduce.py
@@ -0,0 +1 @@
+print('repro')
"""


class TestRates(unittest.TestCase):
    def test_wilson_matches_hand_calculation(self):
        lo, hi = stats.wilson_interval(12, 60)
        self.assertAlmostEqual(lo, 0.1183, delta=1e-3)
        self.assertAlmostEqual(hi, 0.3178, delta=1e-3)

    def test_wilson_bounds(self):
        self.assertEqual(stats.wilson_interval(0, 10)[0], 0.0)
        self.assertEqual(stats.wilson_interval(10, 10)[1], 1.0)
        with self.assertRaises(ValueError):
            stats.wilson_interval(11, 10)

    def test_mcnemar_exact_values(self):
        self.assertAlmostEqual(stats.mcnemar_exact(10, 2), 158 / 4096, places=12)
        self.assertAlmostEqual(stats.mcnemar_exact(2, 10), 158 / 4096, places=12)
        self.assertAlmostEqual(stats.mcnemar_exact(0, 6), 2 / 64, places=12)
        self.assertEqual(stats.mcnemar_exact(0, 0), 1.0)
        self.assertEqual(stats.mcnemar_exact(5, 5), 1.0)

    def test_compare_counts(self):
        a = {"t1": 1, "t2": 1, "t3": 0, "t4": 0, "t5": 1, "t6": 0}
        b = {"t1": 1, "t2": 0, "t3": 1, "t4": 1, "t5": 1, "t6": 0, "t7": 1}
        r = stats.compare(a, b, reps=2000, seed=1)
        self.assertEqual(r["n"], 6)
        self.assertEqual((r["solved_a"], r["solved_b"]), (3, 4))
        self.assertEqual((r["a_only"], r["b_only"]), (1, 2))
        self.assertAlmostEqual(r["diff_b_minus_a"], 1 / 6)
        self.assertEqual(r["only_in_b"], 1)
        self.assertEqual(r["mcnemar_p"], 1.0)
        lo, hi = r["ci95_diff"]
        self.assertLessEqual(lo, r["diff_b_minus_a"])
        self.assertGreaterEqual(hi, r["diff_b_minus_a"])

    def test_bootstrap_degenerate_and_deterministic(self):
        pairs = [(f"t{i}", True, True) for i in range(20)]
        self.assertEqual(stats.paired_bootstrap_ci(pairs, reps=500), (0.0, 0.0))
        mixed = [(f"t{i}", i % 3 == 0, i % 2 == 0) for i in range(30)]
        self.assertEqual(
            stats.paired_bootstrap_ci(mixed, reps=500, seed=7),
            stats.paired_bootstrap_ci(mixed, reps=500, seed=7),
        )

    def test_holm(self):
        adj = stats.holm({"x": 0.01, "y": 0.04, "z": 0.03})
        self.assertAlmostEqual(adj["x"], 0.03)
        self.assertAlmostEqual(adj["z"], 0.06)
        self.assertAlmostEqual(adj["y"], 0.06)


class TestLocalization(unittest.TestCase):
    def test_files_in_tricky_diff(self):
        self.assertEqual(
            stats.files_in_diff(TRICKY_DIFF),
            {"src/mod.py", "new.py", "old.py", "r2.py"},
        )

    def test_empty_and_no_patch(self):
        self.assertEqual(stats.files_in_diff(""), set())
        self.assertEqual(stats.files_in_diff("NO_PATCH"), set())
        self.assertEqual(stats.files_in_diff(None), set())

    def test_localization_metrics(self):
        r = stats.localization(PRED_PATCH, GOLD_PATCH)
        self.assertEqual((r["gold_files"], r["pred_files"]), (2, 2))
        self.assertAlmostEqual(r["recall"], 0.5)
        self.assertAlmostEqual(r["precision"], 0.5)
        self.assertTrue(r["hit"])
        self.assertEqual(r["extra_files"], 1)

    def test_localization_no_patch(self):
        r = stats.localization("NO_PATCH", GOLD_PATCH)
        self.assertEqual(r["recall"], 0.0)
        self.assertIsNone(r["precision"])
        self.assertFalse(r["hit"])
        self.assertIsNone(stats.localization(PRED_PATCH, "")["recall"])


class TestResultsAndCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def test_load_results_and_cli(self):
        rows = ["config,run,instance_id,resolved,wall_seconds"]
        for i in range(10):
            rows.append(f"s1,r1,t{i},{1 if i < 3 else 0},100")
            rows.append(f"s2,r1,t{i},{'pass' if i < 6 else 'fail'},120")
        path = self._write("results.csv", "\n".join(rows) + "\n")
        res = stats.load_results(path)
        self.assertEqual(sum(res["s1"]["r1"].values()), 3)
        self.assertEqual(sum(res["s2"]["r1"].values()), 6)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(stats.main(["summary", path]), 0)
            self.assertEqual(stats.main(["compare", path, "--a", "s1", "--b", "s2", "--reps", "2000"]), 0)
        text = out.getvalue()
        self.assertIn("s1", text)
        self.assertIn("B - A = +0.300", text)
        self.assertIn("A-only 0, B-only 3", text)

    def test_help_text_renders(self):
        for argv in (["--help"], ["summary", "--help"], ["compare", "--help"]):
            with self.subTest(argv=argv), contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as cm:
                    stats.main(argv)
                self.assertEqual(cm.exception.code, 0)
                self.assertIn("usage", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                split.main(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_load_results_rejects_duplicates_and_bad_values(self):
        dup = self._write("dup.csv", "config,run,instance_id,resolved\ns1,r1,t1,1\ns1,r1,t1,0\n")
        with self.assertRaises(ValueError):
            stats.load_results(dup)
        bad = self._write("bad.csv", "config,run,instance_id,resolved\ns1,r1,t1,maybe\n")
        with self.assertRaises(ValueError):
            stats.load_results(bad)


class TestSplit(unittest.TestCase):
    IDS = {
        "org/a": [f"a_{i}" for i in range(9)],
        "org/b": [f"b_{i}" for i in range(6)],
    }

    def test_sizes_disjoint_complete(self):
        tune, held = split.stratified_split(self.IDS, 1 / 3, seed=20261023)
        self.assertEqual(len(tune), 5)  # round(9/3) + round(6/3)
        self.assertEqual(len(held), 10)
        self.assertFalse(set(tune) & set(held))
        all_ids = {i for ids in self.IDS.values() for i in ids}
        self.assertEqual(set(tune) | set(held), all_ids)
        self.assertEqual(sum(1 for i in tune if i.startswith("a_")), 3)

    def test_deterministic_by_seed(self):
        first = split.stratified_split(self.IDS, 1 / 3, seed=5)
        self.assertEqual(first, split.stratified_split(self.IDS, 1 / 3, seed=5))
        self.assertTrue(
            any(split.stratified_split(self.IDS, 1 / 3, seed=s) != first for s in range(6, 12))
        )

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks.jsonl")
            with open(tasks, "w") as fh:
                for repo, ids in self.IDS.items():
                    for iid in ids:
                        fh.write(json.dumps({"instance_id": iid, "repo": repo}) + "\n")
            out_path = os.path.join(tmp, "splits", "split.json")  # parent dir is created
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(split.main(["--tasks", tasks, "--seed", "1", "--out", out_path]), 0)
            with open(out_path) as fh:
                payload = json.load(fh)
            self.assertEqual(payload["n_tune"] + payload["n_heldout"], 15)
            self.assertEqual(payload["counts_by_repo"]["org/b"]["tune"], 2)


if __name__ == "__main__":
    unittest.main()
