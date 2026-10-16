#!/usr/bin/env python3
"""Ask AI OS to build a line-count utility and score hidden guest tests."""
from __future__ import annotations

import json
import hashlib
import argparse
import os
import pathlib
import re
import resource
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone


ALLOWED_HEADERS = {
    "stdio.h", "stdlib.h", "string.h", "sys/types.h", "errno.h", "limits.h",
    "stdint.h",
}
DANGEROUS_SOURCE = re.compile(
    r"\b(system|popen|fork|vfork|exec\w*|socket|connect|accept|bind|listen|"
    r"unlink|remove|rename|chmod|chown|mkdir|rmdir|fopen|freopen|dlopen|"
    r"ptrace|syscall)\s*\(|__asm__|\basm\s*\(",
)


def run_limited_command(
    command: list[str], input_bytes: bytes, cwd: pathlib.Path, tmp_dir: pathlib.Path,
) -> dict[str, object]:
    """Run a guest-built app with short CPU, memory, file, and wall-clock limits."""
    def limit_child() -> None:
        limits = (
            (resource.RLIMIT_CPU, (2, 3)),
            (resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024)),
            (resource.RLIMIT_FSIZE, (64 * 1024, 64 * 1024)),
            (resource.RLIMIT_NOFILE, (32, 32)),
            (resource.RLIMIT_CORE, (0, 0)),
        )
        for key, value in limits:
            try:
                resource.setrlimit(key, value)
            except (OSError, ValueError):
                pass

    env = {"PATH": "/usr/bin:/bin", "HOME": "/ai/tmp", "LANG": "C"}
    with tempfile.TemporaryFile(dir=tmp_dir) as stdout_file, tempfile.TemporaryFile(dir=tmp_dir) as stderr_file:
        try:
            process = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                stdout=stdout_file, stderr=stderr_file, start_new_session=True,
                preexec_fn=limit_child,
            )
            try:
                process.communicate(input=input_bytes, timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                return {"returncode": process.returncode, "stdout": "", "stderr": "timeout", "timed_out": True}
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(64 * 1024 + 1)
            stderr = stderr_file.read(64 * 1024 + 1)
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "timed_out": False,
                "output_limited": len(stdout) > 64 * 1024 or len(stderr) > 64 * 1024,
            }
        except (OSError, subprocess.SubprocessError) as exc:
            return {"returncode": None, "stdout": "", "stderr": str(exc), "timed_out": False}


def run_limited(binary: pathlib.Path, input_bytes: bytes, cwd: pathlib.Path, tmp_dir: pathlib.Path) -> dict[str, object]:
    return run_limited_command([str(binary)], input_bytes, cwd, tmp_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-existing", help="rescore an existing /ai/apps/<name> using prior AI OS session evidence")
    options = parser.parse_args()
    root = pathlib.Path(os.environ.get("AIOS_ROOT", "/ai")).resolve()
    model_url = os.environ.get("AIOS_MODEL_URL", "")
    model = os.environ.get("AIOS_MODEL", "")
    aios = pathlib.Path(os.environ.get("AIOS_BIN", "/ai/bin/aios"))
    if not options.score_existing and (not model_url or not model):
        print("AIOS_MODEL_URL and AIOS_MODEL are required", file=sys.stderr)
        return 2
    if not options.score_existing and not aios.is_file():
        print(f"AI OS executable not found: {aios}", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    name = options.score_existing or "linecount-eval-" + run_id
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", name):
        print("invalid app name", file=sys.stderr)
        return 2
    app = root / "apps" / name
    entry = root / "bin" / name
    source = app / "src" / "main.c"
    test = app / "tests" / "run.sh"
    manifest_path = app / "manifest.json"
    compiler_command = f"gcc -Wall -Wextra -Werror {source} -o {entry}"
    acceptance_command = f"/bin/sh {test}"
    goal = f'''Build a useful C command-line app named {name} entirely inside /ai. It reads stdin and prints the number of lines as a decimal integer followed by a newline. Use getchar() and compare its int result to EOF. Treat byte value 10 as a newline; count each newline as one line; if input is nonempty and the final byte is not 10, count one more line. Empty input has zero lines and blank lines count. Do not use an escaped newline character literal.
Create /ai/apps/{name}/src/main.c, /ai/apps/{name}/tests/run.sh, and /ai/apps/{name}/manifest.json using fs_write. The manifest must be valid JSON with exactly these fields: name {name}, version 0.1.0, entry /ai/bin/{name}, tests /ai/apps/{name}/tests/run.sh.
The acceptance script must test `alpha` and print LINECOUNT_SELF_TEST_PASS only when the output is `1`. Use this exact safe POSIX shell content:
#!/bin/sh
set -eu
actual=$(printf alpha | /ai/bin/{name})
[ "$actual" = "1" ]
echo LINECOUNT_SELF_TEST_PASS
Do not create or modify fixture files. Compile with this exact command: {compiler_command}. Set workdir to /ai/apps/{name}. Then run this exact acceptance command: {acceptance_command} with workdir /ai/apps/{name}; inspect its exit code and LINECOUNT_SELF_TEST_PASS output. Do not register or install the app, call ask_human, use network, or modify other apps or system paths. Finish only after both required commands pass.'''

    sessions_dir = root / "state" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    output = ""
    returncode = 0 if options.score_existing else 124
    if options.score_existing:
        matching_sessions = []
        for path in sorted(sessions_dir.glob("*.jsonl")):
            try:
                rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            except (OSError, json.JSONDecodeError):
                continue
            if rows and rows[0].get("ev") == "session_start" and name in json.dumps(rows):
                matching_sessions.append((path, rows))
        session_path = matching_sessions[-1][0] if matching_sessions else None
        events = [event for _, rows in matching_sessions for event in rows]
        if matching_sessions:
            model = matching_sessions[-1][1][0].get("model", model)
        output = f"Rescoring {name} from {len(matching_sessions)} matching AI OS sessions"
    else:
        before = set(sessions_dir.glob("*.jsonl"))
        env = {**os.environ, "AIOS_ROOT": str(root), "AIOS_MODEL_URL": model_url, "AIOS_MODEL": model}
        try:
            proc = subprocess.run(
                [
                    str(aios), "run", "--max-tools", "36", "--max-seconds", "420",
                    "--require-command", compiler_command,
                    "--require-command", acceptance_command,
                    goal,
                ], text=True, capture_output=True, timeout=450, env=env,
            )
            output = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
            returncode = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            output = stdout + "\nAI OS session timed out after 450 seconds\n" + stderr

        new_sessions = sorted(
            (path for path in sessions_dir.glob("*.jsonl") if path not in before),
            key=lambda path: path.stat().st_mtime,
        )
        session_path = new_sessions[-1] if new_sessions else None
        try:
            events = [json.loads(line) for line in session_path.read_text().splitlines() if line.strip()] if session_path else []
        except (OSError, json.JSONDecodeError):
            events = []

    expected_manifest = {
        "name": name, "version": "0.1.0", "entry": f"/ai/bin/{name}",
        "tests": f"/ai/apps/{name}/tests/run.sh",
    }
    expected_test = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"actual=$(printf alpha | /ai/bin/{name})\n"
        "[ \"$actual\" = \"1\" ]\n"
        "echo LINECOUNT_SELF_TEST_PASS"
    )
    checks: dict[str, bool] = {
        "session_returned_zero": returncode == 0 if not options.score_existing else any(
            event.get("ev") == "verdict" and event.get("kind") == "succeeded" and event.get("verified") is True
            for event in events
        ),
        "session_log_found": session_path is not None,
        "source_created": source.is_file() and not source.is_symlink(),
        "test_created": test.is_file() and not test.is_symlink(),
        "manifest_created": manifest_path.is_file() and not manifest_path.is_symlink(),
        "binary_created": entry.is_file() and not entry.is_symlink(),
        "model_did_not_request_install": not any(
            event.get("ev") == "tool_call" and event.get("tool") in {"registry", "ask_human"}
            for event in events
        ),
    }
    try:
        source_text = source.read_text(encoding="utf-8") if checks["source_created"] else ""
        test_text = test.read_text(encoding="utf-8") if checks["test_created"] else ""
        manifest = json.loads(manifest_path.read_text()) if checks["manifest_created"] else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        source_text, test_text, manifest = "", "", None
    headers = re.findall(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", source_text, flags=re.M)
    checks["source_policy_safe"] = (
        bool(headers)
        and all(header in ALLOWED_HEADERS for header in headers)
        and DANGEROUS_SOURCE.search(source_text) is None
    )
    checks["test_matches_safe_template"] = test_text.removesuffix("\n") == expected_test
    checks["manifest_matches"] = manifest == expected_manifest

    writes = {
        event.get("args", {}).get("path")
        for event in events
        if event.get("ev") == "tool_call" and event.get("tool") == "fs_write"
        and isinstance(event.get("args"), dict)
    }
    checks["model_wrote_all_three_files"] = all(str(path) in writes for path in (source, test, manifest_path))
    successful_shell_calls = [
        event.get("args", {}).get("cmd")
        for index, event in enumerate(events[:-1])
        if event.get("ev") == "tool_call" and event.get("tool") == "shell"
        and isinstance(event.get("args"), dict)
        and events[index + 1].get("ev") == "tool_result"
        and events[index + 1].get("tool") == "shell"
        and events[index + 1].get("command_exit") == 0
    ]
    checks["model_called_compiler"] = compiler_command in successful_shell_calls
    checks["model_ran_acceptance"] = acceptance_command in successful_shell_calls
    checks["harness_verified_required_commands"] = any(
        event.get("ev") == "verdict" and event.get("kind") == "succeeded"
        and event.get("verified") is True
        and event.get("required_commands") == [compiler_command, acceptance_command]
        for event in events
    )

    try:
        header = entry.read_bytes()[:4] if checks["binary_created"] else b""
    except OSError:
        header = b""
    checks["binary_is_guest_elf"] = header == b"\x7fELF"
    hidden_cases = [
        {"name": "empty_input", "input": b"", "expected": "0\n"},
        {"name": "one_line", "input": b"alpha\n", "expected": "1\n"},
        {"name": "missing_final_newline", "input": b"alpha\nbeta", "expected": "2\n"},
        {"name": "blank_lines", "input": b"\n\n", "expected": "2\n"},
        {"name": "mixed_lines", "input": b"alpha\n\nbeta\n", "expected": "3\n"},
    ]
    many_lines = [f"line-{index:04d}" for index in range(512)]
    hidden_cases.append({
        "name": "many_lines",
        "input": ("\n".join(many_lines) + "\n").encode(),
        "expected": "512\n",
    })
    hidden_cases.append({
        "name": "long_line",
        "input": b"x" * (64 * 1024),
        "expected": "1\n",
    })
    safe_to_execute = checks["source_policy_safe"] and checks["binary_is_guest_elf"]
    case_results = []
    if safe_to_execute:
        for case in hidden_cases:
            run = run_limited(entry, case["input"], app, root / "tmp")
            passed = (
                run.get("returncode") == 0
                and run.get("stdout") == case["expected"]
                and not run.get("timed_out", False)
                and not run.get("output_limited", False)
            )
            case_results.append({"name": case["name"], "pass": passed, **run})
    checks["hidden_cases_pass"] = len(case_results) == len(hidden_cases) and all(row["pass"] for row in case_results)

    checks["acceptance_passes"] = False
    checks["acceptance_rejects_bad_binary"] = False
    checks["binary_restored"] = False
    backup = root / "tmp" / f"{name}.original"
    if safe_to_execute and checks["test_matches_safe_template"] and checks["hidden_cases_pass"]:
        try:
            positive = run_limited_command(["/bin/sh", str(test)], b"", app, root / "tmp")
            checks["acceptance_passes"] = (
                positive.get("returncode") == 0 and "LINECOUNT_SELF_TEST_PASS" in positive.get("stdout", "")
                and not positive.get("timed_out", False)
            )
        except (OSError, subprocess.SubprocessError):
            positive = None
        original_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, backup)
            entry.write_text("#!/bin/sh\nexit 1\n")
            entry.chmod(stat.S_IMODE(backup.stat().st_mode))
            negative = run_limited_command(["/bin/sh", str(test)], b"", app, root / "tmp")
            checks["acceptance_rejects_bad_binary"] = negative.get("returncode") not in {None, 0} and not negative.get("timed_out", False)
        except (OSError, subprocess.SubprocessError):
            checks["acceptance_rejects_bad_binary"] = False
        finally:
            if backup.is_file():
                shutil.copy2(backup, entry)
                backup.unlink()
        try:
            checks["binary_restored"] = hashlib.sha256(entry.read_bytes()).hexdigest() == original_hash
        except OSError:
            checks["binary_restored"] = False

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "model_url": model_url,
        "app": name,
        "session": session_path.name if session_path else None,
        "returncode": returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "hidden_case_results": case_results,
        "pass": all(checks.values()),
    }
    eval_dir = root / "state" / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{name}.out").write_text(output)
    with (eval_dir / "live-app-build.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")

    print(output.rstrip())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
