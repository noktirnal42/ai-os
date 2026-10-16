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

    def test_checkpoint_round_trip(self):
        s = self.session(); (self.root / "apps" / "marker").write_text("before")
        self.assertEqual(s.call_tool("checkpoint", {"op": "create", "tag": "baseline"}), {"created": "baseline"})
        (self.root / "apps" / "marker").write_text("after")
        self.assertEqual(s.call_tool("checkpoint", {"op": "rollback", "tag": "baseline"}), {"rolled_back": "baseline"})
        self.assertEqual((self.root / "apps" / "marker").read_text(), "before")

    def test_registry_manifest_and_audit(self):
        s = self.session(); result = s.call_tool("registry", {"op": "install", "name": "hello", "manifest": {"name": "hello", "version": "0.1", "entry": "/ai/bin/hello", "tests": "/ai/apps/hello/tests/run.sh", "tests_pass": True}})
        self.assertTrue(result["registry"]["hello"]["tests_pass"])
        rows = [json.loads(line) for line in s.log.path.read_text().splitlines()]
        self.assertTrue(any(row["ev"] == "tool_result" for row in rows))

    def test_registry_rejects_incomplete_or_unsafe_manifest(self):
        s = self.session()
        self.assertIn("error", s.call_tool("registry", {"op": "install", "name": "bad", "manifest": {"version": "0.1"}}))
        unsafe = {"name": "bad", "version": "0.1", "entry": "/etc/thing", "tests": "/ai/apps/bad/tests/run.sh", "tests_pass": True}
        self.assertIn("error", s.call_tool("registry", {"op": "install", "name": "bad", "manifest": unsafe}))

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


if __name__ == "__main__": unittest.main()
