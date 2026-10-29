#!/usr/bin/env python3
"""Merge an enrichment patch into atlas.json, so the agent writes only what it adds.

Usage: python3 merge.py <atlas.json> <patch.json>   (atlas.json is updated in place)

Patch rules:
  nodes            upsert by "id"; given fields overwrite, others are kept
  edges            upsert by ("from", "to", "kind")
  remove_nodes     list of node ids to delete (their edges go too)
  remove_edges     list of {"from","to","kind"} to delete
  objects          (meta, auth, data, run, operate, context, code ...) merged key by key
  other lists      (flows, apis, tour, gaps, run.setup ...) replace the existing list;
                   prefix the key with "+" to append instead, e.g. "+gaps": ["..."]
"""
import json
import sys


def upsert(items, new, key):
    index = {key(x): i for i, x in enumerate(items)}
    for n in new:
        k = key(n)
        if k in index:
            items[index[k]].update(n)
        else:
            index[k] = len(items)
            items.append(n)


def merge(dst, src):
    for k, v in src.items():
        if k.startswith("+"):
            dst.setdefault(k[1:], []).extend(v)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = v


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    atlas_path, patch_path = sys.argv[1], sys.argv[2]
    with open(atlas_path, encoding="utf-8") as f:
        atlas = json.load(f)
    with open(patch_path, encoding="utf-8") as f:
        patch = json.load(f)

    atlas.setdefault("nodes", [])
    atlas.setdefault("edges", [])
    upsert(atlas["nodes"], patch.pop("nodes", []), lambda n: n["id"])
    ekey = lambda e: (e["from"], e["to"], e.get("kind", ""))
    upsert(atlas["edges"], patch.pop("edges", []), ekey)

    gone = set(patch.pop("remove_nodes", []))
    if gone:
        atlas["nodes"] = [n for n in atlas["nodes"] if n["id"] not in gone]
        atlas["edges"] = [e for e in atlas["edges"] if e["from"] not in gone and e["to"] not in gone]
    drop = {ekey(e) for e in patch.pop("remove_edges", [])}
    if drop:
        atlas["edges"] = [e for e in atlas["edges"] if ekey(e) not in drop]

    merge(atlas, patch)
    with open(atlas_path, "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)
    print(f"merged -> {atlas_path}  ({len(atlas['nodes'])} nodes, {len(atlas['edges'])} edges, "
          f"{len(atlas.get('flows') or [])} flows)", file=sys.stderr)


if __name__ == "__main__":
    main()
