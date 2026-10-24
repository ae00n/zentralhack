"""Image embeddings + FAISS index (CONTRACTS section 1: data/index/<model>.*).

Three models, compared on the archive itself:
- dinov2:  facebook/dinov2-small (CLS token, 384-d). Strong on scene and building structure.
- clip:    open_clip ViT-B-32 (laion2b_s34b_b79k, 512-d). Robust across colour vs black-and-white.
- megaloc: gmberton/MegaLoc via torch.hub (8448-d, 322x322 input, MIT). Trained for visual place
           recognition, i.e. "same place", not "same kind of scene".
Query-only pseudo model "fused": reciprocal rank fusion over every model whose index exists.

    python -m data_pipeline.embed build [--model dinov2|clip|megaloc|all]   # incremental: only new images
    python -m data_pipeline.embed check                             # retrieval check, writes best.json
    python -m data_pipeline.embed query <image> [--k 8]

Vectors are L2-normalised and kept in <model>.npy (row order = <model>.ids.json), so a rebuild
only embeds new images and the FAISS IndexFlatIP (<model>.faiss) is re-created from the matrix.
Runs on CPU (mainframe) or Apple MPS (demo laptop). Load one model at a time: RAM is tight.
"""

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np
from PIL import Image

from .paths import DATA_DIR, INDEX, RECORDS, ensure

MODELS = ("dinov2", "clip", "megaloc")
RRF_K = 60  # reciprocal rank fusion constant (Cormack et al.)
BATCH = int(os.environ.get("EMBED_BATCH", "16"))
SOURCE_PREFIX = {"staatsarchiv": "stasz:", "smapshot": "smapshot:", "epics": "epics:", "lubis": "lubis:", "nb": "nb:",
                 "upload": "upload:", "commons": "commons:", "mapillary": "mapillary:"}


def _device():
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    torch.set_num_threads(min(16, os.cpu_count() or 4))
    return "cpu"


class _Encoder:
    def __init__(self, name: str):
        import torch

        self.torch = torch
        self.name = name
        self.device = _device()
        if name == "dinov2":
            from transformers import AutoImageProcessor, AutoModel

            self.proc = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
            self.model = AutoModel.from_pretrained("facebook/dinov2-small").eval().to(self.device)
        elif name == "clip":
            import open_clip

            self.model, _, self.proc = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k")
            self.model = self.model.eval().to(self.device)
        elif name == "megaloc":
            import torchvision.transforms as tfm

            # trust_repo: torch.hub would otherwise prompt on stdin the first time (hangs headless)
            self.model = torch.hub.load("gmberton/MegaLoc", "get_trained_model", trust_repo=True)
            self.model = self.model.eval().to(self.device)
            self.proc = tfm.Compose([  # as on the model card
                tfm.ToTensor(),
                tfm.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                tfm.Resize(size=[322, 322], antialias=True),
            ])
        else:
            raise ValueError(name)

    def encode(self, images: list[Image.Image]) -> np.ndarray:
        torch = self.torch
        with torch.inference_mode():
            if self.name == "dinov2":
                inp = self.proc(images=images, return_tensors="pt").to(self.device)
                v = self.model(**inp).last_hidden_state[:, 0]
            elif self.name == "megaloc":
                v = self.model(torch.stack([self.proc(im) for im in images]).to(self.device))
            else:
                x = torch.stack([self.proc(im) for im in images]).to(self.device)
                v = self.model.encode_image(x)
        v = v.float().cpu().numpy()
        return v / np.linalg.norm(v, axis=1, keepdims=True).clip(1e-8)


@lru_cache(maxsize=3)
def _encoder(name: str) -> _Encoder:
    # maxsize=3 so model="fused" keeps all three warm (~1.5 GB); build clears the cache per model
    return _Encoder(name)


def _load_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _records() -> list[dict]:
    """Every record with an image: merged records + composite crops (fallback: per-source files)."""
    def read(p: Path):
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    recs = read(RECORDS / "all.jsonl")
    if not recs:
        for src in ("staatsarchiv", "smapshot", "epics"):
            recs += read(RECORDS / f"{src}.jsonl")
    recs += [r for r in read(RECORDS / "crops.jsonl") if "#" in r.get("id", "")]
    seen, out = set(), []
    for r in recs:
        if r.get("image") and r["id"] not in seen and (DATA_DIR / r["image"]["path"]).exists():
            seen.add(r["id"])
            out.append(r)
    return out


def _paths(model: str) -> dict[str, Path]:
    return {k: INDEX / f"{model}.{k}" for k in ("npy", "faiss", "meta.json")} | {"ids": INDEX / f"{model}.ids.json"}


def build(model: str) -> None:
    ensure(INDEX)
    p = _paths(model)
    ids: list[str] = json.loads(p["ids"].read_text()) if p["ids"].exists() else []
    vecs = np.load(p["npy"]) if p["npy"].exists() else None
    have = set(ids)
    todo = [r for r in _records() if r["id"] not in have]
    print(f"{model}: {len(ids)} indexed, {len(todo)} new", flush=True)
    if todo:
        enc = _encoder(model)
        t0 = time.perf_counter()
        new_ids, chunks = [], []
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            ims, ok = [], []
            for r in batch:
                try:
                    ims.append(_load_image(DATA_DIR / r["image"]["path"]))
                    ok.append(r["id"])
                except Exception as e:  # unreadable file: skip, it gets retried next build
                    print(f"  skip {r['id']}: {e}", flush=True)
            if ims:
                chunks.append(enc.encode(ims))
                new_ids += ok
            if (i // BATCH) % 20 == 0:
                rate = (i + len(batch)) / (time.perf_counter() - t0)
                print(f"  {i + len(batch)}/{len(todo)} ({rate:.1f} img/s)", flush=True)
            # checkpoint every ~1000 images so an interrupted build keeps its work
            if len(new_ids) >= 1000 or i + BATCH >= len(todo):
                if chunks:
                    block = np.concatenate(chunks).astype(np.float32)
                    vecs = block if vecs is None else np.concatenate([vecs, block])
                    ids += new_ids
                    np.save(p["npy"], vecs)
                    p["ids"].write_text(json.dumps(ids))
                new_ids, chunks = [], []
    if vecs is None:
        print(f"{model}: nothing to index")
        return
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(p["faiss"]))
    p["meta.json"].write_text(json.dumps({
        "model": model, "dim": int(vecs.shape[1]), "n": len(ids),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }))
    _index.cache_clear()
    print(f"{model}: index has {len(ids)} vectors -> {p['faiss']}")


# ---------- query side (also used on the demo laptop) ----------

def best_model() -> str:
    f = INDEX / "best.json"
    return json.loads(f.read_text())["model"] if f.exists() else "dinov2"


def available_models() -> list[str]:
    """Models whose FAISS index is on disk (the members of "fused")."""
    return [m for m in MODELS if _paths(m)["faiss"].exists()]


@lru_cache(maxsize=3)
def _index(model: str):
    p = _paths(model)
    return faiss.read_index(str(p["faiss"])), json.loads(p["ids"].read_text())


def _base(pid: str) -> str:
    return pid.split("#", 1)[0]


def search_vector(vec: np.ndarray, k: int = 8, model: str = "best", exclude_ids=(), sources=None
                  ) -> list[tuple[str, float]]:
    model = best_model() if model == "best" else model
    index, ids = _index(model)
    excl = {_base(e) for e in exclude_ids}
    prefixes = tuple(SOURCE_PREFIX[s] for s in sources) if sources else None
    want = k
    while True:
        n = min(len(ids), want * 4 + len(excl) + 8)
        scores, rows = index.search(vec.reshape(1, -1).astype(np.float32), n)
        out = []
        for s, r in zip(scores[0], rows[0]):
            if r < 0:
                continue
            pid = ids[r]
            if _base(pid) in excl or (prefixes and not pid.startswith(prefixes)):
                continue
            out.append((pid, float(s)))
            if len(out) == k:
                return out
        if n >= len(ids):
            return out
        want *= 4


def fuse(rankings: list[list[str]], k: int) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(id) = sum over rankings of 1 / (RRF_K + rank), rank from 1."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, 1):
            score[pid] = score.get(pid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(score.items(), key=lambda x: -x[1])[:k]


def search_fused(vecs: dict[str, np.ndarray], k: int = 8, exclude_ids=(), sources=None
                 ) -> list[tuple[str, float]]:
    """RRF over per-model searches. vecs: {model: query vector}. Each model contributes its top
    max(50, 5k), so an id ranked well by one model alone can still make the list."""
    depth = max(50, 5 * k)
    rankings = [[pid for pid, _ in search_vector(v, depth, m, exclude_ids, sources)] for m, v in vecs.items()]
    return fuse(rankings, k)


def search(image_path: str, k: int = 8, model: str = "best", exclude_ids=(), sources=None
           ) -> list[tuple[str, float]]:
    """[(photo_id, score)] best first. exclude_ids also drops crops of those cards (eval leakage).

    score is the cosine similarity, or for model="fused" the RRF score (max 3/61 ~ 0.049).
    """
    p = Path(image_path)
    if not p.exists() and not p.is_absolute():
        p = DATA_DIR / image_path
    im = _load_image(p)
    if model == "fused":
        models = available_models()
        if len(models) == 1:  # nothing to fuse
            return search_vector(_encoder(models[0]).encode([im])[0], k, models[0], exclude_ids, sources)
        # _encoder keeps one model in RAM at a time, so this loads each in turn (slow on first call
        # per model switch; callers that care hold their own vectors and use search_fused)
        return search_fused({m: _encoder(m).encode([im])[0] for m in models}, k, exclude_ids, sources)
    model = best_model() if model == "best" else model
    vec = _encoder(model).encode([im])[0]
    return search_vector(vec, k, model, exclude_ids, sources)


similar = search  # name used in the scope doc


# ---------- retrieval check ----------

def check() -> dict:
    """Leave-one-out: for each Staatsarchiv card with a known municipality, search the rest
    (other cards + reference photos, never the card itself or its crops) and compare the
    municipality of the top hits. Picks the better model into best.json."""
    recs = {r["id"]: r for r in _records()}
    results = {}
    for model in MODELS:
        p = _paths(model)
        if not p["npy"].exists():
            continue
        vecs = np.load(p["npy"])
        ids = json.loads(p["ids"].read_text())
        row = {pid: i for i, pid in enumerate(ids)}
        queries = [pid for pid in ids if pid.startswith("stasz:") and "#" not in pid
                   and recs.get(pid, {}).get("municipality")]
        top1 = vote5 = any5 = 0
        for q in queries:
            hits = search_vector(vecs[row[q]], 5, model, exclude_ids=[q])
            munis = [recs[h]["municipality"] for h, _ in hits if recs.get(h, {}).get("municipality")]
            truth = recs[q]["municipality"]
            top1 += bool(munis) and munis[0] == truth
            any5 += truth in munis
            vote5 += bool(munis) and Counter(munis).most_common(1)[0][0] == truth
        n = len(queries)
        results[model] = {"n": n, "top1": round(top1 / n, 3) if n else None,
                          "vote5": round(vote5 / n, 3) if n else None,
                          "any5": round(any5 / n, 3) if n else None, "index_size": len(ids)}
        print(f"{model}: {results[model]}")
    if results:
        best = max(results, key=lambda m: (results[m]["vote5"] or 0, results[m]["top1"] or 0))
        (INDEX / "best.json").write_text(json.dumps({"model": best, "check": results,
                                                     "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=1))
        print(f"best: {best}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "check", "query"])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--model", default="all", help="dinov2|clip|megaloc|all (query: also fused|best)")
    ap.add_argument("--k", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "build":
        for m in (MODELS if a.model == "all" else (a.model,)):
            build(m)
            _encoder.cache_clear()
    elif a.cmd == "check":
        check()
    else:
        for pid, s in search(a.image, a.k, "best" if a.model == "all" else a.model):
            print(f"{s:.3f}  {pid}")


if __name__ == "__main__":
    main()
