"""Merge the three source files into data/records/all.jsonl (docs/CONTRACTS.md section 1).

    python -m data_pipeline.merge

Smapshot and E-Pics overlap for ETH images: Smapshot's `raw.original_id` is the E-Pics file
name. Such pairs become ONE record: the E-Pics record (license, places, DOI) enriched with the
Smapshot camera pose, which is more precise than E-Pics' own point. Both source ids are kept in
`raw.merged_from`. Smapshot images outside the canton stay in (useful references for similarity
search); `raw.in_canton` tells them apart. Safe to re-run while scrapers are still writing.
"""

import argparse
from collections import Counter

from .jsonl import read_jsonl, write_jsonl
from .paths import RECORDS

SOURCES = ("staatsarchiv", "epics", "smapshot")


def _pixels(rec: dict) -> int:
    img = rec.get("image") or {}
    return (img.get("width") or 0) * (img.get("height") or 0)


def _merge_pair(ep: dict, sm: dict) -> dict:
    out = dict(ep)
    out["raw"] = dict(ep.get("raw") or {})
    out["raw"]["merged_from"] = [ep["id"], sm["id"]]
    out["raw"]["smapshot"] = {
        "id": sm["source_id"],
        "url": sm.get("source_url"),
        "view_type": (sm.get("raw") or {}).get("view_type"),
    }
    if sm.get("camera"):
        out["camera"] = sm["camera"]
        if sm.get("location"):
            out["location"] = sm["location"]  # smapshot_pose: georeferenced, beats the E-Pics point
    if _pixels(sm) > _pixels(ep):
        out["image"] = sm["image"]
    if not out.get("municipality") and sm.get("municipality"):
        out["municipality"] = sm["municipality"]
    if out.get("date", {}).get("year_from") is None and sm.get("date", {}).get("year_from") is not None:
        out["date"] = sm["date"]
    if (sm.get("raw") or {}).get("in_canton") is not None:
        out["raw"]["in_canton"] = sm["raw"]["in_canton"]
    return out


def merge() -> dict:
    stasz = list(read_jsonl(RECORDS / "staatsarchiv.jsonl"))
    epics = list(read_jsonl(RECORDS / "epics.jsonl"))
    smap = list(read_jsonl(RECORDS / "smapshot.jsonl"))

    by_file = {}
    for r in epics:
        by_file[r["source_id"]] = r
    merged_ids = set()
    out: dict[str, dict] = {}

    for r in stasz:
        out[r["id"]] = r
    for r in smap:
        key = (r.get("raw") or {}).get("original_id")
        if key and key in by_file:
            m = _merge_pair(by_file[key], r)
            out[m["id"]] = m
            merged_ids.add(m["id"])
        else:
            out[r["id"]] = r
    for r in epics:
        if r["id"] not in out:
            out[r["id"]] = r

    # dedupe identical images (same sha1) across sources, keep the first seen
    seen_sha = {}
    rows = []
    dup = 0
    for r in out.values():
        sha = (r.get("image") or {}).get("sha1")
        if sha and sha in seen_sha:
            dup += 1
            continue
        if sha:
            seen_sha[sha] = r["id"]
        rows.append(r)

    # preserve an existing split assignment (splits.py owns it)
    old = {r["id"]: r.get("split") for r in read_jsonl(RECORDS / "all.jsonl")}
    for r in rows:
        if old.get(r["id"]):
            r["split"] = old[r["id"]]
        elif not r.get("split") or r["split"] == "none":
            r["split"] = "reference" if r["source"] != "staatsarchiv" else "none"

    n = write_jsonl(RECORDS / "all.jsonl", rows)
    stats = {
        "inputs": {"staatsarchiv": len(stasz), "epics": len(epics), "smapshot": len(smap)},
        "merged_epics_smapshot": len(merged_ids),
        "duplicate_images_dropped": dup,
        "all": n,
        "by_source": dict(Counter(r["source"] for r in rows)),
    }
    return stats


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(merge())


if __name__ == "__main__":
    main()
