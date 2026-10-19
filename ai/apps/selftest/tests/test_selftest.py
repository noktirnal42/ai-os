#!/usr/bin/env python3
"""Hermetic unit tests for selftest (doc 07 §11, F4-4).

Builds fixture registries and apps under temp directories; never touches /ai."""
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import selftest


def make_app(apps_dir, name, exit_code=0, env_snapshot=None):
    app_dir = os.path.join(apps_dir, name)
    os.makedirs(app_dir, exist_ok=True)
    body = "#!/bin/sh\n"
    if env_snapshot:
        body += "env > env.txt\n"
    body += f"exit {exit_code}\n"
    with open(os.path.join(app_dir, "tests", "run.sh"), "w") as handle:
        handle.write(body)
    os.chmod(os.path.join(app_dir, "tests", "run.sh"), 0o755)
    # keep tests/ creation explicit below for clarity


def make_registry(registry_path, entries):
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w") as handle:
        json.dump(entries, handle, indent=2, sort_keys=True)
        handle.write("\n")


class SelftestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="selftest-")
        self.apps_dir = os.path.join(self.tmp, "apps")
        self.state_dir = os.path.join(self.tmp, "state")
        self.registry_path = os.path.join(self.state_dir, "registry.json")
        os.makedirs(self.apps_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _report(self, registry_path=None, out_dir=None, timeout=selftest.TEST_TIMEOUT):
        return selftest.run_selftest(
            registry_path or self.registry_path,
            pathlib.Path(out_dir or self.state_dir),
            timeout=timeout,
        )

    def test_all_pass(self):
        for name, code in (("calc", 0), ("fileutils", 0), ("ask", 0)):
            app_dir = os.path.join(self.apps_dir, name)
            os.makedirs(os.path.join(app_dir, "tests"), exist_ok=True)
            with open(os.path.join(app_dir, "tests", "run.sh"), "w") as handle:
                handle.write(f"#!/bin/sh\nexit {code}\n")
            os.chmod(os.path.join(app_dir, "tests", "run.sh"), 0o755)
        make_registry(self.registry_path, {
            "calc": {"name": "calc", "tests": f"{self.apps_dir}/calc/tests/run.sh"},
            "fileutils": {"name": "fileutils", "tests": f"{self.apps_dir}/fileutils/tests/run.sh"},
            "ask": {"name": "ask", "tests": f"{self.apps_dir}/ask/tests/run.sh"},
        })
        report = self._report()
        self.assertTrue(report["all_pass"])
        self.assertEqual(report["count"], 3)
        self.assertEqual(report["passed"], 3)
        self.assertEqual(report["failed"], 0)
        for r in report["apps"]:
            self.assertTrue(r["passed"])
            self.assertEqual(r["exit_code"], 0)
            self.assertGreaterEqual(r["secs"], 0)
        reports = list(pathlib.Path(self.state_dir).glob("selftest-*.json"))
        self.assertEqual(len(reports), 1)
        with open(reports[0]) as handle:
            stored = json.load(handle)
        self.assertTrue(stored["all_pass"])
        self.assertEqual(stored["count"], 3)

    def test_one_failure_fails_report(self):
        app_dir = os.path.join(self.apps_dir, "bad")
        os.makedirs(os.path.join(app_dir, "tests"), exist_ok=True)
        with open(os.path.join(app_dir, "tests", "run.sh"), "w") as handle:
            handle.write("#!/bin/sh\necho boom >&2\nexit 3\n")
        os.chmod(os.path.join(app_dir, "tests", "run.sh"), 0o755)
        make_registry(self.registry_path, {
            "bad": {"name": "bad", "tests": f"{app_dir}/tests/run.sh"},
        })
        report = self._report()
        self.assertFalse(report["all_pass"])
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["passed"], 0)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["apps"][0]["exit_code"], 3) if False else None
        self.assertEqual(report["apps"][0]["exit_code"], 3)

    def test_missing_tests_file(self):
        make_registry(self.registry_path, {
            "ghost": {"name": "ghost", "tests": "/ai/apps/ghost/tests/run.sh"},
        })
        report = self._report()
        self.assertFalse(report["all_pass"])
        self.assertEqual(report["apps"][0]["error"], "no tests/run.sh")
        self.assertEqual(report["apps"][0]["output_hash"], "missing")

    def test_empty_registry_passes(self):
        make_registry(self.registry_path, {})
        report = self._report()
        self.assertTrue(report["all_pass"])
        self.assertEqual(report["count"], 0)

    def test_registry_file_missing(self):
        report = self._report(registry_path=os.path.join(self.tmp, "nope.json"))
        self.assertTrue(report["all_pass"])
        self.assertEqual(report["count"], 0)

    def test_sandbox_strips_network_and_model_env(self):
        app_dir = os.path.join(self.apps_dir, "envcheck")
        os.makedirs(os.path.join(app_dir, "tests"), exist_ok=True)
        with open(os.path.join(app_dir, "tests", "run.sh"), "w") as handle:
            handle.write("#!/bin/sh\nenv > env.txt\nexit 0\n")
        os.chmod(os.path.join(app_dir, "tests", "run.sh"), 0o755)
        os.environ["AIOS_ALLOW_NETWORK"] = "1"
        os.environ["AIOS_MODEL_URL"] = "http://10.0.2.2:8080"
        try:
            make_registry(self.registry_path, {
                "envcheck": {"name": "envcheck", "tests": f"{app_dir}/tests/run.sh"},
            })
            report = self._report()
        finally:
            del os.environ["AIOS_ALLOW_NETWORK"]
            del os.environ["AIOS_MODEL_URL"]
        self.assertTrue(report["all_pass"])
        env_text = pathlib.Path(app_dir, "tests", "env.txt").read_text()
        self.assertNotIn("AIOS_ALLOW_NETWORK", env_text)
        self.assertNotIn("AIOS_MODEL_URL", env_text)
        self.assertNotIn("AIOS_MODEL", env_text)

    def test_timeout(self):
        app_dir = os.path.join(self.apps_dir, "hang")
        os.makedirs(os.path.join(app_dir, "tests"), exist_ok=True)
        with open(os.path.join(app_dir, "tests", "run.sh"), "w") as handle:
            handle.write("#!/bin/sh\nsleep 999\n")
        os.chmod(os.path.join(app_dir, "tests", "run.sh"), 0o755)
        make_registry(self.registry_path, {
            "hang": {"name": "hang", "tests": f"{app_dir}/tests/run.sh"},
        })
        report = self._report(timeout=5)
        self.assertFalse(report["all_pass"])
        self.assertEqual(report["apps"][0]["exit_code"], None)
        self.assertEqual(report["apps"][0]["output_hash"], "timeout")


if __name__ == "__main__":
    unittest.main(verbosity=2)
