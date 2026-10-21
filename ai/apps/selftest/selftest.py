#!/usr/bin/env python3
"""selftest — AI OS app self-test runner (doc 07 §11, F4-4).

Runs every registered app's tests/run.sh in a sandboxed subprocess
(no AIOS_ALLOW_NETWORK / AIOS_MODEL_URL), prints a name/pass/secs table,
exits 0 iff all pass, and writes /ai/state/selftest-<ts>.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

AI_ROOT = pathlib.Path(os.environ.get("AIOS_ROOT", "/ai")).resolve()
REGISTRY_PATH = AI_ROOT / "state" / "registry.json"
STATE_DIR = AI_ROOT / "state"
TEST_TIMEOUT = 300


def load_registry(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sandbox_env():
    env = dict(os.environ)
    for key in ("AIOS_ALLOW_NETWORK", "AIOS_MODEL_URL", "AIOS_MODEL"):
        env.pop(key, None)
    return env


def run_one(name, tests_path, timeout=TEST_TIMEOUT):
    started = time.monotonic()
    try:
        result = subprocess.run(
            ["/bin/sh", str(tests_path)],
            cwd=str(pathlib.Path(tests_path).parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=sandbox_env(),
        )
        elapsed = time.monotonic() - started
        passed = result.returncode == 0
        digest = hashlib.sha256(
            (result.stdout + result.stderr).encode()
        ).hexdigest()[:16]
        return {
            "name": name,
            "passed": passed,
            "exit_code": result.returncode,
            "secs": round(elapsed, 3),
            "output_hash": digest,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return {
            "name": name,
            "passed": False,
            "exit_code": None,
            "secs": round(elapsed, 3),
            "output_hash": "timeout",
            "error": "timeout",
        }


def run_selftest(registry_path=REGISTRY_PATH, state_dir=STATE_DIR, timeout=TEST_TIMEOUT):
    registry = load_registry(registry_path)
    results = []
    for name in sorted(registry):
        entry = registry[name]
        tests = entry.get("tests")
        if not tests or not pathlib.Path(tests).is_file():
            results.append({
                "name": name,
                "passed": False,
                "exit_code": None,
                "secs": 0.0,
                "output_hash": "missing",
                "error": "no tests/run.sh",
            })
            continue
        results.append(run_one(name, tests, timeout=timeout))
    all_pass = all(r["passed"] for r in results)
    report = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ"),
        "registry": str(registry_path),
        "apps": results,
        "count": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "all_pass": all_pass,
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"selftest-{report['timestamp']}.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    width = max([len(r["name"]) for r in results] + [4])
    print(f"{'name':<{width}}  pass  secs")
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"{r['name']:<{width}}  {mark:<4} {r['secs']}")
    print(
        f"{report['passed']}/{report['count']} apps passed; all_pass={all_pass}"
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="selftest", description="AI OS app self-test runner")
    parser.add_argument("--registry", default=str(REGISTRY_PATH),
                        help="registry.json path (default /ai/state/registry.json)")
    parser.add_argument("--out-dir", default=str(STATE_DIR),
                        help="directory for selftest-<ts>.json reports")
    args = parser.parse_args(argv)
    report = run_selftest(args.registry, pathlib.Path(args.out_dir))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
