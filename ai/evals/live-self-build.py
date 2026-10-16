#!/usr/bin/env python3
"""Run and independently score one live AI OS app-build task in the guest."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


def main() -> int:
    root = pathlib.Path(os.environ.get("AIOS_ROOT", "/ai")).resolve()
    model_url = os.environ.get("AIOS_MODEL_URL", "")
    model = os.environ.get("AIOS_MODEL", "")
    aios = pathlib.Path(os.environ.get("AIOS_BIN", "/ai/bin/aios"))
    if not model_url or not model:
        print("AIOS_MODEL_URL and AIOS_MODEL are required", file=sys.stderr)
        return 2
    if not aios.is_file():
        print(f"AI OS executable not found: {aios}", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    name = "build-eval-" + run_id
    app = root / "apps" / name
    entry = root / "bin" / name
    source = app / "src" / "main.c"
    test = app / "tests" / "run.sh"
    manifest_path = app / "manifest.json"
    goal = f'''Build one tiny C app named {name} entirely inside /ai using fs_write and shell tools. Use one tool action per turn and inspect each result.
Write /ai/apps/{name}/src/main.c with this exact content:
#include <stdio.h>

int main(void) {{
    puts("SELF_BUILD_OK");
    return 0;
}}
Write /ai/apps/{name}/tests/run.sh with this exact content:
#!/bin/sh
set -eu
actual=$(/ai/bin/{name})
[ "$actual" = "SELF_BUILD_OK" ]
echo SELF_BUILD_PASS
Write /ai/apps/{name}/manifest.json as valid JSON with exactly these fields: name {name}, version 0.1.0, entry /ai/bin/{name}, tests /ai/apps/{name}/tests/run.sh.
Compile the C source with gcc -Wall -Wextra -Werror to /ai/bin/{name}. Set the shell workdir to /ai/apps/{name} (the shell tool requires an allowed workspace subdirectory). Run the acceptance script with /bin/sh and inspect the result. Do not register or install the app, do not call ask_human, do not use network, and do not modify any other app or system path. Finish after the acceptance script passes.'''

    sessions_dir = root / "state" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    before = set(sessions_dir.glob("*.jsonl"))
    env = {**os.environ, "AIOS_ROOT": str(root), "AIOS_MODEL_URL": model_url, "AIOS_MODEL": model}
    started = time.monotonic()
    output = ""
    returncode = 124
    try:
        proc = subprocess.run(
            [str(aios), "run", "--max-tools", "24", "--max-seconds", "420", goal],
            text=True,
            capture_output=True,
            timeout=450,
            env=env,
        )
        output = proc.stdout
        if proc.stderr:
            output += "\n[stderr]\n" + proc.stderr
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
    events = []
    if session_path:
        try:
            events = [json.loads(line) for line in session_path.read_text().splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError):
            events = []

    expected = {
        "name": name,
        "version": "0.1.0",
        "entry": f"/ai/bin/{name}",
        "tests": f"/ai/apps/{name}/tests/run.sh",
    }
    expected_source = (
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        '    puts("SELF_BUILD_OK");\n'
        "    return 0;\n"
        "}"
    )
    expected_test = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"actual=$(/ai/bin/{name})\n"
        '[ "$actual" = "SELF_BUILD_OK" ]\n'
        "echo SELF_BUILD_PASS"
    )
    checks: dict[str, bool] = {
        "session_returned_zero": returncode == 0,
        "session_log_found": session_path is not None,
        "source_created": source.is_file(),
        "test_created": test.is_file(),
        "manifest_created": manifest_path.is_file(),
        "binary_created": entry.is_file(),
        "model_did_not_request_install": not any(
            event.get("ev") == "tool_call" and event.get("tool") in {"registry", "ask_human"}
            for event in events
        ),
    }
    checks["source_matches_safe_template"] = source.is_file() and source.read_text() == expected_source
    checks["test_matches_safe_template"] = test.is_file() and test.read_text() == expected_test
    if manifest_path.is_file():
        try:
            checks["manifest_matches"] = json.loads(manifest_path.read_text()) == expected
        except (OSError, json.JSONDecodeError):
            checks["manifest_matches"] = False
    else:
        checks["manifest_matches"] = False

    writes = {
        event.get("args", {}).get("path")
        for event in events
        if event.get("ev") == "tool_call" and event.get("tool") == "fs_write"
        and isinstance(event.get("args"), dict)
    }
    checks["model_wrote_all_three_files"] = all(
        str(path) in writes for path in (source, test, manifest_path)
    )
    shell_commands = [
        event.get("args", {}).get("cmd")
        for event in events
        if event.get("ev") == "tool_call" and event.get("tool") == "shell"
        and isinstance(event.get("args"), dict)
    ]
    checks["model_called_compiler"] = any(isinstance(cmd, str) and "gcc" in cmd and name in cmd for cmd in shell_commands)
    checks["model_ran_acceptance"] = any(isinstance(cmd, str) and str(test) in cmd for cmd in shell_commands)

    safe_artifacts = (
        checks["source_matches_safe_template"]
        and checks["test_matches_safe_template"]
        and checks["manifest_matches"]
    )
    try:
        binary_header = entry.read_bytes()[:4] if entry.is_file() and not entry.is_symlink() else b""
    except OSError:
        binary_header = b""
    checks["binary_is_guest_elf"] = binary_header == b"\x7fELF"
    if entry.is_file() and safe_artifacts and checks["binary_is_guest_elf"]:
        try:
            binary = subprocess.run([str(entry)], capture_output=True, text=True, timeout=10, check=False)
            checks["binary_output_exact"] = binary.returncode == 0 and binary.stdout == "SELF_BUILD_OK\n"
        except (OSError, subprocess.TimeoutExpired):
            checks["binary_output_exact"] = False
    else:
        checks["binary_output_exact"] = False

    if test.is_file() and safe_artifacts and checks["binary_is_guest_elf"]:
        try:
            positive = subprocess.run(["/bin/sh", str(test)], cwd=app, capture_output=True, text=True, timeout=15, check=False)
            checks["acceptance_passes"] = positive.returncode == 0 and "SELF_BUILD_PASS" in positive.stdout
        except (OSError, subprocess.TimeoutExpired):
            positive = None
            checks["acceptance_passes"] = False
    else:
        positive = None
        checks["acceptance_passes"] = False

    checks["acceptance_rejects_bad_binary"] = False
    backup = root / "tmp" / f"{name}.original"
    original_binary_hash = None
    if entry.is_file() and not entry.is_symlink():
        try:
            original_binary_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
        except OSError:
            original_binary_hash = None
    if checks["acceptance_passes"] and entry.is_file() and safe_artifacts and checks["binary_is_guest_elf"]:
        backup.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(entry, backup)
            entry.write_text("#!/bin/sh\nprintf 'WRONG_OUTPUT\\n'\nexit 1\n")
            entry.chmod(stat.S_IMODE(backup.stat().st_mode))
            negative = subprocess.run(["/bin/sh", str(test)], cwd=app, capture_output=True, text=True, timeout=15, check=False)
            checks["acceptance_rejects_bad_binary"] = negative.returncode != 0
        except (OSError, subprocess.TimeoutExpired):
            checks["acceptance_rejects_bad_binary"] = False
        finally:
            if backup.is_file():
                shutil.copy2(backup, entry)
                backup.unlink()
    try:
        checks["binary_restored"] = (
            entry.is_file()
            and not entry.is_symlink()
            and original_binary_hash is not None
            and hashlib.sha256(entry.read_bytes()).hexdigest() == original_binary_hash
        )
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
        "pass": all(checks.values()),
    }
    eval_dir = root / "state" / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{name}.out").write_text(output)
    with (eval_dir / "live-self-build.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")

    print(output.rstrip())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
