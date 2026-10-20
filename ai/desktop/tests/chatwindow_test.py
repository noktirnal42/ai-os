"""Logic tests for the chat window's Do mode. Runs without a display: python3 ai/desktop/tests/chatwindow_test.py"""
import importlib.machinery
import importlib.util
import os
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
_path = os.environ.get("CHATWINDOW_PATH", str(HERE.parent / "bin" / "chatwindow"))
_loader = importlib.machinery.SourceFileLoader("chatwindow", _path)
chat = importlib.util.module_from_spec(importlib.util.spec_from_loader("chatwindow", _loader))
_loader.exec_module(chat)


class DoModeLogic(unittest.TestCase):
    def test_only_yes_approves(self):
        self.assertEqual(chat.gate_reply("y"), b"y\n")
        self.assertEqual(chat.gate_reply(" YES "), b"y\n")
        self.assertEqual(chat.gate_reply("n"), b"n\n")
        self.assertEqual(chat.gate_reply(""), b"n\n")
        self.assertEqual(chat.gate_reply("maybe"), b"n\n")

    def test_do_command_is_bounded_like_the_console(self):
        cmd = chat.do_command("build a thing")
        self.assertIn("run", cmd)
        self.assertEqual(cmd[cmd.index("--max-tools") + 1], "40")
        self.assertEqual(cmd[cmd.index("--max-seconds") + 1], "1500")
        self.assertEqual(cmd[-1], "build a thing")

    def test_tool_arguments_are_never_echoed(self):
        line = chat.event_line({"ev": "tool_call", "tool": "shell", "args": {"cmd": "cat /ai/secrets/x"}})
        self.assertNotIn("secrets", line)
        self.assertIn("shell", line)

    def test_gate_and_verdict_lines(self):
        self.assertEqual(chat.event_line({"ev": "gate", "human": "n"}), "· you answered n")
        self.assertEqual(chat.event_line({"ev": "verdict", "kind": "succeeded"}), "· task succeeded")
        self.assertEqual(chat.event_line({"ev": "session_start"}), "")

    def test_parse_event_rejects_non_objects(self):
        self.assertIsNone(chat.parse_event(b"not json"))
        self.assertIsNone(chat.parse_event(b"[1, 2]"))
        self.assertEqual(chat.parse_event(b'{"ev": "gate"}'), {"ev": "gate"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
