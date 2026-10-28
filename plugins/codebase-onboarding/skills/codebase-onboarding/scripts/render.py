#!/usr/bin/env python3
"""Validate atlas.json and render it into a single self-contained atlas.html.

Usage: python3 render.py atlas.json [-o atlas.html] [--force]
"""
import argparse
import base64
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "viewer.html")
FONTS = os.path.join(HERE, "..", "assets", "fonts")


def font_css():
    """Embed Geist (SIL OFL) so the page looks right offline, with no network fetch."""
    css = []
    for fam, fn in (("Geist", "Geist-Variable.woff2"), ("Geist Mono", "GeistMono-Variable.woff2")):
        path = os.path.join(FONTS, fn)
        if os.path.exists(path):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            css.append(f'@font-face{{font-family:"{fam}";src:url(data:font/woff2;base64,{b64}) format("woff2");'
                       f'font-weight:100 900;font-style:normal;font-display:swap}}')
    return "\n".join(css)
LAYERS = {"client", "identity", "edge", "compute", "messaging", "data", "external", "ops"}


def validate(a):
    errors, warns = [], []
    if not isinstance(a.get("meta"), dict) or not a["meta"].get("name"):
        errors.append("meta.name is required")
    nodes = a.get("nodes") or []
    if not nodes:
        errors.append("nodes is empty")
    ids = set()
    for i, n in enumerate(nodes):
        nid = n.get("id")
        if not nid:
            errors.append(f"nodes[{i}] has no id")
            continue
        if nid in ids:
            errors.append(f"duplicate node id '{nid}'")
        ids.add(nid)
        if not n.get("label"):
            warns.append(f"node '{nid}' has no label")
        if n.get("layer") not in LAYERS:
            warns.append(f"node '{nid}' layer '{n.get('layer')}' not one of {sorted(LAYERS)} — shown under 'external'")
        if n.get("confidence") not in ("declared", "inferred"):
            warns.append(f"node '{nid}' confidence should be declared|inferred")
    for i, e in enumerate(a.get("edges") or []):
        for end in ("from", "to"):
            if e.get(end) not in ids:
                errors.append(f"edges[{i}] {end} '{e.get(end)}' is not a node id")
    for f in a.get("flows") or []:
        if not f.get("name"):
            warns.append(f"flow '{f.get('id')}' has no name")
        for j, s in enumerate(f.get("steps") or []):
            for end in ("from", "to"):
                if s.get(end) not in ids:
                    errors.append(f"flow '{f.get('id') or f.get('name')}' step {j + 1} {end} '{s.get(end)}' is not a node id")
    connected = {e.get("from") for e in a.get("edges") or []} | {e.get("to") for e in a.get("edges") or []}
    orphans = sorted(ids - connected)
    if orphans:
        warns.append(f"{len(orphans)} unconnected node(s): {', '.join(orphans[:10])}")
    if not (a.get("meta") or {}).get("summary"):
        warns.append("meta.summary is empty — write one paragraph describing the system")
    if not a.get("flows"):
        warns.append("no flows — add 3–6 key request flows")
    if not a.get("tour"):
        warns.append("no tour — add 5–8 ordered stops")
    return errors, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("atlas")
    ap.add_argument("-o", "--out")
    ap.add_argument("--force", action="store_true", help="render even with validation errors")
    a = ap.parse_args()
    with open(a.atlas, encoding="utf-8") as f:
        data = json.load(f)
    errors, warns = validate(data)
    for w in warns:
        print(f"warn: {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if errors and not a.force:
        sys.exit(f"{len(errors)} error(s); fix them or pass --force")
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    title = html.escape(f"{data.get('meta', {}).get('name', 'Project')} · Onboarding Atlas")
    out = tpl.replace("/*__FONTS__*/", font_css()).replace("__ATLAS_TITLE__", title).replace("__ATLAS_JSON__", payload)
    dest = a.out or os.path.splitext(a.atlas)[0] + ".html"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"rendered -> {dest}  ({len(data.get('nodes', []))} nodes, {len(data.get('edges', []))} edges, {len(data.get('flows', []))} flows)", file=sys.stderr)


if __name__ == "__main__":
    main()
