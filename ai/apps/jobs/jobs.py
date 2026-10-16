#!/usr/bin/env python3
import json, os, pathlib, signal, subprocess, sys, time

ROOT = pathlib.Path(os.environ.get("AIOS_ROOT", "/ai"))
STATE = ROOT / "state" / "jobs"

def usage():
    print("usage: jobs start CMD... | jobs list | jobs kill ID | jobs log ID", file=sys.stderr)
    return 2

def main(argv):
    STATE.mkdir(parents=True, exist_ok=True)
    if len(argv) < 2: return usage()
    op = argv[1]
    if op == "start" and len(argv) > 2:
        jid = time.strftime("%Y%m%d%H%M%S") + "-" + str(os.getpid())
        log = STATE / (jid + ".log")
        with log.open("w") as fh:
            proc = subprocess.Popen(argv[2:], stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        (STATE / (jid + ".json")).write_text(json.dumps({"id": jid, "pid": proc.pid, "cmd": argv[2:], "log": str(log)}))
        print(jid)
        return 0
    if op == "list" and len(argv) == 2:
        for meta in sorted(STATE.glob("*.json")):
            row = json.loads(meta.read_text())
            alive = (pathlib.Path("/proc") / str(row["pid"])).exists()
            print(row["id"], "running" if alive else "done", " ".join(row["cmd"]))
        return 0
    if op in ("kill", "log") and len(argv) == 3:
        meta = STATE / (argv[2] + ".json")
        if not meta.exists():
            print("error: unknown job", file=sys.stderr)
            return 1
        row = json.loads(meta.read_text())
        if op == "kill":
            try: os.killpg(row["pid"], signal.SIGTERM)
            except ProcessLookupError: pass
            return 0
        print(pathlib.Path(row["log"]).read_text(), end="")
        return 0
    return usage()

if __name__ == "__main__": sys.exit(main(sys.argv))
