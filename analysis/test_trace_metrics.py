"""Unit tests for analysis.trace_metrics (stdlib unittest).

Run from the repo root:  uv run python -m unittest analysis.test_trace_metrics -v
"""
from __future__ import annotations

import unittest

from analysis import trace_metrics as tm


def step(author, tool=None, args=None, observation="", prompt_tokens=None):
    s = {"source": "agent", "extra": {"author": author}}
    if tool is not None:
        call = {"function_name": tool, "arguments": args or {}, "extra": {}}
        if prompt_tokens is not None:
            call["extra"]["usage"] = {"prompt_tokens": prompt_tokens}
        s["tool_calls"] = [call]
        s["observation"] = observation
    else:
        s["message"] = "final reply"
    return s


OK = '{"content": "{\\"status\\": \\"ok\\"}"}'
ERR = '{"content": "{\\"status\\": \\"error\\"}"}'


class TestMalformed(unittest.TestCase):
    def test_well_formed_calls(self):
        self.assertFalse(tm.is_malformed("run_command", {"command": "ls"}))
        self.assertFalse(tm.is_malformed("read_file", {"filepath": "a.py"}))
        self.assertFalse(tm.is_malformed("read_file", {"filepath": "a.py", "start_line": 1, "end_line": 9}))
        self.assertFalse(tm.is_malformed("edit_file", {"filepath": "a.py", "old_string": "x", "new_string": "y"}))

    def test_missing_required_argument(self):
        self.assertTrue(tm.is_malformed("edit_file", {"filepath": "a.py", "new_string": "y"}))
        self.assertTrue(tm.is_malformed("run_command", {}))

    def test_unexpected_argument_name(self):
        # The stray quote seen in the traces: the key arrives as start_line" and is ignored.
        self.assertTrue(tm.is_malformed("read_file", {"filepath": "a.py", 'start_line"': 5}))
        self.assertTrue(tm.is_malformed("run_command", {"command": "ls", "edge_type": "calls"}))

    def test_line_numbers_folded_into_path(self):
        self.assertTrue(tm.is_malformed("read_file", {"filepath": "rich/_inspect.py`,start_line:80"}))

    def test_non_dict_arguments(self):
        self.assertTrue(tm.is_malformed("run_command", "ls"))

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            tm.is_malformed("get_status", {})


class TestRuns(unittest.TestCase):
    def test_longest_identical_run(self):
        self.assertEqual(tm.longest_identical_run([]), 0)
        self.assertEqual(tm.longest_identical_run(["a", "a", "b", "a", "a", "a"]), 3)

    def test_result_status(self):
        self.assertEqual(tm.result_status(OK), "ok")
        self.assertIsNone(tm.result_status("no status here"))


class TestTaskRows(unittest.TestCase):
    def setUp(self):
        grep = {"command": "grep -n x a.py"}
        bad_edit = {"filepath": "a.py", "new_string": "y"}
        good_edit = {"filepath": "a.py", "old_string": "x", "new_string": "y"}
        self.steps = [
            {"source": "user", "extra": {"author": "harness"}, "message": "task"},
            step("localizer", "run_command", grep, OK, prompt_tokens=13000),
            step("localizer", "run_command", grep, OK, prompt_tokens=14000),
            step("localizer", "run_command", grep, '{"budget_warning": "Only 10 tool call(s) remaining"}',
                 prompt_tokens=2000),
            step("localizer"),
            step("coder", "edit_file", bad_edit, ERR),
            step("coder", "edit_file", bad_edit, ERR),
            step("coder", "edit_file", good_edit, OK),
            step("coder", "run_command", {"command": "python -c 'print(1)'"}, OK),
            step("verifier", "run_command", {"command": "git checkout ."}, OK),
            step("coder", "read_file", {"filepath": "a.py"}, OK),
            step("verifier", "get_status", {}, OK),
        ]
        self.rows = {r["role"]: r for r in tm.task_rows("probe8-3", "t1", self.steps)}

    def test_task_level_row(self):
        a = self.rows["ALL"]
        self.assertEqual((a["configuration"], a["stage"]), (4, "original"))
        self.assertEqual(a["tool_calls"], 10)
        self.assertEqual(a["longest_identical_run"], 3)
        self.assertEqual(a["budget_warning_at"], 3)

    def test_localizer_row(self):
        loc = self.rows["localizer"]
        self.assertEqual((loc["first_call_at"], loc["last_call_at"]), (1, 3))
        self.assertEqual(loc["distinct_calls"], 1)
        self.assertEqual(loc["history_resets"], 1)

    def test_malformed_raw_and_distinct(self):
        coder = self.rows["coder"]
        self.assertEqual((coder["edit_calls"], coder["edit_malformed"]), (3, 2))
        self.assertEqual((coder["edit_distinct"], coder["edit_distinct_malformed"]), (2, 1))
        self.assertEqual((coder["edit_ok"], coder["edit_failed"]), (1, 2))
        self.assertEqual(coder["python_runs"], 1)

    def test_invocations_and_verifier_counts(self):
        self.assertEqual(self.rows["coder"]["invocations"], 2)
        self.assertEqual(self.rows["verifier"]["invocations"], 2)
        self.assertEqual(self.rows["verifier"]["git_revert_commands"], 1)
        self.assertEqual(self.rows["verifier"]["get_status_calls"], 1)

    def test_rows_hold_no_text_beyond_identifiers(self):
        for row in self.rows.values():
            for column, value in row.items():
                if column not in ("run", "stage", "task", "role"):
                    self.assertIsInstance(value, (int, str))
                    if isinstance(value, str):
                        self.assertEqual(value, "")


if __name__ == "__main__":
    unittest.main()
