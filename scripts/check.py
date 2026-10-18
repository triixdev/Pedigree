"""Trace a model from the terminal.

    python -m scripts.check org/model [depth]
"""
import sys

from pedigree import service

model = sys.argv[1]
depth = int(sys.argv[2]) if len(sys.argv) > 2 else 4
result = service.check(model, depth)
flags = result["flags"]
counts = {s: len([f for f in flags if f["severity"] == s]) for s in ("review", "warn", "info")}
print(f"{model} (depth {depth}): {counts['review']} to review, {counts['warn']} warnings, {counts['info']} notes")
for f in flags:
    print()
    print(f"[{f['severity'].upper()}] {f['kind']}")
    print("  path:   " + " -> ".join(p["id"] for p in f["path"]))
    print("  why:    " + f["summary"])
    print("  source: " + "  ".join(f["evidence"]))
print()
print("These are flags for human review. They are not legal conclusions.")