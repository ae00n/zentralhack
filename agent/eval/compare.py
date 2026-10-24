"""Side by side: v3 results (data/results) vs v5 results (data/results_v5) for the challenge photos.

No ground truth: agreement between two independent methods is the signal. Where both name the same
Gemeinde the answer is likely right; where they differ, a person looks first.

    python -m agent.eval.compare [--priority 1]
"""

import argparse
import json

import data_pipeline as dp

from ..config import DATA_DIR


def _load(d: str) -> dict[str, dict]:
    out = {}
    for p in (DATA_DIR / d).glob("challenge:*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        out[r["photo_id"]] = r
    return out


def _v(r: dict | None, field: str):
    return (((r or {}).get("fields") or {}).get(field) or {}).get("value")


def _same(a, b) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--priority", type=int)
    a = ap.parse_args()
    v3, v5 = _load("results"), _load("results_v5")
    ids = sorted(set(v3) | set(v5), key=lambda i: int(i.rsplit(".", 1)[1]))
    if a.priority:
        ids = [i for i in ids if ((dp.get_record(i) or {}).get("raw") or {}).get("priority") == a.priority]
    both = agree = 0
    print(f"{'photo':24} {'v3 Ortschaft / Gemeinde (conf)':42} {'v5 Ortschaft / Gemeinde (conf, path)':50}")
    for i in ids:
        r3, r5 = v3.get(i), v5.get(i)
        s3 = f"{_v(r3, 'locality') or '-'} / {_v(r3, 'municipality') or '-'} ({(r3 or {}).get('overall_confidence', 0):.2f})" if r3 else ""
        s5 = (f"{_v(r5, 'locality') or '-'} / {_v(r5, 'municipality') or '-'} ({(r5 or {}).get('overall_confidence', 0):.2f}, "
              f"{((r5 or {}).get('settings') or {}).get('path')})") if r5 else ""
        mark = ""
        if r3 and r5 and _v(r3, "municipality") and _v(r5, "municipality"):
            both += 1
            if _same(_v(r3, "municipality"), _v(r5, "municipality")):
                agree += 1
                mark = "="
            else:
                mark = "!"
        print(f"{i.split(':')[1]:24} {s3:42} {s5:50} {mark}")
    paths: dict[str, int] = {}
    for i in ids:
        p = ((v5.get(i) or {}).get("settings") or {}).get("path")
        if i in v5:
            paths[str(p)] = paths.get(str(p), 0) + 1
    cost = sum(((v5.get(i) or {}).get("usage") or {}).get("cost_usd", 0) for i in ids)
    print(f"\n{len(ids)} photos, v3 {sum(i in v3 for i in ids)}, v5 {sum(i in v5 for i in ids)}; "
          f"both name a Gemeinde: {both}, same Gemeinde: {agree}")
    print(f"v5 paths: {paths}; v5 cost {cost:.2f} USD")


if __name__ == "__main__":
    main()
