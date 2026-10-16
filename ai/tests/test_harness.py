#!/usr/bin/env python3
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import aios


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.patch = mock.patch.object(aios, "AI_ROOT", self.root)
        self.patch.start()
        aios.WRITE_ROOTS = tuple((self.root / p).resolve() for p in ("apps", "lib", "bin", "state", "tmp", "out"))
        aios.READ_ROOTS = aios.WRITE_ROOTS + ((self.root / "checkpoints").resolve(),)
        aios.SECRET_ROOT = (self.root / "secrets").resolve()
        for d in ("apps", "lib", "bin", "state", "tmp", "out", "secrets"):
            (self.root / d).mkdir()

    def tearDown(self): self.patch.stop(); self.tmp.cleanup()

    def session(self): return aios.Session("test", aios.ModelClient("http://unused", offline=True), max_tools=10)

    def test_write_policy_and_secret_denial(self):
        s = self.session()
        self.assertIn("bytes", s.call_tool("fs_write", {"path": str(self.root / "apps" / "hello.txt"), "content": "hello"}))
        self.assertIn("error", s.call_tool("fs_write", {"path": str(self.root / "secrets" / "key"), "content": "no"}))
        self.assertIn("error", s.call_tool("fs_read", {"path": "/etc/shadow"}))

    def test_shell_truncates_and_rejects_dangerous_paths(self):
        s = self.session()
        result = s.call_tool("shell", {"cmd": "printf 'x%.0s' $(seq 1 5000)", "workdir": str(self.root / "apps")})
        self.assertTrue(result["truncated"]); self.assertIn("error", s.call_tool("shell", {"cmd": "cat /etc/shadow"}))
        self.assertIn("error", s.call_tool("shell", {"cmd": "curl http://example.com"}))
        self.assertEqual(s.call_tool("shell", {"cmd": "pwd", "workdir": str(self.root)})["stdout"].strip(), str(self.root))

    def test_repeated_malformed_tool_call_is_stopped_with_actionable_error(self):
        s = self.session()
        args = {"cmd": {"type": "string"}, "workdir": {"type": "string"}}
        results = [s.call_tool("shell", args) for _ in range(4)]
        self.assertIn("command string", results[0]["error"])
        self.assertIn("repeated four times", results[3]["error"])

    def test_nested_shell_command_shape_is_normalized_and_audited(self):
        s = self.session()
        result = s.call_tool("shell", {"cmd": {
            "cmd": "printf NESTED_OK", "timeout_s": 5,
            "workdir": str(self.root / "apps")}})
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["stdout"], "NESTED_OK")
        events = [json.loads(line) for line in s.log.path.read_text().splitlines()]
        self.assertTrue(any(row["ev"] == "tool_args_normalized" for row in events))

    def test_checkpoint_round_trip(self):
        s = self.session(); (self.root / "apps" / "marker").write_text("before")
        self.assertEqual(s.call_tool("checkpoint", {"op": "create", "tag": "baseline"}), {"created": "baseline"})
        (self.root / "apps" / "marker").write_text("after")
        self.assertEqual(s.call_tool("checkpoint", {"op": "rollback", "tag": "baseline"}), {"rolled_back": "baseline"})
        self.assertEqual((self.root / "apps" / "marker").read_text(), "before")

    def test_registry_manifest_and_audit(self):
        self.prepare_app("hello", "exit 0\nprintf 'HELLO TEST PASS\\n'\n")
        s = self.session()
        with mock.patch.object(s, "ask_human", return_value={"approved": True}) as gate:
            result = s.call_tool("registry", {"op": "install", "name": "hello"})
        self.assertNotIn("error", result, result)
        self.assertIn("acceptance test:", gate.call_args.args[0]["question"])
        self.assertTrue(result["registry"]["hello"]["tests_pass"])
        rows = [json.loads(line) for line in s.log.path.read_text().splitlines()]
        self.assertTrue(any(row["ev"] == "tool_result" for row in rows))
        self.assertTrue(any(row["ev"] == "registry_test" and row["exit"] == 0 for row in rows))

    def test_registry_budget_counts_registry_calls_not_build_tools(self):
        self.prepare_app("built", "exit 0\n")
        s = self.session()
        s.tool_count = 6
        with mock.patch.object(s, "ask_human", return_value={"approved": True}):
            result = s.call_tool("registry", {"op": "install", "name": "built"})
        self.assertNotIn("error", result, result)
        self.assertEqual(s.registry_ops, 1)

    def test_registry_rejects_incomplete_or_unsafe_manifest(self):
        self.prepare_app("bad", "exit 0\n", entry="/etc/thing")
        s = self.session()
        self.assertIn("error", s.call_tool("registry", {"op": "install", "name": "bad"}))
        self.prepare_app("bad", "exit 1\n")
        with mock.patch.object(s, "ask_human", return_value={"approved": True}):
            self.assertIn("error", s.call_tool("registry", {"op": "install", "name": "bad"}))
        registry_file = self.root / "state" / "registry.json"
        self.assertFalse(registry_file.exists())

    def test_registry_install_requires_human_approval_before_tests(self):
        self.prepare_app("gated", "touch test-ran\nexit 0\n")
        s = self.session()
        with mock.patch.object(s, "ask_human", return_value={"approved": False}):
            result = s.call_tool("registry", {"op": "install", "name": "gated"})
        self.assertIn("error", result)
        self.assertFalse((self.root / "apps" / "gated" / "test-ran").exists())

    def prepare_app(self, name, test_script, entry=None):
        app = self.root / "apps" / name
        (app / "tests").mkdir(parents=True, exist_ok=True)
        executable = self.root / "bin" / name
        executable.write_text("#!/bin/sh\nexit 0\n")
        tests = app / "tests" / "run.sh"
        tests.write_text("#!/bin/sh\nset -eu\n" + test_script)
        manifest = {"name": name, "version": "0.1.0", "entry": entry or str(executable),
                    "tests": str(tests), "tests_pass": False}
        (app / "manifest.json").write_text(json.dumps(manifest))

    def test_net_status_is_read_only_and_persisted(self):
        s = self.session()
        def fake_run(command, **kwargs):
            body = [{"ifname": "eth0"}] if command[-1] == "addr" else [{"dst": "default"}]
            return mock.Mock(returncode=0, stdout=json.dumps(body), stderr="")
        with mock.patch.object(aios.subprocess, "run", side_effect=fake_run):
            result = s.call_tool("net", {"op": "status"})
        self.assertEqual(result["interfaces"], 1)
        net = json.loads((self.root / "state" / "net.json").read_text())
        self.assertTrue(net["emulated"])
        self.assertEqual(net["routes"][0]["dst"], "default")

    def test_model_tool_call_executes_and_then_verdicts(self):
        root = self.root
        class FakeClient:
            offline = False
            def __init__(self): self.calls = 0
            def chat(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    args = {"path": str(root / "apps" / "built.txt"), "content": "built"}
                    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "fs_write", "arguments": json.dumps(args)}}]}}]}
                return {"choices": [{"message": {"role": "assistant", "content": "done"}}]}
        session = aios.Session("tool loop", FakeClient(), max_tools=4, max_seconds=5)
        self.assertEqual(session.run(), 0)
        self.assertEqual((self.root / "apps" / "built.txt").read_text(), "built")
        self.assertEqual(session.client.calls, 2)
        verdicts = [json.loads(line) for line in session.log.path.read_text().splitlines()]
        verdict = next(row for row in verdicts if row["ev"] == "verdict")
        self.assertEqual(verdict["kind"], "partial")
        self.assertFalse(verdict["verified"])

    def test_required_command_nudges_early_final_and_verifies_success(self):
        root = self.root
        command = "printf REQUIRED_TEST_OK"
        class FakeClient:
            offline = False
            def __init__(self): self.calls = 0
            def chat(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    return {"choices": [{"message": {"role": "assistant", "content": "Done."}}]}
                if self.calls == 2:
                    args = {"cmd": command, "workdir": str(root / "apps")}
                    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "verify", "function": {"name": "shell", "arguments": json.dumps(args)}}]}}]}
                return {"choices": [{"message": {"role": "assistant", "content": "Verified."}}]}
        session = aios.Session("required test", FakeClient(), max_tools=4, max_seconds=5,
                               required_commands=(command,))
        self.assertEqual(session.run(), 0)
        self.assertEqual(session.client.calls, 3)
        verdicts = [json.loads(line) for line in session.log.path.read_text().splitlines()]
        verdict = next(row for row in verdicts if row["ev"] == "verdict")
        self.assertEqual(verdict["kind"], "succeeded")
        self.assertTrue(verdict["verified"])
        shell_result = next(row for row in verdicts if row["ev"] == "tool_result" and row["tool"] == "shell")
        self.assertEqual(shell_result["command_exit"], 0)

    def test_text_tool_fallback_accepts_documented_protocol_and_one_call(self):
        response = '''Plan:
```json
{"tool": "fs_write", "args": {"path": "/ai/apps/first", "content": "one"}}
```
{"name": "shell", "arguments": {"cmd": "echo should-wait"}}
'''
        call = aios.Session.text_tool_call(response)
        self.assertEqual(call["function"]["name"], "fs_write")
        self.assertEqual(json.loads(call["function"]["arguments"]),
                         {"path": "/ai/apps/first", "content": "one"})

    def test_text_tool_fallback_accepts_local_model_shape_and_rejects_unknown(self):
        response = '''{"name": "fs_write", "arguments": "{\\"path\\": \\"/ai/apps/a\\", \\"content\\": \\"ok\\"}"}'''
        call = aios.Session.text_tool_call(response)
        self.assertEqual(call["function"]["name"], "fs_write")
        self.assertEqual(json.loads(call["function"]["arguments"]),
                         {"path": "/ai/apps/a", "content": "ok"})
        self.assertIsNone(aios.Session.text_tool_call(
            '{"name":"invented_tool","arguments":{}}'))
        self.assertIsNone(aios.Session.text_tool_call(
            'Example only: {"name":"fs_write","arguments":{}}'))

    def test_text_tool_fallback_maps_in_workspace_shell_script_shape(self):
        script = self.root / "apps" / "demo" / "tests" / "run.sh"
        script.parent.mkdir(parents=True)
        script.write_text("#!/bin/sh\nexit 0\n")
        response = json.dumps({"name": "/bin/sh", "arguments": {
            "path": str(script), "workdir": str(script.parent)}})
        call = aios.Session.text_tool_call(response)
        self.assertEqual(call["function"]["name"], "shell")
        args = json.loads(call["function"]["arguments"])
        self.assertEqual(args["cmd"], f"/bin/sh {script}")
        self.assertEqual(args["workdir"], str(script.parent))
        outside = json.dumps({"name": "/bin/sh", "arguments": {"path": "/etc/passwd"}})
        self.assertIsNone(aios.Session.text_tool_call(outside))


if __name__ == "__main__": unittest.main()
