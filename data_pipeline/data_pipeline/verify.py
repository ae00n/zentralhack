"""Geometric verification: does a candidate show the same place as the query?

Global embeddings (embed.py) find look-alikes; local feature matching checks them. ALIKED keypoints
(BSD-3; SuperPoint is avoided for its non-commercial licence) + LightGlue matcher (Apache-2.0), then
cv2 RANSAC on a fundamental matrix. The inlier count is the signal: two photos of the same spot
share many geometrically consistent matches, a merely similar lake-and-mountains scene does not.

    python -m data_pipeline.verify <query> <candidate> [<candidate> ...]

Images are resized to max 1024 px (long edge). CPU only is fine: about 1 s per pair, see
INLIER_THRESHOLD for how the threshold was picked.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .paths import DATA_DIR

MAX_SIDE = 1024
MAX_KEYPOINTS = 2048
# Picked on (a) 20 same-place pairs (Smapshot/E-Pics poses within 150 m, azimuth within 30 degrees)
# vs 20 random different-place pairs: same 11 to 821 inliers (median ~140), different 0 to 20; and
# (b) the fused top 10 of 45 archive cards, where look-alike neighbours are much harder: hits with
# >= 30 inliers share the card's municipality 84% of the time, >= 50: 96%, >= 150: 99%.
INLIER_THRESHOLD = int(os.environ.get("VERIFY_INLIERS", "50"))


def _resolve(path) -> Path:
    p = Path(path)
    return p if p.exists() or p.is_absolute() else DATA_DIR / p


@lru_cache(maxsize=1)
def _models():
    import torch
    from lightglue import ALIKED, LightGlue

    torch.set_num_threads(min(8, os.cpu_count() or 4))
    extractor = ALIKED(max_num_keypoints=MAX_KEYPOINTS).eval()
    matcher = LightGlue(features="aliked").eval()
    return extractor, matcher


@lru_cache(maxsize=64)
def _features(path: str) -> dict:
    """Keypoints + descriptors for one image (cached: the query is reused for every candidate)."""
    import torch
    from lightglue.utils import numpy_image_to_torch
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)  # downscale only, keeps aspect
    extractor, _ = _models()
    with torch.inference_mode():
        return extractor.extract(numpy_image_to_torch(np.asarray(im)))


def _match(f0: dict, f1: dict) -> tuple[np.ndarray, np.ndarray]:
    import torch
    from lightglue.utils import rbd

    _, matcher = _models()
    with torch.inference_mode():
        out = rbd(matcher({"image0": f0, "image1": f1}))
    m = out["matches"].numpy()
    k0, k1 = rbd(f0)["keypoints"].numpy(), rbd(f1)["keypoints"].numpy()
    return k0[m[:, 0]], k1[m[:, 1]]


def _inliers(p0: np.ndarray, p1: np.ndarray) -> int:
    if len(p0) < 8:
        return 0
    _, mask = cv2.findFundamentalMat(p0, p1, cv2.USAC_MAGSAC, 3.0, 0.999, 10000)
    return int(mask.sum()) if mask is not None else 0


def verify(query_path, candidate_paths) -> list[dict]:
    """[{path, matches, inliers, verified}] in candidate order. An unreadable candidate gets
    matches = inliers = 0 and verified False (never raises for one bad file)."""
    q = _features(str(_resolve(query_path)))
    out = []
    for cp in candidate_paths:
        try:
            p0, p1 = _match(q, _features(str(_resolve(cp))))
            n, inl = len(p0), _inliers(p0, p1)
        except Exception as e:  # missing or corrupt file
            print(f"verify: skip {cp}: {e}", file=sys.stderr)
            n = inl = 0
        out.append({"path": str(cp), "matches": n, "inliers": inl, "verified": inl >= INLIER_THRESHOLD})
    return out


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    for r in verify(sys.argv[1], sys.argv[2:]):
        print(f"{r['inliers']:4d}/{r['matches']:4d}  {'OK ' if r['verified'] else '   '} {r['path']}")


if __name__ == "__main__":
    main()
