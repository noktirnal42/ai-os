#!/usr/bin/env python3
"""wbrowse — AI OS text browser (doc 07 §9, F4-2).

Pipeline: libhttp fetch -> minimal HTML parser (tags -> text blocks, <a href>,
<pre> passthrough, scripts/styles ignored) -> line-wrapped render with numbered
links [N] -> curses viewer. Keys: j/k scroll, Enter open link under cursor,
Tab next link, b back, q quit, :open URL.

Non-interactive modes for scripts/tests/acceptance:
  wbrowse --dump URL            render page to stdout
  wbrowse --html-file F [--base URL] [--width N]   render a local fixture
"""
from __future__ import annotations

import curses
import os
import re
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser

DEFAULT_WIDTH = 80
FETCH_TIMEOUT = 30
HISTORY_LIMIT = 50
PAGE_CACHE_LIMIT = 30

HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
BLOCK_KINDS = set(HEADING_PREFIX) | {"p", "li", "pre"}


class FetchError(RuntimeError):
    pass


def libhttp_path() -> str:
    return os.environ.get("AIOS_LIBHTTP", "/ai/bin/libhttp")


def normalize_url(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    return url


def fetch(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[int, str]:
    """GET via the libhttp CLI: returns (final_status, body). Redirects are
    followed inside libhttp (up to 5 hops)."""
    url = normalize_url(url)
    try:
        proc = subprocess.run([libhttp_path(), url], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise FetchError(f"libhttp not found at {libhttp_path()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError(f"fetch timed out after {timeout}s: {url}") from exc
    if proc.returncode != 0:
        raise FetchError(f"fetch failed (exit {proc.returncode}): {url}")
    out = proc.stdout
    nl = out.find("\n")
    if nl < 0:
        raise FetchError(f"malformed libhttp output for {url}")
    try:
        status = int(out[:nl].strip())
    except ValueError as exc:
        raise FetchError(f"malformed status from libhttp for {url}") from exc
    return status, out[nl + 1:]


class _Parser(HTMLParser):
    """Minimal HTML -> blocks + numbered links. Inline tags flatten into the
    surrounding text; script/style contents are dropped; <pre> is verbatim."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.links: list[dict] = []
        self.title = ""
        self._skip = 0          # inside <script>/<style>
        self._in_title = False
        self._kind: str | None = None   # open block kind (p/hN/li/pre)
        self._segments: list[tuple] = []  # ("t", text) | ("link", num, href, text)
        self._pre_lines: list[str] = []
        self._pre_buf: list[str] = []
        self._anchor: dict | None = None  # {"href":..., "text":...} while <a> open

    # -- block plumbing ----------------------------------------------------
    def _flush(self) -> None:
        """Close the currently open block (or loose inline text)."""
        if self._kind == "pre":
            raw = "".join(self._pre_buf)
            self.blocks.append({"kind": "pre", "lines": raw.split("\n")})
            self._pre_buf = []
        elif self._segments:
            self.blocks.append({"kind": self._kind or "text", "segments": self._segments})
            self._segments = []
        self._kind = None

    def _close_anchor(self) -> None:
        if self._anchor is None:
            return
        num = len(self.links) + 1
        self.links.append({"num": num, "href": self._anchor["href"], "text": " ".join(self._anchor["text"].split())})
        self._segments.append(("link", num, self._anchor["href"], self.links[-1]["text"]))
        self._anchor = None

    # -- HTMLParser callbacks ----------------------------------------------
    def handle_starttag(self, tag, attrs) -> None:
        if self._skip:
            if tag in ("script", "style"):
                self._skip += 1
            return
        if tag in ("script", "style"):
            self._flush()
            self._skip = 1
            return
        if tag == "title":
            self._flush()
            self._in_title = True
            return
        if tag == "br":
            self._close_anchor()
            if self._kind == "pre":
                self._pre_buf.append("\n")
            else:
                self._flush()
            return
        if tag == "hr":
            self._close_anchor()
            self._flush()
            self.blocks.append({"kind": "rule"})
            return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href and self._anchor is None:  # nested <a> flows into the outer one
                self._anchor = {"href": href.strip(), "text": ""}
            return
        if tag in BLOCK_KINDS:
            self._close_anchor()
            self._flush()
            self._kind = tag
            return
        # inline or container tags (b, i, span, div, ul, ...) change nothing here

    def handle_endtag(self, tag) -> None:
        if self._skip:
            if tag in ("script", "style"):
                self._skip -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag == "a":
            self._close_anchor()
            return
        if tag in BLOCK_KINDS and self._kind == tag:
            self._close_anchor()
            self._flush()
        elif tag in ("p", "li") or tag in HEADING_PREFIX:
            # implied end (e.g. <p> closed by a sibling block): already flushed
            pass

    def handle_data(self, data) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        if self._kind == "pre":
            self._pre_buf.append(data)
            return
        if self._anchor is not None:
            self._anchor["text"] += data
            return
        if not data:
            return
        if not self._kind and data.isspace() and not self._segments:
            return  # stray whitespace between blocks
        collapsed = " ".join(data.split())
        if not collapsed and data.isspace():
            collapsed = " "
        if self._segments and self._segments[-1][0] == "t":
            prev = self._segments[-1][1]
            self._segments[-1] = ("t", prev + " " + collapsed)
        else:
            if collapsed.strip() or self._kind:
                self._segments.append(("t", collapsed))

    def close(self) -> None:
        super().close()
        self._close_anchor()
        self._flush()


def parse_html(html: str) -> dict:
    parser = _Parser()
    parser.feed(html)
    parser.close()
    return {"title": " ".join(parser.title.split()), "blocks": parser.blocks, "links": parser.links}


def _wrap(tokens: list[tuple[str, int | None]], width: int, prefix: str, indent: int) -> list[tuple[str, list[tuple[int, int, int]]]]:
    """tokens: (word, link_num_or_None). Returns [(line, [(num, col_start, col_end_inclusive)])]."""
    out: list[tuple[str, list[tuple[int, int, int]]]] = []
    line = prefix
    marks: list[tuple[int, int, int]] = []
    for word, num in tokens:
        if line.strip() and len(line) + 1 + len(word) > width:
            out.append((line, marks))
            line = " " * indent
            marks = []
        if line and not line.endswith(" "):
            line += " "
        start = len(line)
        line += word
        if num is not None:
            marks.append((num, start, len(line) - 1))
    if line.strip() or not out:
        out.append((line, marks))
    return out


def render_page(parsed: dict, width: int = DEFAULT_WIDTH) -> dict:
    """Render parsed blocks to screen lines + per-line link marker spans."""
    lines: list[str] = []
    spans: list[list[tuple[int, int, int]]] = []

    def blank() -> None:
        if lines:
            lines.append("")
            spans.append([])

    for block in parsed["blocks"]:
        kind = block["kind"]
        if kind == "rule":
            blank()
            lines.append("-" * min(width, 40))
            spans.append([])
            blank()
            continue
        blank()
        if kind == "pre":
            for raw in block["lines"]:
                lines.append(raw.rstrip("\r"))
                spans.append([])
            continue
        if kind == "li":
            prefix, indent = "- ", 2
        else:
            prefix = HEADING_PREFIX.get(kind, "")
            indent = len(prefix) if kind in HEADING_PREFIX else 0
        tokens: list[tuple[str, int | None]] = []
        for segment in block["segments"]:
            if segment[0] == "t":
                for word in segment[1].split():
                    tokens.append((word, None))
            else:
                _, num, _href, text = segment
                for word in text.split():
                    tokens.append((word, None))
                tokens.append((f"[{num}]", num))
        for line, marks in _wrap(tokens, width, prefix, indent):
            lines.append(line)
            spans.append(marks)
    return {"lines": lines, "spans": spans, "links": {l["num"]: l["href"] for l in parsed["links"]}, "title": parsed["title"]}


def load_page(url: str, cache: dict | None = None, timeout: int = FETCH_TIMEOUT) -> dict:
    """Fetch + parse + render one page. HTTP error statuses render an error page."""
    url = normalize_url(url)
    parsed_html: dict
    status = 0
    if cache is not None and url in cache:
        status, html = cache[url]
        parsed_html = parse_html(html)
    else:
        try:
            status, html = fetch(url, timeout=timeout)
        except FetchError as exc:
            status = 0
            html = f"<h1>Could not load page</h1><p>{exc}</p>"
        parsed_html = parse_html(html)
        if cache is not None and status != 0:
            if len(cache) >= PAGE_CACHE_LIMIT:
                cache.pop(next(iter(cache)))
            cache[url] = (status, html)
    if 400 <= status:
        title = " ".join(parse_html(html).get("title", "").split()) if status else ""
        parsed_html = parse_html(f"<h1>HTTP {status}</h1><p>Request failed for {url}</p>")
        if title:
            parsed_html["title"] = title
    return {"url": url, "status": status, **render_page(parsed_html)}


def resolve_link(page: dict, num: int) -> str:
    href = page["links"].get(num, "")
    return urllib.parse.urljoin(page["url"], href) if href else ""


class Browser:
    """History stack shared by the TUI and tests: go() pushes, back() pops."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.pos = -1
        self.cache: dict[str, tuple[int, str]] = {}

    def go(self, url: str) -> dict:
        url = normalize_url(url)
        self.stack = self.stack[: self.pos + 1]
        self.stack.append(url)
        if len(self.stack) > HISTORY_LIMIT:
            self.stack = self.stack[-HISTORY_LIMIT:]
        self.pos = len(self.stack) - 1
        return self.current()

    def back(self) -> dict | None:
        if self.pos <= 0:
            return None
        self.pos -= 1
        return self.current()

    def current(self) -> dict:
        return load_page(self.stack[self.pos], cache=self.cache)

    def open_link(self, page: dict, num: int) -> dict:
        target = resolve_link(page, num)
        if not target:
            raise ValueError(f"no link number {num} on this page")
        self.go(target)
        return self.current()


# ---------------------------------------------------------------------------
# non-interactive dump

def dump_html_file(path: str, base: str = "", width: int = DEFAULT_WIDTH) -> dict:
    html = open(path, encoding="utf-8", errors="replace").read()
    parsed = parse_html(html)
    return {"url": base or f"file://{path}", "status": 200, **render_page(parsed, width)}


def dump_html_file(path: str, base: str = "", width: int = DEFAULT_WIDTH) -> dict:
    html = open(path, encoding="utf-8", errors="replace").read()
    parsed = parse_html(html)
    return {"url": base or f"file://{path}", "status": 200, **render_page(parsed, width)}


def print_page(page: dict) -> None:
    for line in page["lines"]:
        print(line)


# ---------------------------------------------------------------------------
# curses viewer

KEY_HINT = "j/k scroll · Enter open link · Tab next link · b back · q quit · :open URL"


class Viewer:
    def __init__(self, browser: Browser, start_url: str) -> None:
        self.browser = browser
        self.page = self.browser.go(start_url)
        self.scroll = 0
        self.cursor_line = self._first_link_line()
        self.cursor_mark = 0

    # cursor helpers ---------------------------------------------------------
    def _first_link_line(self) -> int:
        for i, marks in enumerate(self.page["spans"]):
            if marks:
                return i
        return 0

    def _flat_links(self) -> list[tuple[int, int]]:
        flat = []
        for i, marks in enumerate(self.page["spans"]):
            for j, mark in enumerate(marks):
                flat.append((i, j))
        return flat

    def move(self, delta: int) -> None:
        target = self.cursor_line + delta
        if 0 <= target < len(self.page["lines"]):
            self.cursor_line = target
            self.cursor_mark = 0 if self.page["spans"][target] else -1

    def next_link(self) -> None:
        flat = self._flat_links()
        if not flat:
            return
        current = (self.cursor_line, self.cursor_mark)
        try:
            idx = flat.index(current)
            nxt = flat[(idx + 1) % len(flat)]
        except ValueError:
            nxt = flat[0]
        self.cursor_line, self.cursor_mark = nxt

    def selected_link(self) -> int | None:
        marks = self.page["spans"][self.cursor_line]
        if 0 <= self.cursor_mark < len(marks):
            return marks[self.cursor_mark][0]
        return None

    def open_selected(self) -> None:
        num = self.selected_link()
        if num is None:
            return
        self.page = self.browser.open_link(self.page, num)
        self.scroll = 0
        self.cursor_line = self._first_link_line()
        self.cursor_mark = 0

    def back(self) -> None:
        page = self.browser.back()
        if page is not None:
            self.page = page
            self.scroll = 0
            self.cursor_line = self._first_link_line()
            self.cursor_mark = 0

    def open_url(self, url: str) -> None:
        self.page = self.browser.go(url)
        self.scroll = 0
        self.cursor_line = self._first_link_line()
        self.cursor_mark = 0

    # drawing ------------------------------------------------------------------
    def _follow_scroll(self, rows: int) -> None:
        top = self.scroll
        bottom = top + rows - 1
        if self.cursor_line < top:
            self.scroll = self.cursor_line
        elif self.cursor_line > bottom:
            self.scroll = self.cursor_line - rows + 1
        self.scroll = max(0, min(self.scroll, max(0, len(self.page["lines"]) - rows)))

    def draw(self, screen, message: str = "") -> None:
        screen.erase()
        rows, cols = screen.getmaxyx()
        body_rows = max(1, rows - 2)
        self._follow_scroll(body_rows)
        status = f" {self.page['url']}"
        if self.page.get("title"):
            status += f" — {self.page['title']}"
        if self.page["status"]:
            status += f" [{self.page['status']}]"
        screen.addnstr(0, 0, status[: cols - 1], curses.A_REVERSE)
        for row in range(body_rows):
            i = self.scroll + row
            if i >= len(self.page["lines"]):
                break
            line = self.page["lines"][i]
            screen.addnstr(row + 1, 0, line[: cols - 1])
            for j, (num, start, end) in enumerate(self.page["spans"][i]):
                attr = curses.A_REVERSE if (i == self.cursor_line and j == self.cursor_mark) else curses.A_BOLD
                if end < cols - 1:
                    screen.chgat(row + 1, start, end - start + 1, attr)
        bottom = message if message else KEY_HINT
        screen.addnstr(rows - 1, 0, bottom[: cols - 1], curses.A_DIM)
        pos = f" {self.cursor_line + 1}/{len(self.page['lines'])}"
        if len(pos) < cols:
            screen.addnstr(rows - 1, cols - len(pos) - 1, pos, curses.A_DIM)

    def command_prompt(self, screen) -> str | None:
        buf = ""
        while True:
            self.draw(screen, message=f":{buf}")
            screen.refresh()
            key = screen.getch()
            if key in (curses.KEY_BACKSPACE, 127, 8):
                buf = buf[:-1]
            elif key in (10, 13, curses.KEY_ENTER):
                return buf
            elif key == 27:
                return None
            elif 32 <= key < 127:
                buf += chr(key)

    def run(self, screen) -> None:
        while True:
            self.draw(screen)
            screen.refresh()
            key = screen.getch()
            if key in (ord("j"), curses.KEY_DOWN):
                self.move(1)
            elif key in (ord("k"), curses.KEY_UP):
                self.move(-1)
            elif key == ord("b"):
                self.back()
            elif key == ord("q"):
                return
            elif key == ord("\t"):
                self.next_link()
            elif key in (10, 13, curses.KEY_ENTER):
                self.open_selected()
            elif key == ord(":"):
                cmd = self.command_prompt(screen)
                if cmd is None:
                    continue
                cmd = cmd.strip()
                if not cmd:
                    continue
                if cmd in ("q", "quit"):
                    return
                if cmd.startswith("open "):
                    cmd = cmd[5:].strip()
                elif cmd.startswith("o "):
                    cmd = cmd[2:].strip()
                self.open_url(cmd)


def interactive_main(url: str) -> int:
    if not sys.stdout.isatty():
        print("wbrowse: no terminal; use --dump URL for non-interactive rendering", file=sys.stderr)
        return 2
    viewer = Viewer(Browser(), url)
    curses.wrapper(viewer.run)
    return 0


# ---------------------------------------------------------------------------
# CLI

def main(argv: list[str]) -> int:
    args = list(argv)
    width = DEFAULT_WIDTH
    if "--width" in args:
        i = args.index("--width")
        if i + 1 >= len(args):
            print("wbrowse: --width needs a number", file=sys.stderr)
            return 2
        try:
            width = max(20, int(args[i + 1]))
        except ValueError:
            print("wbrowse: --width needs a number", file=sys.stderr)
            return 2
        del args[i:i + 2]
    dump_mode = False
    if "--dump" in args:
        dump_mode = True
        args.remove("--dump")
    html_file = None
    base = ""
    if "--html-file" in args:
        i = args.index("--html-file")
        if i + 1 >= len(args):
            print("wbrowse: --html-file needs a path", file=sys.stderr)
            return 2
        html_file = args[i + 1]
        del args[i:i + 2]
        if "--base" in args:
            j = args.index("--base")
            if j + 1 >= len(args):
                print("wbrowse: --base needs a URL", file=sys.stderr)
                return 2
            base = args[j + 1]
            del args[j:j + 2]
    targets = [a for a in args if not a.startswith("-")]
    if html_file:
        if len(targets) != 0:
            print("wbrowse: --html-file takes no other target", file=sys.stderr)
            return 2
        print_page(dump_html_file(html_file, base=base, width=width))
        return 0
    if not targets:
        print("usage: wbrowse [--dump] [--width N] URL | --html-file PATH [--base URL]", file=sys.stderr)
        return 2
    url = targets[0]
    if dump_mode:
        page = load_page(url)
        print_page(page)
        return 0 if 0 < page["status"] < 400 else 1
    return interactive_main(url)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
