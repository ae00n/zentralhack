"""Apply the current confidence table, sentence and name rules to the stored v7 results, without new Claude calls.

    python -m agent.v7.rescore --dry-run    # print what would change
    python -m agent.v7.rescore              # rewrite data/results/*.json in place

Everything needed is in each result already (settings.tier, settings.facts, settings.candidates), so this
redoes only the last step of pipeline.result: field confidences from the tier's rate, needs_review, the
per-photo sentence (tiers.explain), the final trace line, and a building that is only a type word ("Kirche")
left empty. A review stays as it is.
"""

import argparse
import json
import re

from .. import fields as submit
from ..config import DATA_DIR
from . import tiers
from .common import dist_m, generic_name
from .pipeline import ACCEPT

RESULTS = DATA_DIR / "results"


def chosen_candidate(r: dict) -> dict | None:
    c = (r["fields"].get("coordinates") or {}).get("value")
    if not c:
        return None
    near = [x for x in (r.get("settings") or {}).get("candidates") or []
            if x.get("lat") is not None and dist_m(x, c) < 5]
    return near[0] if near else None


def rescore(r: dict) -> list[str]:
    """Update r in place; return what changed."""
    s = r.get("settings") or {}
    t, facts = s.get("tier"), s.get("facts") or {}
    if s.get("pipeline") != 7 or t is None:
        return []
    changes = []
    f = r["fields"]
    chosen = chosen_candidate(r)
    if t != "-":
        b = f.get("buildings") or {}
        if b.get("value") and all(generic_name(x) for x in b["value"]):
            changes.append(f"Gebäude {b['value']} entfernt (nur Gattung)")
            f["buildings"] = submit.empty_fields()["buildings"]
        conf, measured = tiers.value(t)
        reg = bool(facts.get("register"))
        rule = {"municipality": conf, "locality": conf, "coordinates": conf,
                "buildings": conf if reg else min(conf, 0.5), "street": conf if reg else min(conf, 0.4),
                "landscape_features": min(conf, 0.8)}
        for name, c in rule.items():
            cell = f.get(name)
            if cell and cell.get("value") not in (None, [], "") and cell.get("confidence") != round(c, 3):
                changes.append(f"{name} {cell.get('confidence')} -> {round(c, 3)}")
                cell["confidence"] = round(c, 3)
        overall = f["municipality"]["confidence"] if f["municipality"]["value"] else 0.0
        if r.get("overall_confidence") != round(overall, 3):
            r["overall_confidence"] = round(overall, 3)
        needs = overall < ACCEPT or not f["municipality"]["value"]
        if needs != r.get("needs_review"):
            changes.append(f"needs_review {r.get('needs_review')} -> {needs}")
        r["needs_review"] = needs
        if not r.get("review"):
            r["status"] = "needs_review" if needs else "done"
    else:
        conf, measured = 0.0, False
    old = r.get("confidence_explanation") or ""
    if not old.startswith("Nicht im Kanton"):
        new = tiers.explain(t, facts, f, (chosen or {}).get("anchor"), (chosen or {}).get("inliers"), conf, measured,
                            upload=r["photo_id"].startswith("upload:"))
        if new != old:
            r["confidence_explanation"] = new
            changes.append("Begründung neu")
    for item in r.get("trace") or []:
        if item.get("type") == "final":
            item["text"] = re.sub(r"Konfidenz [\d.]+", f"Konfidenz {r['overall_confidence']:.2f}", item.get("text") or "")
    return changes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    n = 0
    for p in sorted(RESULTS.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(r, dict) or "fields" not in r:
            continue
        ch = rescore(r)
        if not ch:
            continue
        n += 1
        print(f"{r['photo_id']}: {'; '.join(ch)}")
        if not a.dry_run:
            p.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n} results {'would change' if a.dry_run else 'rewritten'}")


if __name__ == "__main__":
    main()
