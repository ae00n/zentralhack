"""Where a result's buildings and landmarks are in the photo: `photo_marks` for the frontend.

    python -m agent.photo_marks [--split challenge] [--priority 1] [ids...]

One Claude call per result: the photo (1024 px) and the names from fields.buildings and
fields.landscape_features. Claude boxes each name it can see, in pixels of that image; we store
[{name, kind, x, y, box}] with x, y the box centre and box = [x0, y0, x1, y1], all 0..1 of the
width and height, (0, 0) top left. Names it cannot see are left out, never guessed.
Written into the result file in place (data/results/<photo_id>.json), cached by input.
"""

import argparse
import io
import json

import data_pipeline as dp

from . import llm, results
from .config import MODEL
from .v7.common import CACHE_ONLY, block, cached, key, store

PX = 1024
VERSION = "marks.1"
KINDS = ("mountain", "water", "building", "place")
TOOL = {
    "name": "marks", "description": "Boxes of the listed names visible in the photo. Call exactly once.", "strict": True,
    "input_schema": {"type": "object", "additionalProperties": False, "properties": {"marks": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "name": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)},
            "x0": {"type": "integer"}, "y0": {"type": "integer"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}},
            "required": ["name", "kind", "x0", "y0", "x1", "y1"]}}}, "required": ["marks"]}}

PROMPT = """The photo is {w} x {h} pixels. For each name below that is visible in it, give the box around it \
in pixels (x0, y0 top left; x1, y1 bottom right) and its kind (mountain, water, building, place). A mountain's \
box is around its visible summit area; a lake's around the visible water; a building's around the building \
itself. Leave out every name you cannot clearly see in the photo.

Names:
{names}"""


def _image(rec: dict) -> tuple[bytes, int, int]:
    from PIL import Image
    with Image.open(dp.image_file(rec)) as im:
        im = im.convert("RGB")
        im.thumbnail((PX, PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), im.width, im.height


def names_of(result: dict) -> list[str]:
    f = result.get("fields") or {}
    out = []
    for k in ("buildings", "landscape_features"):
        for n in (f.get(k) or {}).get("value") or []:
            if n and n not in out:
                out.append(n)
    return out


def marks(rec: dict, result: dict) -> tuple[list[dict], float]:
    """(photo_marks, usd)."""
    names = names_of(result)
    if not names:
        return [], 0.0
    data, w, h = _image(rec)
    k = key(VERSION, MODEL, rec["id"], names, w, h)
    if (hit := cached(k)) is None:
        if CACHE_ONLY:
            return [], 0.0
        resp, usd = llm.create(
            llm.make_client(), model=MODEL, meta={"photo_id": rec["id"], "step": "photo_marks"}, max_tokens=4000,
            tools=[TOOL], tool_choice={"type": "auto"}, output_config={"effort": "low"},
            messages=[{"role": "user", "content": [block(data), {"type": "text", "text": PROMPT.format(
                w=w, h=h, names="\n".join(f"- {n}" for n in names))}]}])
        use = next((b for b in resp.content if b.type == "tool_use" and b.name == "marks"), None)
        hit = {"marks": (use.input.get("marks") if use else None) or [], "usd": usd}
        store(k, hit)
    else:
        usd = 0.0
    out = []
    for m in hit["marks"]:
        if m["name"] not in names or m["kind"] not in KINDS:
            continue  # only what the result names
        x0, x1 = sorted((max(0, min(w, m["x0"])) / w, max(0, min(w, m["x1"])) / w))
        y0, y1 = sorted((max(0, min(h, m["y0"])) / h, max(0, min(h, m["y1"])) / h))
        if x1 - x0 < 0.005 or y1 - y0 < 0.005:
            continue
        out.append({"name": m["name"], "kind": m["kind"], "x": round((x0 + x1) / 2, 4), "y": round((y0 + y1) / 2, 4),
                    "box": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]})
    return out, usd


def run(ids: list[str]) -> None:
    total = 0.0
    for pid in ids:
        r, rec = results.load(pid), dp.get_record(pid)
        if not r or not rec:
            continue
        m, usd = marks(rec, r)
        total += usd
        r["photo_marks"] = m
        results.save(r)
        print(f"{pid}: {', '.join(x['name'] for x in m) or '-'}  ${usd:.3f}", flush=True)
    print(f"total ${total:.2f}")


def main() -> None:
    from data_pipeline.jsonl import read_jsonl
    from data_pipeline.paths import RECORDS

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--split", default="challenge")
    ap.add_argument("--priority", type=int, default=1)
    a = ap.parse_args()
    ids = a.ids or [r["id"] for r in read_jsonl(RECORDS / f"{a.split}.jsonl")
                    if a.priority is None or (r.get("raw") or {}).get("priority") == a.priority]
    run(ids)


if __name__ == "__main__":
    main()
