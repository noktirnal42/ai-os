#!/usr/bin/env python3
"""Hermetic unit tests for aipkg (doc 07 §10, F4-3).

All tests run against temporary directories (never /ai), so they are safe on
any host, with or without a guest VM."""
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import aipkg


class AppFixture:
    """Build a fake app under apps_dir: manifest.json, src/, tests/, entry point."""

    def __init__(self, apps_dir, bin_dir, name, version="0.1.0", lang="python",
                 failing_tests=False, with_src=True, with_tests=True, register=True):
        self.name = name
        self.version = version
        self.dir = os.path.join(apps_dir, name)
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(bin_dir, exist_ok=True)
        entry_path = os.path.join(bin_dir, name)
        manifest = {
            "name": name,
            "version": version,
            "entry": entry_path,
            "lang": lang,
            "tests": f"/ai/apps/{name}/tests/run.sh",
        }
        with open(os.path.join(self.dir, "manifest.json"), "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        if with_src:
            src = os.path.join(self.dir, "src")
            os.makedirs(src, exist_ok=True)
            with open(os.path.join(src, f"{name}.py"), "w") as handle:
                handle.write('print("hello from %s")\n' % name)
        if with_tests:
            tests = os.path.join(self.dir, "tests")
            os.makedirs(tests, exist_ok=True)
            body = "#!/bin/sh\nexit 0\n"
            if failing_tests:
                body = "#!/bin/sh\nexit 3\n"
            with open(os.path.join(tests, "run.sh"), "w") as handle:
                handle.write(body)
            os.chmod(os.path.join(tests, "run.sh"), 0o755)
        with open(entry_path, "w") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(entry_path, 0o755)
        if register:
            reg_path = os.path.join(os.path.dirname(apps_dir), "state", "registry.json")
            os.makedirs(os.path.dirname(reg_path), exist_ok=True)
            try:
                with open(reg_path) as handle:
                    reg = json.load(handle)
            except (OSError, json.JSONDecodeError):
                reg = {}
            reg[name] = {"name": name, "version": version, "entry": entry_path,
                         "lang": lang, "tests": manifest["tests"], "tests_pass": True}
            with open(reg_path, "w") as handle:
                json.dump(reg, handle, indent=2, sort_keys=True)
                handle.write("\n")


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aipkg-export-")
        self.apps_dir = os.path.join(self.tmp, "apps")
        self.bin_dir = os.path.join(self.tmp, "bin")
        self.out_dir = os.path.join(self.tmp, "out")
        self.registry_path = os.path.join(self.tmp, "state", "registry.json")
        os.makedirs(self.apps_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _member_names(self, tar_path):
        with tarfile.open(tar_path, "r") as tar:
            return {m.name for m in tar.getmembers()}

    def _read_member(self, tar_path, name):
        with tarfile.open(tar_path, "r") as tar:
            return tar.extractfile(name).read()

    def test_export_creates_tarball_with_all_components(self):
        AppFixture(self.apps_dir, self.bin_dir, "widget", version="1.2.0",
                   with_src=True, with_tests=True)
        rc = aipkg.export(["widget"], apps_dir=self.apps_dir, out_dir=self.out_dir,
                          registry_path=self.registry_path)
        self.assertEqual(rc, 0)
        tarball = os.path.join(self.out_dir, "widget-1.2.0.aipkg")
        self.assertTrue(os.path.isfile(tarball))
        names = self._member_names(tarball)
        self.assertIn("manifest.json", names)
        self.assertIn("registry.json", names)
        self.assertIn("entry", names)
        self.assertIn("src", names)
        self.assertIn("src/widget.py", names)
        self.assertIn("tests", names)
        manifest = json.loads(self._read_member(tarball, "manifest.json").decode())
        reg = json.loads(self._read_member(tarball, "registry.json").decode())
        entry = self._read_member(tarball, "entry").decode()
        self.assertEqual(manifest["name"], "widget")
        self.assertEqual(manifest["version"], "1.2.0")
        self.assertEqual(reg["tests_pass"], True)
        self.assertIn("#!/bin/sh", entry)

    def test_export_unregistered_app_writes_empty_registry_entry(self):
        AppFixture(self.apps_dir, self.bin_dir, "plain", register=False)
        rc = aipkg.export(["plain"], apps_dir=self.apps_dir, out_dir=self.out_dir,
                          registry_path=self.registry_path)
        self.assertEqual(rc, 0)
        reg = json.loads(self._read_member(
            os.path.join(self.out_dir, "plain-0.1.0.aipkg"), "registry.json").decode())
        self.assertEqual(reg, {})

    def test_export_multiple_apps(self):
        AppFixture(self.apps_dir, self.bin_dir, "one")
        AppFixture(self.apps_dir, self.bin_dir, "two")
        rc = aipkg.export(["one", "two"], apps_dir=self.apps_dir, out_dir=self.out_dir,
                          registry_path=self.registry_path)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "one-0.1.0.aipkg")))
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "two-0.1.0.aipkg")))

    def test_export_missing_app_errors(self):
        rc = aipkg.export(["no-such-app"], apps_dir=self.apps_dir, out_dir=self.out_dir,
                          registry_path=self.registry_path)
        self.assertEqual(rc, 1)

    def test_export_app_without_manifest_errors(self):
        os.makedirs(os.path.join(self.apps_dir, "manifestless"))
        rc = aipkg.export(["manifestless"], apps_dir=self.apps_dir, out_dir=self.out_dir,
                          registry_path=self.registry_path)
        self.assertEqual(rc, 1)

    def test_export_no_args_errors(self):
        self.assertEqual(aipkg.export([]), 2)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aipkg-install-")
        self.apps_dir = os.path.join(self.tmp, "apps")
        self.bin_dir = os.path.join(self.tmp, "bin")
        self.out_dir = os.path.join(self.tmp, "out")
        self.registry_path = os.path.join(self.tmp, "state", "registry.json")
        for d in (self.apps_dir, self.bin_dir, self.out_dir):
            os.makedirs(d)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_registry(self):
        try:
            with open(self.registry_path) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}

    def _build_package(self, name="widget", version="0.9.0", failing_tests=False,
                       no_tests=False, entry=None, lang="python"):
        """Create a .aipkg tarball in out_dir and return its path."""
        pkg_dir = tempfile.mkdtemp(prefix="pkg-")
        manifest = {
            "name": name, "version": version, "lang": lang,
            "entry": entry or f"/ai/bin/{name}",
            "tests": f"/ai/apps/{name}/tests/run.sh",
        }
        with open(os.path.join(pkg_dir, "manifest.json"), "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        with open(os.path.join(pkg_dir, "registry.json"), "w") as handle:
            json.dump({"name": name, "tests_pass": False}, handle)
        entry_path = os.path.join(pkg_dir, "entry")
        with open(entry_path, "w") as handle:
            handle.write(f"#!/bin/sh\nexec python3 /ai/apps/{name}/{name}.py \"$@\"\n")
        os.chmod(entry_path, 0o755)
        if not no_tests:
            tests_dir = os.path.join(pkg_dir, "tests")
            os.makedirs(tests_dir)
            body = "#!/bin/sh\npwd > cwd.txt\nexit 0\n"
            if failing_tests:
                body = "#!/bin/sh\nexit 7\n"
            with open(os.path.join(tests_dir, "run.sh"), "w") as handle:
                handle.write(body)
            os.chmod(os.path.join(tests_dir, "run.sh"), 0o755)
        src_dir = os.path.join(pkg_dir, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, f"{name}.py"), "w") as handle:
            handle.write('print("pkg")\n')
        tar_path = os.path.join(self.out_dir, f"{name}-{version}.aipkg")
        with tarfile.open(tar_path, "w") as tar:
            for arc in ("manifest.json", "registry.json", "entry"):
                tar.add(os.path.join(pkg_dir, arc), arcname=arc)
            tar.add(src_dir, arcname="src")
            if not no_tests:
                tar.add(os.path.join(pkg_dir, "tests"), arcname="tests")
        shutil.rmtree(pkg_dir)
        return tar_path

    def test_install_unpacks_runs_tests_registers(self):
        tar_path = self._build_package("widget", version="0.9.0")
        rc = aipkg.install(tar_path, apps_dir=self.apps_dir, bin_dir=self.bin_dir,
                           registry_path=self.registry_path)
        self.assertEqual(rc, 0)
        dest = os.path.join(self.apps_dir, "widget")
        self.assertTrue(os.path.isdir(dest))
        self.assertTrue(os.path.isfile(os.path.join(dest, "manifest.json")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "widget.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "tests", "run.sh")))
        self.assertEqual(os.path.realpath(pathlib.Path(os.path.join(dest, "cwd.txt")).read_text().strip()),
                         os.path.realpath(dest))
        entry = os.path.join(self.bin_dir, "widget")
        self.assertTrue(os.path.isfile(entry))
        self.assertTrue(os.access(entry, os.X_OK))
        reg = self._read_registry()
        self.assertTrue(reg["widget"]["tests_pass"])
        self.assertEqual(reg["widget"]["version"], "0.9.0")
        self.assertEqual(reg["widget"]["entry"], entry)

    def test_install_failing_tests_aborts_and_leaves_nothing(self):
        tar_path = self._build_package("broken", failing_tests=True)
        rc = aipkg.install(tar_path, apps_dir=self.apps_dir, bin_dir=self.bin_dir,
                           registry_path=self.registry_path)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(os.path.join(self.apps_dir, "broken")))
        self.assertNotIn("broken", self._read_registry())

    def test_install_missing_manifest_errors(self):
        tar_path = os.path.join(self.out_dir, "bad.aipkg")
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("notes.txt")
            info.size = 0
            tar.addfile(info, io.BytesIO(b""))
        self.assertEqual(aipkg.install(tar_path, apps_dir=self.apps_dir,
                                       bin_dir=self.bin_dir, registry_path=self.registry_path), 1)

    def test_install_without_tests_runsh_errors(self):
        tar_path = self._build_package("notests", no_tests=True)
        self.assertEqual(aipkg.install(tar_path, apps_dir=self.apps_dir,
                                       bin_dir=self.bin_dir, registry_path=self.registry_path), 1)
        self.assertFalse(os.path.exists(os.path.join(self.apps_dir, "notests")))

    def test_install_nonexistent_package_errors(self):
        self.assertEqual(aipkg.install(os.path.join(self.out_dir, "ghost.aipkg"),
                                       apps_dir=self.apps_dir, bin_dir=self.bin_dir,
                                       registry_path=self.registry_path), 1)

    def test_install_overwrites_previous_installation(self):
        tar_path = self._build_package("widget", version="0.9.0")
        self.assertEqual(aipkg.install(tar_path, apps_dir=self.apps_dir,
                                       bin_dir=self.bin_dir, registry_path=self.registry_path), 0)
        tar_path = self._build_package("widget", version="1.0.0")
        self.assertEqual(aipkg.install(tar_path, apps_dir=self.apps_dir,
                                       bin_dir=self.bin_dir, registry_path=self.registry_path), 0)
        reg = self._read_registry()
        self.assertEqual(reg["widget"]["version"], "1.0.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
