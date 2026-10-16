#!/usr/bin/env python3
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import aios

def main():
    session = aios.Session("sandbox probes", aios.ModelClient("http://unused", offline=True), max_tools=20)
    probes = [
        ("read shadow", session.call_tool("fs_read", {"path": "/etc/shadow"}), "error"),
        ("write secret", session.call_tool("fs_write", {"path": "/ai/secrets/probe", "content": "x"}), "error"),
        ("network shell", session.call_tool("shell", {"cmd": "curl http://example.com"}), "error"),
        ("protected shell", session.call_tool("shell", {"cmd": "cat /etc/passwd"}), "error"),
    ]
    failed = [name for name, result, expected in probes if expected not in result]
    if failed:
        print("failed probes: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("sandbox probes: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
