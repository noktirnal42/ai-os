#!/usr/bin/env python3
"""wbrowse acceptance tests (doc 07 §9, F4-2): >=15 checks over the parser,
renderer, link resolution, history stack, redirect handling and dump mode.
Network-dependent tests use a loopback-only HTTP server via the real libhttp
and are skipped automatically when libhttp is not installed."""
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import wbrowse

LIBHTTP = wbrowse.libhttp_path()
HAVE_LIBHTTP = os.path.isfile(LIBHTTP)
FIXTURE = HERE / "fixtures" / "sample.html"

PAGE_HTML = """<!DOCTYPE html><html><head><title>T</title></head><body>
<h1>Mock Page</h1><p>Loopback content with a <a href="next.html">link</a>.</p>
</body></html>"""


class LoopbackServer:
    def __init__(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redir":
                    self.send_response(301)
                    self.send_header("Location", "/page")
                    self.end_headers()
                elif self.path == "/redir2":
                    self.send_response(302)
                    self.send_header("Location", "/redir")
                    self.end_headers()
                elif self.path == "/page":
                    body = PAGE_HTML.encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()
            def log_message(self, *args):
                pass
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class ParserTests(unittest.TestCase):
    def test_headings_render_with_level_prefixes(self):
        parsed = wbrowse.parse_html("<h1>One</h1><h2>Two</h2><h6>Six</h6>")
        page = wbrowse.render_page(parsed)
        self.assertIn("# One", page["lines"])
        self.assertIn("## Two", page["lines"])
        self.assertIn("###### Six", page["lines"])

    def test_paragraphs_become_wrapped_text_blocks(self):
        parsed = wbrowse.parse_html("<p>first para</p><p>second para</p>")
        page = wbrowse.render_page(parsed)
        joined = "\n".join(page["lines"])
        self.assertIn("first para", joined)
        self.assertIn("second para", joined)
        self.assertNotIn("para second", joined.replace("\n", " "))

    def test_list_items_get_bullet_prefix(self):
        parsed = wbrowse.parse_html("<ul><li>alpha</li><li>beta</li></ul>")
        page = wbrowse.render_page(parsed)
        self.assertIn("- alpha", page["lines"])
        self.assertIn("- beta", page["lines"])

    def test_links_numbered_in_document_order_with_markers(self):
        parsed = wbrowse.parse_html('<p>See <a href="/a">first</a> and <a href="/b">second</a>.</p>')
        page = wbrowse.render_page(parsed)
        joined = " ".join(page["lines"])
        self.assertIn("first [1]", joined)
        self.assertIn("second [2]", joined)
        self.assertEqual(page["links"], {1: "/a", 2: "/b"})

    def test_nested_inline_tags_flatten_into_surrounding_text(self):
        parsed = wbrowse.parse_html("<p>plain <b>bold <i>both</i></b> end</p>")
        page = wbrowse.render_page(parsed)
        self.assertIn("plain bold both end", " ".join(page["lines"]))

    def test_entities_decode_including_numeric_refs(self):
        parsed = wbrowse.parse_html("<p>fish & chips, 3 < 4, caf&#233;</p>")
        page = wbrowse.render_page(parsed)
        joined = " ".join(page["lines"])
        self.assertIn("fish & chips", joined)
        self.assertIn("3 < 4", joined)
        self.assertIn("café", joined)

    def test_pre_block_passthrough_preserves_whitespace(self):
        parsed = wbrowse.parse_html("<pre>alpha\n  beta   gamma\n</pre>")
        page = wbrowse.render_page(parsed)
        self.assertIn("alpha", page["lines"])
        self.assertIn("  beta   gamma", page["lines"])

    def test_script_and_style_contents_are_ignored(self):
        parsed = wbrowse.parse_html("<style>.x{color:red}</style>"
                                    "<script>var secret='script-body-must-not-render';</script>"
                                    "<p>visible</p>")
        joined = " ".join(wbrowse.render_page(parsed)["lines"])
        self.assertIn("visible", joined)
        self.assertNotIn("script-body-must-not-render", joined)
        self.assertNotIn("color", joined)

    def test_title_captured_separately_not_as_body(self):
        parsed = wbrowse.parse_html("<html><head><title>My Title</title></head><body><p>body</p></body></html>")
        self.assertEqual(parsed["title"], "My Title")
        joined = " ".join(wbrowse.render_page(parsed)["lines"])
        self.assertNotIn("My Title", joined)
        self.assertIn("body", joined)

    def test_br_splits_within_paragraph(self):
        parsed = wbrowse.parse_html("<p>line one<br>line two</p>")
        page = wbrowse.render_page(parsed)
        self.assertIn("line one", page["lines"])
        self.assertIn("line two", page["lines"])
        self.assertNotIn("line one line two", " ".join(page["lines"]))

    def test_empty_anchor_renders_marker_only(self):
        parsed = wbrowse.parse_html('<p>Go <a href="/bare"></a> now</p>')
        page = wbrowse.render_page(parsed)
        joined = " ".join(page["lines"])
        self.assertIn("[1]", joined)
        self.assertEqual(page["links"], {1: "/bare"})

    def test_link_spans_record_marker_columns_for_cursor(self):
        parsed = wbrowse.parse_html('<p>words <a href="/x">target link</a> more</p>')
        page = wbrowse.render_page(parsed, width=80)
        spans = [s for s in page["spans"] if s]
        self.assertEqual(len(spans), 1)
        num, start, end = spans[0][0]
        self.assertEqual(num, 1)
        line = page["lines"][[i for i, s in enumerate(page["spans"]) if s][0]]
        self.assertEqual(line[start:end + 1], "[1]")


class RenderTests(unittest.TestCase):
    def test_wrapping_respects_width(self):
        text = "word " * 30
        parsed = wbrowse.parse_html(f"<p>{text}</p>")
        page = wbrowse.render_page(parsed, width=40)
        for line in page["lines"]:
            if line:
                self.assertLessEqual(len(line), 40)

    def test_pre_lines_are_never_wrapped(self):
        parsed = wbrowse.parse_html("<pre>" + "x" * 200 + "</pre>")
        page = wbrowse.render_page(parsed, width=40)
        self.assertIn("x" * 200, page["lines"])

    def test_relative_links_resolve_against_page_url(self):
        parsed = wbrowse.parse_html('<p><a href="next.html">l</a> <a href="/abs">a</a></p>')
        page = {"url": "http://example.com/dir/page", **wbrowse.render_page(parsed)}
        self.assertEqual(wbrowse.resolve_link(page, 1), "http://example.com/dir/next.html")
        self.assertEqual(wbrowse.resolve_link(page, 2), "http://example.com/abs")

    def test_normalize_url_adds_http_scheme(self):
        self.assertEqual(wbrowse.normalize_url("example.com"), "http://example.com")
        self.assertEqual(wbrowse.normalize_url(" https://x.io "), "https://x.io")


class HistoryTests(unittest.TestCase):
    def test_history_go_and_back(self):
        browser = wbrowse.Browser()
        self.assertEqual(len(browser.stack), 0)
        with unittest.mock.patch.object(wbrowse, "load_page", side_effect=lambda url, cache=None: {"url": url}):
            browser.go("http://a.example/")
            browser.go("http://b.example/")
            browser.go("http://c.example/")
            self.assertEqual(browser.stack, ["http://a.example/", "http://b.example/", "http://c.example/"])
            self.assertEqual(browser.back()["url"], "http://b.example/")
            self.assertEqual(browser.back()["url"], "http://a.example/")
            self.assertIsNone(browser.back())

    def test_history_truncates_forward_entries_on_new_go(self):
        browser = wbrowse.Browser()
        with unittest.mock.patch.object(wbrowse, "load_page", side_effect=lambda url, cache=None: {"url": url}):
            browser.go("http://a.example/")
            browser.go("http://b.example/")
            browser.back()
            browser.go("http://d.example/")
            self.assertEqual(browser.stack, ["http://a.example/", "http://d.example/"])


import unittest.mock  # noqa: E402  (used above; kept at bottom to mirror import style)


@unittest.skipUnless(HAVE_LIBHTTP, "libhttp CLI not installed")
class FetchTests(unittest.TestCase):
    def test_fetch_follows_redirects_via_libhttp(self):
        with LoopbackServer() as server:
            status, body = wbrowse.fetch(f"http://127.0.0.1:{server.port}/redir2")
            self.assertEqual(status, 200)
            self.assertIn("Loopback content", body)

    def test_dump_end_to_end_through_redirect(self):
        with LoopbackServer() as server:
            proc = subprocess.run(
                [sys.executable, str(HERE.parent / "wbrowse.py"), "--dump", f"http://127.0.0.1:{server.port}/redir"],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("# Mock Page", proc.stdout)
            self.assertIn("link [1]", proc.stdout)

    def test_dump_http_error_status_fails_with_error_page(self):
        with LoopbackServer() as server:
            proc = subprocess.run(
                [sys.executable, str(HERE.parent / "wbrowse.py"), "--dump", f"http://127.0.0.1:{server.port}/missing"],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("HTTP 404", proc.stdout)


class DumpModeTests(unittest.TestCase):
    def test_dump_renders_local_fixture_file(self):
        proc = subprocess.run(
            [sys.executable, str(HERE.parent / "wbrowse.py"), "--html-file", str(FIXTURE),
             "--base", "http://example.com/dir/", "--width", "60"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# AI OS Sample", proc.stdout)
        self.assertIn("- First item links to a relative page [3]", proc.stdout)
        self.assertIn("the external site [2]", proc.stdout)
        self.assertIn("  and   indentation", proc.stdout)
        self.assertIn('fish & chips', proc.stdout)
        self.assertNotIn("script-body-must-not-render", proc.stdout)

    def test_usage_error_without_target(self):
        proc = subprocess.run([sys.executable, str(HERE.parent / "wbrowse.py")],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
