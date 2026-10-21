#!/usr/bin/env python3
"""AI OS console: colored, streaming, with an animated companion and model picker."""
from __future__ import annotations

import curses
import json
import os
import pathlib
import re
import select
import signal
import subprocess
import sys
import textwrap
import time
from collections import deque
from typing import Any


AI_ROOT = pathlib.Path(os.environ.get("AIOS_ROOT", "/ai")).resolve()
TOOL_LABELS = {
    "shell": "Running a command",
    "fs_read": "Reading a workspace file",
    "fs_write": "Writing a workspace file",
    "proc": "Checking a process",
    "registry": "Checking or installing an app",
    "checkpoint": "Working with a checkpoint",
    "ask_human": "Waiting for your decision",
    "net": "Checking emulated network status",
}

COMMANDS = ["/build", "/chat", "/clear", "/do", "/exit", "/help", "/history", "/install", "/model", "/provider", "/providers", "/quit", "/stream", "/status", "/retry", "/run", "/ok"]
def complete_command(prefix: str) -> list[str]:
    return [c for c in COMMANDS if c.startswith(prefix)]

# Animated companion: cycles while AI OS waits on the model.
COMPANION_FRAMES = ["\u0295\u2022\u1d25\u2022\u0294", "\u0295\u00b7\u1d25\u00b7\u0294", "\u0295\u2022\u1d25\u2022\u0294", "\u0295\u1d55\u1d25\u1d55\u0294"]
SPINNER_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

# Color pair ids
C_HEADER, C_OK, C_WARN, C_USER, C_ERROR, C_AI, C_DIM = 1, 2, 3, 4, 5, 6, 7

HISTORY_MAX = 100

def history_path() -> str:
    return str(AI_ROOT / "state" / "history.json")

def load_history(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "history" in data:
                return data["history"]
    except Exception:
        pass
    return []

def save_history(path: str, history: list[str]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"history": history}, f)
    except OSError:
        pass

def history_step(history: list[str], index: int | None, direction: int) -> tuple[str, int | None]:
    if not history:
        return ("", None)
    if direction == -1:
        if index is None:
            return (history[-1], len(history) - 1)
        index = max(0, index - 1)
        return (history[index], index)
    if direction == 1:
        if index is None:
            return ("", None)
        index = index + 1
        if index >= len(history):
            return ("", None)
        return (history[index], index)
    return ("", None)

def event_message(event: dict[str, Any]) -> str:
    """Turn an audit row into safe, concise user-facing progress."""
    kind = event.get("ev")
    if kind == "session_start":
        return "AI OS started a task"
    if kind == "tool_call":
        return TOOL_LABELS.get(str(event.get("tool")), "AI OS is using a tool")
    if kind == "tool_result":
        exit_code = event.get("command_exit")
        if exit_code is not None:
            return f"Command finished (exit {exit_code})"
        return "Step finished" if event.get("exit") == 0 else "Step needs attention"
    if kind == "tool_args_normalized":
        return "Adjusted a command into the expected format"
    if kind == "verdict":
        verdict = event.get("kind", "finished")
        return f"Task {verdict}" + (f": {event['error']}" if event.get("error") else "")
    return ""


def command_for(mode: str, prompt: str) -> list[str]:
    """Construct the child command; do-mode runs remain explicitly bounded."""
    script = pathlib.Path(__file__).with_name("aios.py")
    if mode == "do":
        return [sys.executable, "-u", str(script), "run", "--max-tools", "40",
                "--max-seconds", "1500", prompt]
    return [sys.executable, "-u", str(script), "ask", prompt]


def gate_answer(key: Any) -> bytes | None:
    """Map a keypress at an approval prompt to the answer line the harness reads.

    Enter and anything other than y/yes means no, matching the [y/N] default.
    """
    if key in ("y", "Y"):
        return b"y\n"
    if key in ("n", "N", "\n", 13):
        return b"n\n"
    return None


def input_character(key: Any) -> str | None:
    return key if isinstance(key, str) and len(key) == 1 and key.isprintable() else None
def is_enter_key(key: Any) -> bool:
    return key in (curses.KEY_ENTER, 10, 13, "\n", "\r")
def is_backspace_key(key: Any) -> bool:
    return key in (curses.KEY_BACKSPACE, 127, 8, "\b", "\x7f")
def completion_status(mode: str, exit_code: int, verdict: dict[str, Any] | None,
                      actions_taken: bool) -> str:
    if exit_code == 2:
        return "Stopped at the task/time budget. Narrow the task and try again."
    if exit_code != 0:
        return f"AI OS exited with code {exit_code}. Check the model connection or the last error above."
    if mode == "chat":
        return "Answer received. Review the result above."
    if verdict and verdict.get("kind") == "partial":
        if actions_taken:
            return "AI OS used tools, but did not verify completion. Review its output and test the result."
        return "AI OS returned without taking action. Try /do with one small, concrete task."
    return "Task session ended. Review the result and verification events above."


def load_current_model() -> dict[str, Any]:
    path = AI_ROOT / "state" / "model.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}
def load_providers() -> list[dict[str, Any]]:
    path = AI_ROOT / "state" / "providers.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("providers", []) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []
def progress_status(phase: str, label: str, elapsed: int, model: str,
                    timeout: int) -> str:
    if phase == "tool":
        return f"{label}\u2026 {elapsed}s"
    return f"Waiting for {model}\u2026 {elapsed}s elapsed (request limit {timeout}s)"


class Console:
    def __init__(self, screen: Any):
        self.screen = screen
        self.mode = "chat"
        self.lines: deque[str] = deque(maxlen=800)
        self.input = ""
        self.scroll = 0
        self.last_verdict: dict[str, Any] | None = None
        self.actions_taken = False
        self.progress_phase = "model"
        self.progress_label = ""
        self.progress_since = 0.0
        self.status = "Ready. Ask a question, press F2 for Do mode, or F3 to pick a model."
        self.busy = False
        self.history: list[str] = []
        self.history_index: int | None = None
        self.last_prompt: str = ""
        self.pending_run: str | None = None
        self.pending_gate: dict[str, Any] | None = None
        
        # Persistent history
        hist = load_history(history_path())
        self.history = hist[-HISTORY_MAX:] if hist else []

        # live streaming state
        self.stream_partial = ""
        self.stream_active = False
        # current model selection
        current = load_current_model()
        self.model = current.get("model") or os.environ.get("AIOS_MODEL", "not configured")
        self.endpoint = current.get("url") or os.environ.get("AIOS_MODEL_URL", "not configured")
        self.key_file = current.get("key_file") or ""
        self.stream_enabled = True
        self.model_timeout = max(10, min(int(current.get("timeout_seconds") or os.environ.get("AIOS_MODEL_TIMEOUT", "300")), 600))
        self.colors = curses.has_colors()
        if self.colors:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(C_HEADER, curses.COLOR_CYAN, -1)
            curses.init_pair(C_OK, curses.COLOR_GREEN, -1)
            curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
            curses.init_pair(C_USER, curses.COLOR_MAGENTA, -1)
            curses.init_pair(C_ERROR, curses.COLOR_RED, -1)
            curses.init_pair(C_AI, curses.COLOR_BLUE, -1)
            curses.init_pair(C_DIM, curses.COLOR_WHITE, -1)
        self.screen.keypad(True)
        self.screen.timeout(100)

    # ---------- rendering ----------

    def add(self, text: str, color: int = 0) -> None:
        text = text.replace("\\r", " ").replace("\\x00", "")
        width = max(24, self.screen.getmaxyx()[1] - 7)
        for line in text.splitlines() or [""]:
            wrapped = textwrap.wrap(line, width=width, replace_whitespace=False,
                                    drop_whitespace=True, break_long_words=True,
                                    break_on_hyphens=False) or [""]
            for segment in wrapped:
                self.lines.append((str(color) + "\\x1f" if color else "") + segment)
        self.scroll = 0

    def companion(self) -> str:
        if not self.busy:
            return ""
        if self.progress_phase == "tool":
            return SPINNER_FRAMES[int(time.monotonic() * 10) % len(SPINNER_FRAMES)]
        return COMPANION_FRAMES[int(time.monotonic() * 2) % len(COMPANION_FRAMES)]

    def visible_rows(self, content_rows: int) -> list[str]:
        rows = list(self.lines)
        if self.stream_active and self.stream_partial:
            rows.append("6\\x1fAI OS \u258c " + self.stream_partial)
        if self.scroll:
            end = max(0, len(rows) - self.scroll)
            return rows[max(0, end - content_rows):end]
        return rows[-content_rows:]

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 10 or width < 46:
            self.screen.addnstr(0, 0, "Resize terminal to at least 46 x 10", max(width - 1, 0))
            self.screen.refresh()
            return
        dim = curses.A_DIM if self.colors else 0
        title = " AI OS CONSOLE "
        self.screen.addnstr(0, 1, title, width - 2, curses.A_BOLD | curses.color_pair(C_HEADER))
        mode_label = "CHAT" if self.mode == "chat" else "DO"
        mode_color = curses.color_pair(C_OK) if self.mode == "chat" else curses.color_pair(C_WARN)
        stream_tag = " \u00b7 stream on" if self.stream_enabled else ""
        self.screen.addnstr(1, 2, f"[{mode_label}]", 12, curses.A_BOLD | mode_color)
        self.screen.addnstr(1, 10, f"F2 mode \u00b7 F3 model \u00b7 {self.model}{stream_tag}", width - 12, dim)
        self.screen.addnstr(2, 2, self.endpoint, width - 4, dim)
        self.screen.hline(3, 1, curses.ACS_HLINE, width - 2)

        content_top, content_bottom = 4, height - 4
        content_rows = max(1, content_bottom - content_top)
        for row, value in enumerate(self.visible_rows(content_rows), content_top):
            color = 0
            if "\\x1f" in value:
                pair, value = value.split("\\x1f", 1)
                color = curses.color_pair(int(pair))
            self.screen.addnstr(row, 2, value, width - 4, color)

        self.screen.hline(height - 3, 1, curses.ACS_HLINE, width - 2)
        status = self.status
        if self.busy:
            icon = self.companion()
            status = f"{icon}  " + status
        self.screen.addnstr(height - 2, 2, status, width - 4, dim)
        prompt = ("you \u203a " if self.mode == "chat" else "you [do] \u203a ") + self.input
        self.screen.addnstr(height - 1, 2, prompt, width - 4, curses.A_BOLD | curses.color_pair(C_USER))
        self.screen.move(height - 1, min(width - 2, 2 + len(prompt)))
        self.screen.refresh()

    def help(self) -> None:
        self.add("AI OS console help", C_HEADER)
        self.add("  Type a question and Enter to chat. F2 (or /do) switches to Do mode for bounded tool work.")
        self.add("  F3 or /model \u2014 pick a provider and model. /stream \u2014 toggle streaming responses.")
        self.add("  /install NAME \u2014 install an app directly: tests run after your approval, no model involved.")
        self.add("  /clear clears the transcript; /history lists your previous commands.", C_DIM)
        self.add("  /status shows the console state; /retry re-runs your last prompt.", C_DIM)
        self.add("  /run <cmd> stages a guest shell command; /ok confirms, anything else cancels.", C_DIM)
        self.add("  F1 help \u00b7 F2 mode \u00b7 F3 model \u00b7 \u2191/\u2193 scroll \u00b7 Ctrl-C/Esc exit", C_DIM)
        self.add("  Do mode writes only inside /ai. Approvals and test results are shown here.", C_WARN)

    # ---------- model picker ----------

    def picker(self) -> None:
        providers = load_providers()
        if not providers:
            self.add("No provider registry found at /ai/state/providers.json.", C_WARN)
            return
        rows: list[tuple[str, str, str]] = []
        for provider in providers:
            if not provider.get("available", True):
                continue
            for model in provider.get("models", []):
                tag = " \u2713" if model == self.model and provider.get("url") == self.endpoint else ""
                rows.append((f"{provider['name']} \u00b7 {model}{tag}",
                             provider["url"], model))
        if not rows:
            self.add("No providers with keys are available. Run emulation/sync-keys.sh on the host.", C_WARN)
            return
        index = 0
        while True:
            self.screen.erase()
            height, width = self.screen.getmaxyx()
            self.screen.addnstr(0, 1, " Pick a provider and model ", width - 2,
                                curses.A_BOLD | curses.color_pair(C_HEADER))
            self.screen.addnstr(1, 2, "\u2191/\u2193 navigate \u00b7 Enter select \u00b7 Esc cancel", width - 4,
                                curses.A_DIM if self.colors else 0)
            for row, (label, _url, _model) in enumerate(rows[:height - 4], 2):
                attr = curses.A_REVERSE if row - 2 == index else 0
                self.screen.addnstr(row, 4, label, width - 6, attr)
            self.screen.refresh()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if key in (3, 27):
                return
            if key == curses.KEY_UP:
                index = (index - 1) % len(rows)
            elif key == curses.KEY_DOWN:
                index = (index + 1) % len(rows)
            elif is_enter_key(key):
                _label, url, model = rows[index]
                provider = next((p for p in providers if p.get("url") == url and model in p.get("models", [])), {})
                self.endpoint = url
                self.model = model
                self.key_file = provider.get("key_file") or ""
                self.save_selection()
                self.add(f"Model \u2192 {provider.get('name', url)} \u00b7 {model}", C_OK)
                return

    def save_selection(self) -> None:
        config = {"url": self.endpoint, "model": self.model,
                  "timeout_seconds": self.model_timeout}
        if self.key_file:
            config["key_file"] = self.key_file
        path = AI_ROOT / "state" / "model.json"
        try:
            path.write_text(json.dumps(config) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
        except OSError as exc:
            self.add(f"Could not save model selection: {exc}", C_ERROR)

    def child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AIOS_MODEL_URL"] = self.endpoint
        env["AIOS_MODEL"] = self.model
        env["AIOS_MODEL_TIMEOUT"] = str(self.model_timeout)
        if self.key_file:
            env["AIOS_MODEL_KEY_FILE"] = self.key_file
        elif "AIOS_MODEL_KEY_FILE" in env:
            env.pop("AIOS_MODEL_KEY_FILE")
        env["AIOS_STREAM"] = "1" if self.stream_enabled else "0"
        return env

    # ---------- task execution ----------

    def run_child(self, prompt: str, args: list[str] | None = None) -> None:
        self.last_verdict = None
        self.actions_taken = False
        self.stream_partial = ""
        self.stream_active = False
        self.pending_gate = None
        direct = args is not None
        args = args if direct else command_for(self.mode, prompt)
        sessions_dir = AI_ROOT / "state" / "sessions"
        before = set(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else set()
        try:
            child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=False, bufsize=0,
                                     env=self.child_env(), start_new_session=True)
        except OSError as exc:
            self.add(f"Could not start AI OS: {exc}", C_ERROR)
            self.status = "Close or repair the guest runtime, then try again."
            return

        self.busy = True
        self.progress_phase = "model"
        self.progress_label = ""
        self.progress_since = time.monotonic()
        stream = child.stdout
        assert stream is not None
        fd = stream.fileno()
        os.set_blocking(fd, False)
        pending = b""
        log_file: pathlib.Path | None = None
        log_offset = 0
        log_partial = b""
        announced: set[tuple[int, str]] = set()
        output_lines = 0

        def announce(event: dict[str, Any]) -> None:
            if event.get("ev") == "gate_request":
                # The harness is blocked on one answer line; the next y/n keypress goes to it.
                self.pending_gate = event
                self.add(f"\u2022 Approval needed: {event.get('question', '')} (y/N)", C_WARN)
                return
            message = event_message(event)
            if not message:
                return
            identity = (len(announced), message)
            if identity in announced:
                return
            announced.add(identity)
            kind = event.get("ev")
            if kind == "verdict" and event.get("kind") == "succeeded":
                color = C_OK
            elif kind == "verdict":
                color = C_WARN
            else:
                color = C_HEADER
            self.add("\u2022 " + message, color)
            if kind == "tool_call":
                self.actions_taken = True
                self.progress_phase = "tool"
                self.progress_label = message
                self.progress_since = time.monotonic()
                self.status = message + "\u2026"
            elif kind == "tool_result":
                self.progress_phase = "model"
                self.progress_label = ""
                self.progress_since = time.monotonic()
                self.status = "Step complete. AI OS is continuing\u2026"
            if kind == "verdict":
                self.last_verdict = event

        def consume_child_output(final: bool = False) -> None:
            nonlocal pending, output_lines
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                text = raw.decode(errors="replace").strip()
                if text:
                    self.add("AI OS \u203a " + text, C_AI)
                    output_lines += 1
                    self.stream_partial = ""
                    self.stream_active = False
            if pending:
                text = pending.decode(errors="replace")
                if final:
                    if text.strip():
                        self.add("AI OS \u203a " + text.strip(), C_AI)
                        output_lines += 1
                    pending = b""
                    self.stream_partial = ""
                    self.stream_active = False
                else:
                    # Live streaming: show the partial line as it grows.
                    if text and not text.startswith("AI OS \u203a "):
                        self.stream_partial = text
                        self.stream_active = True

        while child.poll() is None:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(fd, 8192)
                except BlockingIOError:
                    chunk = b""
                if chunk:
                    pending += chunk
                    consume_child_output()

            if log_file is None and sessions_dir.exists():
                created = [p for p in sessions_dir.glob("*.jsonl") if p not in before]
                if created:
                    log_file = max(created, key=lambda p: p.stat().st_mtime_ns)
            if log_file is not None:
                try:
                    with log_file.open("rb") as log:
                        log.seek(log_offset)
                        data = log.read()
                        log_offset = log.tell()
                    log_partial += data
                    while b"\n" in log_partial:
                        raw, log_partial = log_partial.split(b"\n", 1)
                        try:
                            announce(json.loads(raw))
                        except (ValueError, UnicodeDecodeError):
                            continue
                except OSError:
                    pass

            elapsed = int(time.monotonic() - self.progress_since)
            self.status = progress_status(self.progress_phase, self.progress_label,
                                          elapsed, self.model, self.model_timeout)
            if self.pending_gate is not None:
                self.status = "Approval needed: press y to approve, n or Enter to decline."
            self.draw()
            try:
                key = self.screen.get_wch()
            except curses.error:
                key = -1
            if self.pending_gate is not None and (answer := gate_answer(key)) is not None:
                try:
                    assert child.stdin is not None
                    child.stdin.write(answer)
                    child.stdin.flush()
                    self.add("\u2022 Answered " + ("yes" if answer == b"y\n" else "no"), C_OK if answer == b"y\n" else C_WARN)
                except (BrokenPipeError, OSError, ValueError):
                    self.add("Could not send the answer; the task has already stopped.", C_ERROR)
                self.pending_gate = None
                continue
            if key in (3, 27):
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                self.status = "Stopping AI OS\u2026"
                break
            if key == curses.KEY_UP:
                self.scroll = min(self.scroll + 1, len(self.lines))
            elif key == curses.KEY_DOWN:
                self.scroll = max(0, self.scroll - 1)
            elif key == curses.KEY_PPAGE:
                self.scroll = min(self.scroll + 10, len(self.lines))
            elif key == curses.KEY_NPAGE:
                self.scroll = max(0, self.scroll - 10)

        self.pending_gate = None
        if child.stdin is not None:
            try:
                child.stdin.close()
            except OSError:
                pass
        try:
            remainder = stream.read() or b""
        except (OSError, ValueError):
            remainder = b""
        pending += remainder
        consume_child_output(final=True)

        if log_file is not None:
            try:
                with log_file.open("rb") as log:
                    log.seek(log_offset)
                    log_partial += log.read()
                for raw in log_partial.splitlines():
                    try:
                        announce(json.loads(raw))
                    except (ValueError, UnicodeDecodeError):
                        continue
            except OSError:
                pass
        elif sessions_dir.exists():
            created = [p for p in sessions_dir.glob("*.jsonl") if p not in before]
            if created:
                newest = max(created, key=lambda p: p.stat().st_mtime_ns)
                try:
                    for raw in newest.read_bytes().splitlines():
                        try:
                            announce(json.loads(raw))
                        except (ValueError, UnicodeDecodeError):
                            continue
                except OSError:
                    pass

        if child.poll() is None:
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        code = child.returncode
        if direct:
            self.status = ("Install finished. See the result above." if code == 0
                           else "Install did not complete. See the reason above.")
        else:
            self.status = completion_status(self.mode, code, self.last_verdict, self.actions_taken)
        if not output_lines and code not in (0, 2):
            self.add("No assistant response was returned. Check the model with F3 and try again.", C_ERROR)
        self.busy = False

    # ---------- input handling ----------

    def submit(self) -> bool:
        if self.pending_run is not None:
            # Implicit cancel if any other command is entered
            # But we must check if the command is /ok first.
            # The design says: "any OTHER command or input while self.pending_run is not None must first set self.pending_run = None"
            # This means if it's NOT /ok, we cancel.
            pass

        self.history_index = None
        prompt = self.input.strip()
        if prompt and (not self.history or self.history[-1] != prompt):
            self.history.append(prompt)
            if len(self.history) > HISTORY_MAX:
                self.history = self.history[-HISTORY_MAX:]
            save_history(history_path(), self.history)
        self.input = ""
        if not prompt:
            return True
        command, _, remainder = prompt.partition(" ")
        lowered = command.lower()

        # Handle /ok first to avoid implicit cancel
        if lowered == "/ok":
            if self.pending_run is None:
                self.add("Nothing pending. Use /run <command> first.", 3)
                return True
            cmd = self.pending_run
            self.pending_run = None
            try:
                proc = subprocess.run(["/bin/sh", "-c", cmd], cwd=str(AI_ROOT), text=True, capture_output=True, timeout=30)
                self.add(f"exit {proc.returncode}", 2 if proc.returncode == 0 else 5)
                if proc.stdout:
                    out = proc.stdout[:1500]
                    if len(proc.stdout) > 1500:
                        out += "\n..."
                    self.add(out, 6)
                if proc.stderr:
                    err = proc.stderr[:1500]
                    if len(proc.stderr) > 1500:
                        err += "\n..."
                    self.add(err, 5)
            except subprocess.TimeoutExpired:
                self.add("Timed out after 30s.", 5)
            except OSError as exc:
                self.add(str(exc), 5)
            return True

        # Now handle implicit cancel for any other input
        if self.pending_run is not None:
            self.pending_run = None

        if lowered in {"/quit", "/exit"}:
            return False
        if lowered in {"/help", "/?"}:
            self.help()
            return True
        if lowered == "/clear":
            self.lines = deque(maxlen=self.lines.maxlen)
            self.scroll = 0
            self.add("Transcript cleared.", 7)
            return True
        if lowered == "/history":
            if not self.history:
                self.add("No commands yet.", 3)
            else:
                for entry in self.history:
                    self.add("  " + entry, 7)
            return True
        if lowered == "/status":
            self.add(f"mode: {self.mode}", 7)
            self.add(f"model: {self.model}  stream: {'on' if self.stream_enabled else 'off'}", 7)
            self.add(f"history: {len(self.history)} entries  transcript: {len(self.lines)} lines", 7)
            return True
        if lowered == "/retry":
            if self.last_prompt:
                prompt = self.last_prompt
            else:
                self.add("Nothing to retry yet.", 3)
                return True
        if lowered == "/chat":
            self.mode = "chat"
            self.status = "Chat mode: ask questions without allowing tool actions."
            return True
        if lowered in {"/do", "/build"}:
            self.mode = "do"
            if remainder.strip():
                prompt = remainder.strip()
            else:
                self.status = "Do mode is on. Describe a task and press Enter."
                return True
        if lowered in {"/model", "/provider"}:
            self.picker()
            return True
        if lowered == "/stream":
            self.stream_enabled = not self.stream_enabled
            self.add(f"Streaming {'enabled' if self.stream_enabled else 'disabled'}.", C_OK)
            return True
        if lowered == "/providers":
            for provider in load_providers():
                state = "available" if provider.get("available", True) else "no key"
                self.add(f"  {provider['name']} ({provider['url']}) \u2014 {state}", C_DIM)
            return True
        if lowered == "/run":
            if not remainder:
                self.add("Usage: /run <shell command> then Enter on /ok to confirm.", 3)
                return True
            self.pending_run = remainder
            self.add("Run: " + remainder, 3)
            self.add("Press Enter on /ok to execute, anything else cancels.", 7)
            return True
        
        if lowered == "/install":
            name = remainder.strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                self.add("Usage: /install NAME (an app in /ai/apps with a passing test).", C_WARN)
                return True
            self.add("Install " + name + ": the acceptance tests run after you approve.", C_HEADER)
            self.run_child(prompt, [sys.executable, "-u", str(pathlib.Path(__file__).with_name("aios.py")), "registry", "install", name])
            return True

        self.last_prompt = prompt
        self.add(("you \u203a " if self.mode == "chat" else "you [do] \u203a ") + prompt, C_USER)
        self.run_child(prompt)
        return True

    def main(self) -> None:
        self.add("Welcome to the AI OS console.", C_OK)
        self.add("Chat freely, press F2 for Do mode, F3 to switch models. /help shows everything.", C_DIM)
        while True:
            self.draw()
            try:
                key = self.screen.get_wch()
            except curses.error:
                key = -1
            if key in (3, 27):
                break
            if key == curses.KEY_F1:
                self.help()
            elif key == curses.KEY_F2:
                self.mode = "do" if self.mode == "chat" else "chat"
                self.status = ("Do mode: tasks can use the bounded AI OS tools." if self.mode == "do"
                               else "Chat mode: ask questions without allowing tool actions.")
            elif key == curses.KEY_F3:
                self.picker()
            elif key == curses.KEY_UP:
                if self.input == "" or self.history_index is not None:
                    self.input, self.history_index = history_step(self.history, self.history_index, -1)
                else:
                    self.scroll = min(self.scroll + 1, len(self.lines))
            elif key == curses.KEY_DOWN:
                if self.history_index is not None:
                    self.input, self.history_index = history_step(self.history, self.history_index, 1)
                else:
                    self.scroll = max(0, self.scroll - 1)
            elif key == curses.KEY_PPAGE:
                self.scroll = min(self.scroll + 10, len(self.lines))
            elif key == curses.KEY_NPAGE:
                self.scroll = max(0, self.scroll - 10)
            elif key == "\t" and self.input.startswith("/"):
                matches = complete_command(self.input)
                if len(matches) == 1:
                    self.input = matches[0] + " "
                    self.history_index = None
                elif len(matches) > 1:
                    self.add("  " + "   ".join(matches), 7)
            elif is_backspace_key(key):
                self.history_index = None
                self.input = self.input[:-1]
            elif is_enter_key(key):
                if not self.submit():
                    break
            else:
                character = input_character(key)
                if character:
                    self.history_index = None
                    self.input += character


def main() -> int:
    try:
        curses.wrapper(lambda screen: Console(screen).main())
        return 0
    except curses.error as exc:
        print(f"AI OS TUI needs an interactive terminal ({exc}). Run: aios tui", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
