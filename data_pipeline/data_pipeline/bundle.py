"""Offline bundle for the demo laptop (docs/ARCHITECTURE.md section 7).

    python -m data_pipeline.bundle [--out ~/zh-bundle]

Writes one uncompressed tar (images and tiles do not compress) with:
- data/   everything except raw/ and logs/: records, images, all indexes, splits, gazetteer, tiles.
          The full index stays in, so any card (not only the demo ones) still works offline.
- cache/  the model weights: Hugging Face (CLIP, DINOv2, MegaLoc) and torch hub (MegaLoc code,
          ALIKED + LightGlue), so nothing is downloaded on first use.
- README.txt with the environment variables.

The bundle holds Staatsarchiv images (no open licence): copy it only over a private path
(USB stick, Taildrop), never to a public upload. It is written outside the repo.
"""

import argparse
import subprocess
from pathlib import Path

from .paths import DATA_DIR

HOME = Path.home()
HF_HUB = HOME / ".cache" / "huggingface" / "hub"
TORCH_HUB = HOME / ".cache" / "torch" / "hub"
HF_MODELS = ["models--facebook--dinov2-small", "models--gberton--MegaLoc",
             "models--laion--CLIP-ViT-B-32-laion2B-s34B-b79K"]

README = """Zentral Hack 2026: offline data bundle (private, contains Staatsarchiv Schwyz images)

1. tar -xf zh-data.tar -C <dir>
2. In the shell that runs the backend:
     export ZH_DATA_DIR=<dir>/data
     export HF_HOME=<dir>/cache/huggingface
     export TORCH_HOME=<dir>/cache/torch
     export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
3. Check: python -c "from data_pipeline import get_record; print(get_record('stasz:359891')['title'])"

Map tiles: data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>; data/tiles/manifest.json lists the cached
zeitreihen times (map_years), zooms and areas.
"""


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "README.txt").write_text(README)
    tar = out / "zh-data.tar"
    cache_hf = [f"huggingface/hub/{m}" for m in HF_MODELS if (HF_HUB / m).exists()]
    blobs = sorted({p.resolve().relative_to(HF_HUB.parent.parent) for m in HF_MODELS
                    for p in (HF_HUB / m).rglob("*") if p.is_symlink()})
    cmd = ["tar", "-cf", str(tar),
           "--exclude=data/raw", "--exclude=data/logs", "--exclude=data/tiles/.caps",
           "-C", str(DATA_DIR.parent), DATA_DIR.name,
           "-C", str(out), "README.txt",
           "--transform", r"s,^huggingface/,cache/huggingface/,;s,^torch/,cache/torch/,",
           "-C", str(HF_HUB.parent.parent), *cache_hf, *map(str, blobs),
           "-C", str(TORCH_HUB.parent.parent), "torch/hub/checkpoints", "torch/hub/gmberton_MegaLoc_main",
           "torch/hub/trusted_list"]
    subprocess.run(cmd, check=True)
    size = tar.stat().st_size / 1e9
    print(f"{tar}: {size:.1f} GB")
    return tar


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HOME / "zh-bundle")
    build(ap.parse_args().out)


if __name__ == "__main__":
    main()
