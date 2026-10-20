"""Logic tests for the activity window. Runs without a display: python3 ai/desktop/tests/activity_test.py"""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
_path = os.environ.get("ACTIVITY_PATH", str(HERE.parent / "bin" / "activity"))
_loader = importlib.machinery.SourceFileLoader("activity", _path)
activity = importlib.util.module_from_spec(importlib.util.spec_from_loader("activity", _loader))
_loader.exec_module(activity)


class ActivityLogic(unittest.TestCase):
    def test_tool_arguments_are_never_shown(self):
        line = activity.format_event({"ev": "tool_call", "tool": "shell", "t": "2026-10-20T08:00:01Z",
                                      "args": {"cmd": "cat /ai/secrets/key"}})
        self.assertNotIn("secrets", line)
        self.assertIn("used shell", line)
        self.assertTrue(line.startswith("10-20 08:00:01"))

    def test_policy_and_gate_events_are_readable(self):
        policy = activity.format_event({"ev": "policy", "t": "2026-10-20T08:00:00Z",
                                        "write_roots": ["/ai/apps"], "note": ""})
        self.assertIn("write roots: /ai/apps", policy)
        gate = activity.format_event({"ev": "gate", "human": "n", "t": "2026-10-20T08:00:02Z"})
        self.assertIn("approval answered: n", gate)

    def test_recent_lines_reads_all_sessions_oldest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = pathlib.Path(tmp, "a.jsonl")
            two = pathlib.Path(tmp, "b.jsonl")
            one.write_text(json.dumps({"ev": "verdict", "kind": "partial", "t": "2026-10-20T09:00:00Z"}) + "\n" + "not json\n")
            two.write_text(json.dumps({"ev": "verdict", "kind": "succeeded", "t": "2026-10-20T08:00:00Z"}) + "\n")
            lines = activity.recent_lines(tmp)
            self.assertEqual(len(lines), 2)
            self.assertIn("succeeded", lines[0])
            self.assertIn("partial", lines[1])

    def test_policy_text_reports_blocked_writes_when_unreadable(self):
        self.assertIn("blocked", activity.policy_text("/nonexistent/policy.json"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
