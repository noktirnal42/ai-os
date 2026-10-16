#!/usr/bin/env python3
import pathlib
import sys

def usage():
    print("usage: aed FILE", file=sys.stderr)
    return 2

def main(argv):
    if len(argv) != 2:
        return usage()
    path = pathlib.Path(argv[1])
    lines = path.read_text().splitlines() if path.exists() else []
    undo = None
    dirty = False
    print(f"aed: {path} ({len(lines)} lines); :w save, :q quit, :wq save+quit, /text find")
    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if line == ":w":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + ("\n" if lines else ""))
            dirty = False
            print("written")
        elif line == ":q":
            if dirty:
                print("unsaved changes; use :wq or :q!", file=sys.stderr)
                return 1
            return 0
        elif line == ":q!":
            return 0
        elif line == ":wq":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + ("\n" if lines else ""))
            return 0
        elif line.startswith("/"):
            needle = line[1:]
            for idx, value in enumerate(lines, 1):
                if needle in value:
                    print(f"{idx}:{value}")
        elif line == "u":
            if undo is not None:
                lines, undo = undo, lines
                dirty = True
        elif line.startswith(":d "):
            try:
                idx = int(line[3:]) - 1
            except ValueError:
                print("error: :d requires a line number", file=sys.stderr)
                continue
            if 0 <= idx < len(lines):
                undo, lines = lines, lines[:idx] + lines[idx + 1:]
                dirty = True
            else:
                print("error: line out of range", file=sys.stderr)
        else:
            undo = list(lines)
            lines.append(line)
            dirty = True
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
