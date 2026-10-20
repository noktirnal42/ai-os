#!/usr/bin/env python3
import io
import json
import curses
import os
import subprocess
import pathlib
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import aios
import aios_tui


class HarnessTests(unittest.TestCase):
    def test_tui_progress_labels_audit_events_without_echoing_tool_args(self):
        self.assertEqual(aios_tui.event_message({"ev": "tool_call", "tool": "shell", "args": {"cmd": "secret"}}), "Running a command")
        self.assertEqual(aios_tui.event_message({"ev": "tool_result", "command_exit": 0}), "Command finished (exit 0)")
        self.assertEqual(aios_tui.event_message({"ev": "verdict", "kind": "failed", "error": "timed out"}), "Task failed: timed out")

    def test_tui_chat_and_do_modes_have_separate_bounded_commands(self):
        chat = aios_tui.command_for("chat", "hello")
        do = aios_tui.command_for("do", "build a tool")
        self.assertEqual(chat[-2:], ["ask", "hello"])
        self.assertIn("--max-tools", do)
        self.assertIn("--max-seconds", do)
        self.assertEqual(do[-1], "build a tool")

    def test_tui_accepts_curses_wide_character_input_not_control_keys(self):
        self.assertEqual(aios_tui.input_character("a"), "a")
        self.assertEqual(aios_tui.input_character("?"), "?")
        self.assertIsNone(aios_tui.input_character(97))
        self.assertIsNone(aios_tui.input_character(curses.KEY_UP))
        self.assertTrue(aios_tui.is_enter_key("\n"))
        self.assertTrue(aios_tui.is_enter_key(13))
        self.assertTrue(aios_tui.is_backspace_key("\x7f"))
        partial = {"kind": "partial"}
        self.assertIn("without taking action", aios_tui.completion_status("do", 0, partial, False))
        self.assertIn("used tools", aios_tui.completion_status("do", 0, partial, True))
        self.assertIn("Waiting for qwen", aios_tui.progress_status("model", "", 12, "qwen2.5-coder:3b", 300))
        self.assertIn("Running a command", aios_tui.progress_status("tool", "Running a command", 4, "qwen", 300))

    def test_model_config_persists_defaults_but_environment_overrides_it(self):
        (self.root / "state" / "model.json").write_text(json.dumps({
            "url": "http://10.0.2.2:11434", "model": "qwen2.5-coder:3b", "timeout_seconds": 300,
        }))
        with mock.patch.dict(os.environ, {"AIOS_MODEL_URL": "", "AIOS_MODEL": "", "AIOS_MODEL_TIMEOUT": ""}, clear=False):
            aios.load_model_config()
            self.assertEqual(os.environ["AIOS_MODEL_URL"], "http://10.0.2.2:11434")
            self.assertEqual(os.environ["AIOS_MODEL"], "qwen2.5-coder:3b")
            self.assertEqual(os.environ["AIOS_MODEL_TIMEOUT"], "300")

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

    def test_shell_schema_object_from_small_models_is_normalized(self):
        s = self.session()
        result = s.call_tool("shell", {"cmd": {"type": "string", "cmd": "printf MODEL_TOOL_OK", "workdir": str(self.root)}})
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["stdout"], "MODEL_TOOL_OK")

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

    def test_install_verdict_comes_from_acceptance_tests_not_model_wording(self):
        self.prepare_app("verdict-app", "exit 0\n")
        class FakeClient:
            offline = False
            def __init__(self): self.calls = 0
            def chat(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    args = {"op": "install", "name": "verdict-app"}
                    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "registry", "arguments": json.dumps(args)}}]}}]}
                return {"choices": [{"message": {"role": "assistant", "content": "I am not sure it worked."}}]}
        session = aios.Session("install it", FakeClient(), max_tools=4, max_seconds=5)
        with mock.patch.object(session, "ask_human", return_value={"approved": True}):
            self.assertEqual(session.run(), 0)
        self.assertIn("verdict-app", session.verified_installs)
        rows = [json.loads(line) for line in session.log.path.read_text().splitlines()]
        verdict = next(row for row in rows if row["ev"] == "verdict")
        self.assertEqual(verdict["kind"], "succeeded")
        self.assertTrue(verdict["verified"])

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

    def test_task_state_summary_reads_shared_list_and_fails_closed(self):
        tasks_path = self.root / "state" / "tasks.json"
        tasks_path.write_text(json.dumps({"tasks": [
            {"id": 1, "title": "write step", "status": "done", "depends": [], "acceptance_cmd": "true"},
            {"id": 2, "title": "second step", "status": "pending", "depends": [1], "acceptance_cmd": "test -f /ai/apps/ok"},
            {"id": 3, "title": "broken step", "status": "failed", "depends": [], "acceptance_cmd": ""},
        ]}))
        summary = aios.task_state_summary()
        self.assertIn("[2] second step (pending) depends:1 acceptance:test -f /ai/apps/ok", summary)
        self.assertIn("[3] broken step (failed)", summary)
        self.assertNotIn("[1]", summary)
        tasks_path.write_text("{corrupt json")
        self.assertIsNone(aios.task_state_summary())
        with mock.patch.dict(os.environ, {"AIOS_TASKS_FILE": str(self.root / "state" / "elsewhere.json")}):
            self.assertIsNone(aios.task_state_summary())

    def test_resume_goal_brief_includes_unfinished_tasks_and_original_goal(self):
        (self.root / "state" / "tasks.json").write_text(json.dumps({"tasks": [
            {"id": 1, "title": "done thing", "status": "done"},
            {"id": 2, "title": "resume thing", "status": "active", "acceptance_cmd": "echo ok"},
        ]}))
        goal = aios.resume_goal("build the widget")
        self.assertIn("[2] resume thing (active)", goal)
        self.assertIn("Original session goal: build the widget", goal)
        self.assertNotIn("[1]", goal)
        (self.root / "state" / "tasks.json").write_text(json.dumps({"tasks": [
            {"id": 1, "title": "done", "status": "done"}]}))
        self.assertIsNone(aios.resume_goal("anything"))

    def test_run_injects_task_state_and_refreshes_when_list_changes(self):
        root = self.root
        (root / "state" / "tasks.json").write_text(json.dumps({"tasks": [
            {"id": 1, "title": "finish it", "status": "pending", "acceptance_cmd": "true"}]}))
        seen = []
        class FakeClient:
            offline = False
            def __init__(self): self.calls = 0
            def chat(self, messages, tools):
                self.calls += 1
                seen.append(messages[1]["content"])
                if self.calls == 1:
                    args = {"path": str(root / "state" / "tasks.json"),
                            "content": json.dumps({"tasks": [{"id": 1, "title": "finish it", "status": "done", "acceptance_cmd": "true"}]})}
                    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
                        {"id": "1", "function": {"name": "fs_write", "arguments": json.dumps(args)}}]}}]}
                return {"choices": [{"message": {"role": "assistant", "content": "all done"}}]}
        session = aios.Session("task injection", FakeClient(), max_tools=4, max_seconds=5, resumes="prior-sid")
        self.assertEqual(session.run(), 0)
        self.assertIn("[1] finish it (pending)", seen[0])
        self.assertNotIn("[1]", seen[1])
        rows = [json.loads(line) for line in session.log.path.read_text().splitlines()]
        start = next(r for r in rows if r["ev"] == "session_start")
        self.assertEqual(start["resumes"], "prior-sid")
        refresh = [r for r in rows if r["ev"] == "task_state_refresh"]
        self.assertEqual(len(refresh), 1)

    def test_session_goal_recovery_from_audit_log(self):
        log_dir = self.root / "state" / "sessions"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "sid-abc.jsonl").write_text(
            json.dumps({"ev": "session_start", "goal": "write the browser"}) + "\n" +
            json.dumps({"ev": "tool_call"}) + "\n")
        self.assertEqual(aios.session_goal_from_log("sid-abc"), "write the browser")
        self.assertIsNone(aios.session_goal_from_log("missing-sid"))
        self.assertIsNone(aios.session_goal_from_log("../escape"))


    def test_ask_human_reads_one_answer_and_logs_the_request(self):
        s = self.session()
        with mock.patch("sys.stdin", io.StringIO("yes\n")), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(s.ask_human({"question": "Install?"}), {"approved": True})
        rows = [json.loads(line) for line in (self.root / "state" / "sessions").glob("*.jsonl").__next__().read_text().splitlines()]
        self.assertEqual([r["ev"] for r in rows if r["ev"].startswith("gate")], ["gate_request", "gate"])

    def test_ask_human_denies_when_no_one_can_answer(self):
        s = self.session()
        with mock.patch("sys.stdin", io.StringIO("")), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(s.ask_human({"question": "Install?"})["approved"], False)

    def test_tui_gate_keys_map_to_the_harness_answer_line(self):
        self.assertEqual(aios_tui.gate_answer("y"), b"y\n")
        self.assertEqual(aios_tui.gate_answer("Y"), b"y\n")
        self.assertEqual(aios_tui.gate_answer("\n"), b"n\n")
        self.assertEqual(aios_tui.gate_answer(13), b"n\n")
        self.assertEqual(aios_tui.gate_answer("n"), b"n\n")
        self.assertIsNone(aios_tui.gate_answer("x"))
        self.assertIsNone(aios_tui.gate_answer(-1))

    def test_registry_install_through_a_pipe_needs_a_yes_and_nothing_else(self):
        self.prepare_app("piped", "exit 0\n")
        script = pathlib.Path(aios.__file__)
        env = {**os.environ, "AIOS_ROOT": str(self.root)}
        denied = subprocess.run([sys.executable, str(script), "registry", "install", "piped"],
                                input="", text=True, capture_output=True, env=env)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("not approved", denied.stderr)
        self.assertFalse((self.root / "state" / "registry.json").exists())
        approved = subprocess.run([sys.executable, str(script), "registry", "install", "piped"],
                                  input="y\n", text=True, capture_output=True, env=env)
        self.assertEqual(approved.returncode, 0, approved.stderr)
        registry = json.loads((self.root / "state" / "registry.json").read_text())
        self.assertTrue(registry["piped"]["tests_pass"])


    def test_model_cannot_request_approvals_itself(self):
        s = self.session()
        names = [t["function"]["name"] for t in aios.TOOLS]
        self.assertNotIn("ask_human", names)
        result = s.call_tool("ask_human", {"question": "Install anything?"})
        self.assertIn("error", result)
        self.assertIn("harness", result["error"])

    def test_registry_remove_requires_human_approval(self):
        self.prepare_app("kept", "exit 0\n")
        registry = self.root / "state" / "registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"kept": {"name": "kept", "version": "0.1.0"}}))
        s = self.session()
        with mock.patch.object(s, "ask_human", return_value={"approved": False}):
            with self.assertRaises(PermissionError):
                s.registry({"op": "remove", "name": "kept"})
        self.assertIn("kept", json.loads(registry.read_text()))
        with mock.patch.object(s, "ask_human", return_value={"approved": True}):
            s.registry({"op": "remove", "name": "kept"})
        self.assertNotIn("kept", json.loads(registry.read_text()))

    def test_model_cannot_remove_apps_or_see_remove_in_its_tools(self):
        self.prepare_app("kept", "exit 0\n")
        registry = self.root / "state" / "registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"kept": {"name": "kept", "version": "0.1.0"}}))
        schema = next(t["function"] for t in aios.TOOLS if t["function"]["name"] == "registry")
        self.assertEqual(schema["parameters"]["properties"]["op"]["enum"], ["install", "query"])
        s = self.session()
        with mock.patch.object(s, "ask_human", return_value={"approved": True}):
            result = s.call_tool("registry", {"op": "remove", "name": "kept"})
        self.assertIn("error", result)
        self.assertIn("kept", json.loads(registry.read_text()))


if __name__ == "__main__": unittest.main()
