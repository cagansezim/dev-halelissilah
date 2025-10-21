#!/usr/bin/env python3
import sys, re
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# Pattern:  name: Field = Field(....)
BAD = re.compile(r"^(\s*)([A-Za-z_]\w*)\s*:\s*Field\s*=\s*Field\((.*?)\)\s*$")

def fix_line(line: str):
    m = BAD.match(line)
    if not m:
        return line, False
    indent, name, args = m.groups()
    # Keep default=... if present, else None (equivalent in most existing models)
    default = "None"
    for piece in re.split(r",(?![^(]*\))", args):
        if "default=" in piece or "default_factory=" in piece:
            default = piece.strip()
            break
    # Replace with a simple assignment; existing validators still work on the model.
    new_line = f"{indent}{name}: object = {default}\n"
    return new_line, True

changed = 0
for path in ROOT.rglob("*.py"):
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue
    new_lines = []
    file_changed = False
    for ln in text.splitlines(keepends=True):
        nl, did = fix_line(ln)
        new_lines.append(nl)
        file_changed |= did
    if file_changed:
        path.write_text("".join(new_lines), encoding="utf-8")
        print(f"patched: {path}")
        changed += 1

print(f"pydantic patch complete; files changed: {changed}")
