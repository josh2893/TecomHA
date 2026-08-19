#!/usr/bin/env python3
"""Structural checks that must pass before any release.

These catch the classes of mistake that are easy to make and invisible until a
user hits them: a service documented but never registered, a platform listed
with no module, a translation key missing so the options screen shows a raw
field name, or site data committed to a public repository.

    python3 tools/validate_project.py
"""
from __future__ import annotations

import ast
import glob
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    raise SystemExit(2)

D = "custom_components/tecom_challengerplus"
failures: list[str] = []
notes: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label} {detail}".strip())


print("Syntax")
for f in sorted(glob.glob(f"{D}/*.py")):
    try:
        ast.parse(open(f).read())
        ok, detail = True, ""
    except SyntaxError as e:
        ok, detail = False, str(e)
    check(os.path.basename(f), ok, detail)

print("\nSchemas")
services = {}
try:
    services = yaml.safe_load(open(f"{D}/services.yaml")) or {}
    check("services.yaml parses", True)
except Exception as e:
    check("services.yaml parses", False, str(e))

translations = {}
try:
    translations = json.load(open(f"{D}/translations/en.json"))
    check("translations/en.json parses", True)
except Exception as e:
    check("translations/en.json parses", False, str(e))

manifest = {}
try:
    manifest = json.load(open(f"{D}/manifest.json"))
    check("manifest.json parses", True)
except Exception as e:
    check("manifest.json parses", False, str(e))

print("\nWiring")
init = open(f"{D}/__init__.py").read()
registered = set(re.findall(r'async_register\(\s*DOMAIN,\s*"([a-z_]+)"', init))
missing = sorted(set(services) - registered)
check("every service in services.yaml is registered", not missing, str(missing))

undocumented = sorted(registered - set(services))
if undocumented:
    notes.append(f"registered but not in services.yaml: {undocumented}")

m = re.search(r"PLATFORMS[^=]*=\s*(\[[^\]]*\])", init)
platforms = eval(m.group(1)) if m else []
missing_mod = [p for p in platforms if not os.path.exists(f"{D}/{p}.py")]
check("every platform has a module", not missing_mod, str(missing_mod))

print("\nConfig UI")
# Every option offered in the schema needs a label in both the setup wizard and
# the options screen, or the user sees a raw key.
cf = open(f"{D}/config_flow.py").read()
const = open(f"{D}/const.py").read()
conf_map = dict(re.findall(r'CONF_([A-Z_0-9]+)\s*=\s*"([a-z_0-9]+)"', const))
used = {conf_map[k] for k in re.findall(r"vol\.\w+\(CONF_([A-Z_0-9]+)", cf) if k in conf_map}
for screen, path in (("setup wizard", ("config", "step", "user")),
                     ("options screen", ("options", "step", "init"))):
    node = translations
    for part in path:
        node = node.get(part, {}) if isinstance(node, dict) else {}
    labelled = set(node.get("data", {}))
    gap = sorted(used - labelled)
    check(f"{screen}: all fields labelled", not gap, str(gap))

print("\nPrivacy")
# Debug dumps and captures come from a live site; nothing identifying should
# reach a public repository.
patterns = [r"192\.168\.1\.(?:245|34)\b"]
hits = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".github"}]
    for name in files:
        if not name.endswith((".py", ".md", ".json", ".yaml", ".yml", ".js")):
            continue
        if name == "ctplus_eventtable_data.py":
            continue
        p = os.path.join(root, name)
        try:
            text = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for pat in patterns:
            for match in re.finditer(pat, text):
                hits.append(f"{p}: {match.group(0)}")
check("no site-specific addresses committed", not hits, str(hits[:5]))

print("\nDocumentation")
check("CHANGELOG.md exists", os.path.exists("CHANGELOG.md"))
if manifest.get("version") and os.path.exists("CHANGELOG.md"):
    ver = manifest["version"]
    has = re.search(rf"^## Version {re.escape(ver)}\s*$", open("CHANGELOG.md").read(), re.M)
    check(f"CHANGELOG has a section for {ver}", bool(has))

if notes:
    print("\nNotes")
    for n in notes:
        print(f"  {n}")

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    raise SystemExit(1)
print("All checks passed")
