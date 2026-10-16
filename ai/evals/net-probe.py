#!/usr/bin/env python3
"""Read-only Phase 2 network evidence probe."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import aios

result = aios.Session("network status probe", aios.ModelClient("http://unused", offline=True)).call_tool("net", {"op": "status"})
if "error" in result or result["interfaces"] < 1:
    raise SystemExit(f"network probe failed: {result}")
payload = json.loads((aios.AI_ROOT / "state" / "net.json").read_text())
if payload.get("schema_version") != 1 or not payload.get("emulated"):
    raise SystemExit("network evidence missing schema/emulated marker")
print(f"network probe: PASS ({result['interfaces']} interfaces, {result['routes']} routes)")
