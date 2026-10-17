#!/usr/bin/env python3
"""Small, beginner-facing full-screen terminal client for AI OS."""
from __future__ import annotations

import curses
import json
import os
import pathlib
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
        return [sys.executable, "-u", str(script), "run", "--max-tools", "32",
                "--max-seconds", "900", prompt]
    return [sys.executable, "-u", str(script), "ask", prompt]


def input_character(key: Any) -> str | None:
    """Normalize curses text input while keeping special key codes separate."""
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


def progress_status(phase: str, label: str, elapsed: int, model: str,
                    timeout: int) -> str:
    if phase == "tool":
        return f"{label}… {elapsed}s"
    return f"Waiting for {model}… {elapsed}s elapsed (request limit {timeout}s)"


class Console:
    def __init__(self, screen: Any):
        self.screen = screen
        self.mode = "chat"
        self.lines: deque[str] = deque(maxlen=500)
        self.input = ""
        self.scroll = 0
        self.last_verdict: dict[str, Any] | None = None
        self.actions_taken = False
        self.progress_phase = "model"
        self.progress_label = ""
        self.progress_since = 0.0
        self.status = "Ready. Ask a question, or press F2 to switch to Do mode."
        self.busy = False
        self.model = os.environ.get("AIOS_MODEL", "not configured")
        self.endpoint = os.environ.get("AIOS_MODEL_URL", "not configured")
        self.model_timeout = max(10, min(int(os.environ.get("AIOS_MODEL_TIMEOUT", "300")), 600))
        self.colors = curses.has_colors()
        if self.colors:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        self.screen.keypad(True)
        self.screen.timeout(100)

    def add(self, text: str, color: int = 0) -> None:
        text = text.replace("\r", " ").replace("\x00", "")
        width = max(24, self.screen.getmaxyx()[1] - 7)
        for line in text.splitlines() or [""]:
            wrapped = textwrap.wrap(line, width=width, replace_whitespace=False,
                                    drop_whitespace=True, break_long_words=True,
                                    break_on_hyphens=False) or [""]
            for segment in wrapped:
                self.lines.append((str(color) + "\x1f" if color else "") + segment)
        self.scroll = 0

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 10 or width < 46:
            self.screen.addnstr(0, 0, "Resize terminal to at least 46 x 10", max(width - 1, 0))
            self.screen.refresh()
            return
        title = " AI OS  /  INTERACTIVE CONSOLE "
        self.screen.addnstr(0, 1, title, width - 2, curses.A_BOLD | (curses.color_pair(1) if self.colors else 0))
        mode_label = "CHAT · F2 switches to DO" if self.mode == "chat" else "DO · F2 switches to CHAT"
        model_line = f"{mode_label}    model: {self.model}"
        self.screen.addnstr(1, 2, model_line, width - 4, curses.A_DIM)
        endpoint_line = f"endpoint: {self.endpoint}"
        self.screen.addnstr(2, 2, endpoint_line, width - 4, curses.A_DIM)
        self.screen.hline(3, 1, curses.ACS_HLINE, width - 2)

        content_top, content_bottom = 4, height - 4
        content_rows = max(1, content_bottom - content_top)
        visible = list(self.lines)
        if self.scroll:
            end = max(0, len(visible) - self.scroll)
            visible = visible[max(0, end - content_rows):end]
        else:
            visible = visible[-content_rows:]
        for row, value in enumerate(visible, content_top):
            color = 0
            if "\x1f" in value:
                pair, value = value.split("\x1f", 1)
                color = curses.color_pair(int(pair)) if self.colors else 0
            self.screen.addnstr(row, 2, value, width - 4, color)

        self.screen.hline(height - 3, 1, curses.ACS_HLINE, width - 2)
        status = self.status
        self.screen.addnstr(height - 2, 2, status, width - 4, curses.A_DIM)
        prompt = "you › " + self.input
        self.screen.addnstr(height - 1, 2, prompt, width - 4, curses.A_BOLD)
        self.screen.move(height - 1, min(width - 2, 2 + len(prompt)))
        self.screen.refresh()

    def help(self) -> None:
        self.add("Help: type a question and press Enter in Chat mode. Switch to Do mode with F2, then describe a task AI OS should build or change.", 1)
        self.add("F1 help · F2 switch mode · ↑/↓ scroll · Ctrl-C or /quit exit", 1)
        self.add("Do mode can write only within its approved /ai workspace. Review approvals and test results before accepting changes.", 3)

    def run_child(self, prompt: str) -> None:
        self.last_verdict = None
        self.actions_taken = False
        args = command_for(self.mode, prompt)
        sessions_dir = AI_ROOT / "state" / "sessions"
        before = set(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else set()
        try:
            child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=False, bufsize=0,
                                     start_new_session=True)
        except OSError as exc:
            self.add(f"Could not start AI OS: {exc}", 3)
            self.status = "Close or repair the guest runtime, then try again."
            return

        self.busy = True
        started = time.monotonic()
        self.progress_phase = "model"
        self.progress_label = ""
        self.progress_since = started
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
        while child.poll() is None:
            ready, _, _ = select.select([fd], [], [], 0.15)
            if ready:
                try:
                    chunk = os.read(fd, 8192)
                except BlockingIOError:
                    chunk = b""
                if chunk:
                    pending += chunk
                    while b"\n" in pending:
                        raw, pending = pending.split(b"\n", 1)
                        text = raw.decode(errors="replace").strip()
                        if text:
                            self.add("AI OS › " + text)
                            output_lines += 1

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
                            event = json.loads(raw)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        message = event_message(event)
                        identity = (len(announced), message)
                        if message and identity not in announced:
                            announced.add(identity)
                            color = 2 if event.get("ev") == "verdict" and event.get("kind") == "succeeded" else 3 if event.get("ev") == "verdict" and event.get("kind") in {"failed", "partial"} else 1
                            self.add("• " + message, color)
                            if event.get("ev") == "tool_call":
                                self.actions_taken = True
                                self.progress_phase = "tool"
                                self.progress_label = message
                                self.progress_since = time.monotonic()
                            elif event.get("ev") == "tool_result":
                                self.progress_phase = "model"
                                self.progress_label = ""
                                self.progress_since = time.monotonic()
                            if event.get("ev") == "verdict":
                                self.last_verdict = event
                            if event.get("ev") == "tool_call":
                                self.status = message + "…"
                            elif event.get("ev") == "tool_result":
                                self.status = "Step complete. AI OS is continuing…"
                except OSError:
                    pass

            elapsed = int(time.monotonic() - self.progress_since)
            self.status = progress_status(self.progress_phase, self.progress_label,
                                          elapsed, self.model, self.model_timeout)
            self.draw()
            try:
                key = self.screen.get_wch()
            except curses.error:
                key = -1
            if key in (3, 27):
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                self.status = "Stopping AI OS…"
                break
            if key == curses.KEY_UP:
                self.scroll = min(self.scroll + 1, len(self.lines))
            elif key == curses.KEY_DOWN:
                self.scroll = max(0, self.scroll - 1)

        # Fast model responses can finish before the polling loop sees their log.
        if sessions_dir.exists():
            if log_file is None:
                created = [p for p in sessions_dir.glob("*.jsonl") if p not in before]
                if created:
                    log_file = max(created, key=lambda p: p.stat().st_mtime_ns)
            if log_file is not None:
                try:
                    with log_file.open("rb") as log:
                        log.seek(log_offset)
                        log_partial += log.read()
                    for raw in log_partial.splitlines():
                        try:
                            event = json.loads(raw)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        message = event_message(event)
                        if message:
                            color = 2 if event.get("ev") == "verdict" and event.get("kind") == "succeeded" else 3 if event.get("ev") == "verdict" and event.get("kind") in {"failed", "partial"} else 1
                            self.add("• " + message, color)
                        if event.get("ev") == "tool_call":
                            self.actions_taken = True
                            self.progress_phase = "tool"
                            self.progress_label = message
                            self.progress_since = time.monotonic()
                        elif event.get("ev") == "tool_result":
                            self.progress_phase = "model"
                            self.progress_label = ""
                            self.progress_since = time.monotonic()
                        if event.get("ev") == "verdict":
                            self.last_verdict = event
                except OSError:
                    pass

        try:
            remainder = stream.read() or b""
        except (OSError, ValueError):
            remainder = b""
        if remainder:
            pending += remainder
        if pending.strip():
            self.add("AI OS › " + pending.decode(errors="replace").strip())
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
        self.status = completion_status(self.mode, code, self.last_verdict, self.actions_taken)
        if not output_lines and code not in (0, 2):
            self.add("No assistant response was returned. Check that the model URL and model name shown above are correct.", 3)
        self.busy = False

    def submit(self) -> bool:
        prompt = self.input.strip()
        self.input = ""
        if not prompt:
            return True
        command, _, remainder = prompt.partition(" ")
        if command.lower() in {"/quit", "/exit"}:
            return False
        if command.lower() in {"/help", "/?"}:
            self.help()
            return True
        if command.lower() == "/chat":
            self.mode = "chat"
            self.status = "Chat mode: ask questions without allowing tool actions."
            return True
        if command.lower() in {"/do", "/build"}:
            if remainder.strip():
                self.mode = "do"
                prompt = remainder.strip()
            else:
                self.mode = "do"
                self.status = "Do mode is on. Describe a task and press Enter."
                return True
        self.add(("you › " if self.mode == "chat" else "you [do] › ") + prompt, 4)
        self.run_child(prompt)
        return True

    def main(self) -> None:
        self.add("Welcome. Ask a question in Chat mode, or press F2 and describe what you want AI OS to do.", 2)
        self.add("AI OS work is bounded to /ai. It shows approvals and verification results here.", 1)
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
                self.status = "Do mode: tasks can use the bounded AI OS tools." if self.mode == "do" else "Chat mode: ask questions without allowing tool actions."
            elif key == curses.KEY_UP:
                self.scroll = min(self.scroll + 1, len(self.lines))
            elif key == curses.KEY_DOWN:
                self.scroll = max(0, self.scroll - 1)
            elif is_backspace_key(key):
                self.input = self.input[:-1]
            elif is_enter_key(key):
                if not self.submit():
                    break
            else:
                character = input_character(key)
                if character:
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
