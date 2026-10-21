#!/usr/bin/env python3
"""aipkg — AI OS package export/install (doc 07 §10, F4-3).

aipkg export NAME... → /ai/out/NAME-<ver>.aipkg
    Tarball containing: manifest.json, registry.json (the app's registry entry,
    or {} when unregistered), entry (deployable copy of the manifest entry
    point), src/ (the app's sources: a src/ directory and/or root-level .py
    files), tests/ (when present).
aipkg install FILE → unpack tarball, run tests/run.sh, register in
    /ai/state/registry.json and create the entry point under /ai/bin/.

Designed so a package exported on one machine can be installed and
self-tested on another (AC-5: machine #2 test).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

AI_ROOT = os.environ.get("AIOS_ROOT", "/ai")
APPS_DIR = os.path.join(AI_ROOT, "apps")
BIN_DIR = os.path.join(AI_ROOT, "bin")
OUT_DIR = os.path.join(AI_ROOT, "out")
REGISTRY_PATH = os.path.join(AI_ROOT, "state", "registry.json")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def die(msg, code=EXIT_ERROR):
    print(f"aipkg: {msg}", file=sys.stderr)
    return code


def load_registry(registry_path=REGISTRY_PATH):
    try:
        with open(registry_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_registry(reg, registry_path=REGISTRY_PATH):
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as handle:
        json.dump(reg, handle, indent=2, sort_keys=True)
        handle.write("\n")


def app_dir(name, apps_dir=APPS_DIR):
    return os.path.join(apps_dir, name)


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def copy_tree(src, dst):
    shutil.copytree(src, dst)


def _extract_all(tar, dest):
    try:
        tar.extractall(dest, filter="data")
    except TypeError:  # older Pythons lack the filter argument
        tar.extractall(dest)


def export(names, apps_dir=APPS_DIR, out_dir=OUT_DIR, registry_path=REGISTRY_PATH):
    if not names:
        return die("usage: aipkg export NAME [NAME...]", EXIT_USAGE)
    os.makedirs(out_dir, exist_ok=True)
    registry = load_registry(registry_path)
    failures = []
    for name in names:
        ad = app_dir(name, apps_dir)
        if not os.path.isdir(ad):
            failures.append(f"{name}: app directory not found ({ad})")
            continue
        manifest_path = os.path.join(ad, "manifest.json")
        if not os.path.isfile(manifest_path):
            failures.append(f"{name}: manifest.json not found")
            continue
        try:
            manifest = json.loads(read_text(manifest_path))
        except json.JSONDecodeError as exc:
            failures.append(f"{name}: manifest.json is not valid JSON: {exc}")
            continue
        version = manifest.get("version", "0.0.0")
        out_name = f"{name}-{version}.aipkg"
        out_path = os.path.join(out_dir, out_name)

        registry_entry = registry.get(name, {})
        entry_path = manifest.get("entry")

        # Entry point to deploy: prefer the installed entry file; for Python apps
        # fall back to a generated wrapper over the app root module so an
        # exported package is self-contained even when /ai/bin/<name> is absent.
        entry_content = None
        if entry_path and os.path.isfile(entry_path):
            entry_content = read_text(entry_path)
        elif manifest.get("lang") == "python":
            candidate = os.path.join(ad, f"{name}.py")
            if os.path.isfile(candidate):
                entry_content = f"#!/bin/sh\nexec python3 {candidate} \"$@\"\n"

        try:
            with tarfile.open(out_path, "w") as tar:
                data = json.dumps(registry_entry, indent=2, sort_keys=True).encode()
                info = tarfile.TarInfo("registry.json")
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))

                tar.add(manifest_path, arcname="manifest.json")

                if entry_content is not None:
                    data = entry_content.encode()
                    info = tarfile.TarInfo("entry")
                    info.size = len(data)
                    info.mode = 0o755
                    tar.addfile(info, io.BytesIO(data))

                # src/: the src/ directory if present, plus root-level .py files.
                src_added = False
                src_dir = os.path.join(ad, "src")
                if os.path.isdir(src_dir):
                    tar.add(src_dir, arcname="src", recursive=True)
                    src_added = True
                for entry in sorted(os.listdir(ad)):
                    full = os.path.join(ad, entry)
                    if os.path.isfile(full) and entry.endswith(".py"):
                        tar.add(full, arcname=f"src/{entry}")
                        src_added = True

                tests_dir = os.path.join(ad, "tests")
                if os.path.isdir(tests_dir):
                    tar.add(tests_dir, arcname="tests", recursive=True)
        except OSError as exc:
            failures.append(f"{name}: cannot write {out_path}: {exc}")
            continue
        print(f"exported {out_path}")
    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def install(path, apps_dir=APPS_DIR, bin_dir=BIN_DIR, registry_path=REGISTRY_PATH):
    if not os.path.isfile(path):
        return die(f"package not found: {path}")
    tmp = tempfile.mkdtemp(prefix="aipkg-install-")
    try:
        with tarfile.open(path, "r") as tar:
            _extract_all(tar, tmp)
        manifest_path = os.path.join(tmp, "manifest.json")
        if not os.path.isfile(manifest_path):
            return die("package is missing manifest.json")
        try:
            manifest = json.loads(read_text(manifest_path))
        except json.JSONDecodeError as exc:
            return die(f"manifest.json is not valid JSON: {exc}")
        name = manifest.get("name")
        version = manifest.get("version", "0.0.0")
        if not name or not isinstance(name, str):
            return die("manifest.json has no usable name")
        dest = app_dir(name, apps_dir)
        entry_path = manifest.get("entry")
        entry_dest = os.path.join(bin_dir, os.path.basename(entry_path)) if entry_path else None

        # Fresh install destination (reinstalling replaces the previous copy).
        if os.path.exists(dest):
            shutil.rmtree(dest)

        # Stage: unpack sources into the app root, write manifest.
        src_dir = os.path.join(tmp, "src")
        tests_dir = os.path.join(tmp, "tests")
        if os.path.isdir(src_dir):
            copy_tree(src_dir, dest)
        if os.path.isdir(tests_dir):
            copy_tree(tests_dir, os.path.join(dest, "tests"))
        write_text(os.path.join(dest, "manifest.json"),
                   json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        # Run the app's acceptance tests before committing anything visible.
        run_tests = os.path.join(dest, "tests", "run.sh")
        if not os.path.isfile(run_tests):
            shutil.rmtree(dest, ignore_errors=True)
            return die(f"package {name} has no tests/run.sh")
        result = subprocess.run(["/bin/sh", run_tests], cwd=dest,
                                capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            output = (result.stdout + "\n" + result.stderr).strip()
            return die(f"{name}: acceptance tests failed (exit {result.returncode}):\n{output}")

        # Commit: entry point + registry entry.
        reg = load_registry(registry_path)
        entry_src = os.path.join(tmp, "entry") if os.path.isfile(os.path.join(tmp, "entry")) else entry_path
        if entry_src and os.path.isfile(entry_src):
            shutil.copyfile(entry_src, entry_dest)
            os.chmod(entry_dest, 0o755)
        reg[name] = {
            "name": name,
            "version": version,
            "entry": entry_dest or manifest.get("entry"),
            "lang": manifest.get("lang"),
            "tests": manifest.get("tests"),
            "tests_pass": True,
        }
        save_registry(reg, registry_path)
        print(f"installed {name} {version} → {entry_dest or entry_path}")
        print(f"registered in {registry_path} (tests_pass=true)")
        return EXIT_OK
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aipkg", description="AI OS package export/install")
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="export app(s) to .aipkg tarballs under /ai/out/")
    ex.add_argument("names", nargs="+", help="app names (as in /ai/apps/)")
    ins = sub.add_parser("install", help="install a .aipkg tarball (unpack, test, register)")
    ins.add_argument("file", help="path to a .aipkg tarball")
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.names)
    return install(args.file)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
