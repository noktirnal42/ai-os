#!/usr/bin/env python3
import http.server
import json
import os
import pathlib
import socketserver
import subprocess
import threading

NET_BIN = pathlib.Path(__file__).parents[1] / "bin"

class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/")
            self.end_headers()
            return
        body = b"NET_OK\n"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_): pass

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def run(tool, url, *, allow="127.0.0.1", enabled="1"):
    env = {**os.environ, "AIOS_FETCH_ALLOWLIST": allow}
    if enabled is None: env.pop("AIOS_ALLOW_NETWORK", None)
    else: env["AIOS_ALLOW_NETWORK"] = enabled
    return subprocess.run([str(NET_BIN / tool), url], capture_output=True, text=True, env=env, timeout=8)

def main():
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        good = run("a-fetch", base + "/")
        assert good.returncode == 0 and good.stdout == "NET_OK\n", good
        assert run("a-fetch", base + "/", enabled=None).returncode == 4
        assert run("a-fetch", base + "/", allow="example.com").returncode == 3
        redirected = run("a-fetch", base + "/redirect")
        assert redirected.returncode != 0 and "allowlist" in redirected.stderr.lower(), redirected
        check = run("a-netcheck", base + "/")
        result = json.loads(check.stdout)
        assert check.returncode == 0 and result["http_status"] == 200 and result["addresses"], check
        assert run("a-netcheck", base + "/", enabled=None).returncode == 4
        assert run("a-netcheck", base + "/", allow="example.com").returncode == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    print("NET ALL PASS (gate, allowlist, DNS, HTTP, redirect policy)")

if __name__ == "__main__": main()
