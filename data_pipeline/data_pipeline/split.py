"""Composite postcard splitter.

Many archive cards hold several photos: "Gruss aus Schwyz" collages, an oval inset of the
hotel next to the village view, two views stacked on one card. In this archive the panels
usually touch or overlap with no paper gap, so classical CV (paper/gutter segmentation,
straight-line frame detection) found none of the 10 hand-labelled composites
(see `python -m data_pipeline.split eval`). The working method is a vision model:

- method "vlm" (default when ANTHROPIC_API_KEY is set): Claude Haiku returns the photo panels
  as normalised boxes. About 500 image tokens per card, well under $1 for all 6.4k cards.
  Answers are cached in data/splits/composite_cache.jsonl, so each card is asked once.
- method "cv": conservative paper-gap segmentation. Only fires when panels sit on visible
  card paper; never splits a single photo in the labelled set.

    split_composite("data/images/staatsarchiv/359891.jpg", photo_id="stasz:359891")
    -> [{"bbox": [x, y, w, h], "path": ".../crops/stasz:359891#1.jpg"}, ...]

One item with the full image is returned when the card is not composite.

    python -m data_pipeline.split eval [--method cv|vlm]   # against tests/split_labels.json
    python -m data_pipeline.split batch [--limit N]        # all Staatsarchiv cards -> records/crops.jsonl
    python -m data_pipeline.split run <img>...
"""

import argparse
import base64
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

from .paths import DATA_DIR, IMAGES, RECORDS, SPLITS, ensure

CROP_DIR = IMAGES / "crops"
CACHE = SPLITS / "composite_cache.jsonl"
LABELS = Path(__file__).resolve().parents[1] / "tests" / "split_labels.json"
VLM_MODEL = os.environ.get("SPLIT_MODEL", "claude-haiku-5-5")
MIN_PANEL_SHARE = 0.03  # ignore boxes smaller than 3% of the card (stamps, coats of arms)

VLM_PROMPT = """This is a scanned historical postcard. Some postcards show several separate photographs \
(or printed photo views) on one card, e.g. a collage, an inset oval or a second view next to the first. \
Decorations, ornaments, coats of arms, printed text, handwriting and stamps are NOT photographs.

List every separate photograph on the card with its bounding box as fractions of the card width and height \
(x0, y0 = top left, x1, y1 = bottom right, values 0 to 1). If the whole card is one photograph \
(even with a caption or a border), return exactly one box covering it.

Answer with JSON only: {"panels": [{"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}]}"""

_BOX = {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
        "properties": {k: {"type": "number"} for k in ("x0", "y0", "x1", "y1")}}
PANELS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["panels"],
                 "properties": {"panels": {"type": "array", "items": _BOX}}}


# ---------- classical CV (conservative fallback) ----------

def find_panels_cv(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Panels separated by visible card paper. [] when not composite."""
    H, W = img.shape[:2]
    s = 400 / max(H, W)
    sm = cv2.resize(img, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
    h, w = sm.shape[:2]
    g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY).astype(np.float32)
    m = cv2.boxFilter(g, -1, (5, 5))
    sq = cv2.boxFilter(g * g, -1, (5, 5))
    std = np.sqrt(np.maximum(sq - m * m, 0))
    # card paper = smooth regions connected to the card edge
    n, lab, _, _ = cv2.connectedComponentsWithStats((std < 6).astype(np.uint8), 4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    content = (~np.isin(lab, list(edge))).astype(np.uint8)
    k = max(3, int(0.015 * max(h, w)))
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(content, 8)
    out = []
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 0.035 * h * w or a / (bw * bh) < 0.55 or not 0.2 < bw / bh < 5:
            continue
        if std[lab == i].mean() < 12:
            continue  # flat region, not a photo
        out.append((x, y, bw, bh, a))
    if len(out) < 2 or max(o[4] for o in out) > 0.72 * h * w:
        return []
    inv = 1 / s
    return [(int(x * inv), int(y * inv), int(bw * inv), int(bh * inv)) for x, y, bw, bh, _ in out]


# ---------- vision model ----------

_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        if CACHE.exists():
            for line in CACHE.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    _cache[r["key"]] = r["panels"]
    return _cache


def find_panels_vlm(path: Path, key: str) -> list[tuple[int, int, int, int]]:
    cache = _load_cache()
    img = cv2.imread(str(path))
    H, W = img.shape[:2]
    if key not in cache:
        import anthropic

        data = base64.standard_b64encode(path.read_bytes()).decode()
        # Haiku 5.5 thinks by default: low effort keeps that short, and the JSON schema
        # guarantees the text block parses (a small max_tokens used to cut it off mid-JSON)
        msg = anthropic.Anthropic().messages.create(
            model=VLM_MODEL,
            max_tokens=4000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": PANELS_SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
                {"type": "text", "text": VLM_PROMPT},
            ]}],
        )
        text = next((b.text for b in msg.content if b.type == "text"), "")
        panels = json.loads(text)["panels"] if text else []
        cache[key] = panels
        ensure(SPLITS)
        with CACHE.open("a") as f:
            f.write(json.dumps({"key": key, "panels": panels, "model": VLM_MODEL}) + "\n")
    boxes = []
    for p in cache[key]:
        x0, y0 = max(0.0, float(p["x0"])), max(0.0, float(p["y0"]))
        x1, y1 = min(1.0, float(p["x1"])), min(1.0, float(p["y1"]))
        if (x1 - x0) * (y1 - y0) < MIN_PANEL_SHARE:
            continue
        boxes.append((int(x0 * W), int(y0 * H), int((x1 - x0) * W), int((y1 - y0) * H)))
    return boxes if len(boxes) >= 2 else []


def _method(method: str | None) -> str:
    return method or ("vlm" if os.environ.get("ANTHROPIC_API_KEY") else "cv")


# ---------- contract ----------

def _resolve(image_path: str) -> Path:
    p = Path(image_path)
    if not p.exists() and not p.is_absolute():
        p = DATA_DIR / image_path
    if not p.exists():
        raise FileNotFoundError(image_path)
    return p


def split_composite(image_path: str, photo_id: str | None = None, method: str | None = None) -> list[dict]:
    """CONTRACTS section 4: [{bbox:[x,y,w,h], path}]; one full-image item when not composite."""
    p = _resolve(image_path)
    img = cv2.imread(str(p))
    H, W = img.shape[:2]
    stem = photo_id or p.stem
    boxes = find_panels_vlm(p, stem) if _method(method) == "vlm" else find_panels_cv(img)
    if len(boxes) < 2:
        return [{"bbox": [0, 0, W, H], "path": str(p)}]
    ensure(CROP_DIR)
    out = []
    for i, (x, y, w, h) in enumerate(sorted(boxes, key=lambda b: (b[1] // 40, b[0])), 1):
        path = CROP_DIR / f"{stem}#{i}.jpg"
        cv2.imwrite(str(path), img[y:y + h, x:x + w], [cv2.IMWRITE_JPEG_QUALITY, 90])
        out.append({"bbox": [x, y, w, h], "path": str(path)})
    return out


# ---------- CLI ----------

def _eval(method: str) -> None:
    labels = {k: v for k, v in json.loads(LABELS.read_text()).items() if not k.startswith("_")}
    tp = fp = fn = tn = exact = 0
    times = []
    for sid, true_n in labels.items():
        path = IMAGES / "staatsarchiv" / f"{sid}.jpg"
        if not path.exists():
            continue
        t = time.perf_counter()
        if method == "vlm":
            n = len(find_panels_vlm(path, f"stasz:{sid}"))
        else:
            n = len(find_panels_cv(cv2.imread(str(path))))
        times.append(time.perf_counter() - t)
        pc, tc = n >= 2, true_n >= 2
        tp += pc and tc
        fp += pc and not tc
        fn += tc and not pc
        tn += not pc and not tc
        exact += max(n, 1) == true_n
        if pc != tc or (tc and n != true_n):
            print(f"  {sid}: true {true_n}, predicted {max(n, 1)}")
    total = tp + fp + fn + tn
    prec = f"{tp / (tp + fp):.2f}" if tp + fp else "n/a"
    rec = f"{tp / (tp + fn):.2f}" if tp + fn else "n/a"
    print(f"{method}: n={total}, composite precision {prec}, recall {rec} (tp {tp} fp {fp} fn {fn} tn {tn}), "
          f"exact panel count {exact}/{total}, {1000 * np.mean(times):.0f} ms/card")


def _batch(limit: int | None, method: str | None) -> None:
    """Split every Staatsarchiv card and write crop PhotoRecords to records/crops.jsonl (read by api.py)."""
    src = RECORDS / "staatsarchiv.jsonl"
    out = RECORDS / "crops.jsonl"
    done_file = SPLITS / "split_done.txt"  # every card already processed, composite or not
    ensure(SPLITS)
    done = set(done_file.read_text().split()) if done_file.exists() else set()
    recs = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    todo = [r for r in recs if r.get("image") and r["id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} cards to split ({_method(method)})", flush=True)
    n_comp = 0
    with out.open("a") as f, done_file.open("a") as d:
        for i, r in enumerate(todo, 1):
            parts = split_composite(r["image"]["path"], photo_id=r["id"], method=method)
            if len(parts) >= 2:
                n_comp += 1
                for j, part in enumerate(parts, 1):
                    crop = dict(r, id=f"{r['id']}#{j}", parent_id=r["id"], crop_bbox=part["bbox"],
                                image={"path": str(Path(part["path"]).relative_to(DATA_DIR)),
                                       "width": part["bbox"][2], "height": part["bbox"][3], "sha1": None})
                    f.write(json.dumps(crop, ensure_ascii=False) + "\n")
            d.write(r["id"] + "\n")
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}, {n_comp} composite", flush=True)
    print(f"done: {n_comp} composite of {len(todo)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["eval", "batch", "run"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--method", choices=["cv", "vlm"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "eval":
        _eval(_method(a.method))
    elif a.cmd == "batch":
        _batch(a.limit, a.method)
    else:
        for p in a.paths:
            print(p, split_composite(p, method=a.method))


if __name__ == "__main__":
    main()
