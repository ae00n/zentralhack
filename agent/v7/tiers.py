"""Confidence by rule. A tier says which independent checks agree; its shown number is the hit rate the
hand check measured for it (agent/v7_tiers.json, written by `python -m agent.v7.score --fit`), else a prior.

  A  the image check passes at the chosen place, the place is a register building or address,
     and at least 2 of the 3 attempts name its Gemeinde
  B  two of: image check passes / register building or address / 2+ attempts agree
  C  one source only (usually Claude alone)
  -  no Gemeinde: fields stay empty
"""

import json

from ..config import REPO_ROOT
from .common import gem

TABLE = REPO_ROOT / "agent" / "v7_tiers.json"
PRIORS = {"A": 0.95, "B": 0.8, "C": 0.5, "-": 0.0}
WHY = {
    "A": "Bildvergleich vor Ort bestätigt, Gebäude bzw. Adresse im amtlichen Register, und mindestens zwei von drei "
         "unabhängigen Untersuchungen nennen dieselbe Gemeinde",
    "B": "Zwei unabhängige Belege stimmen überein",
    "C": "Nur ein Beleg, meist Claudes Einschätzung des Bildes",
    "-": "Kein belastbarer Hinweis auf den Ort: offen gelassen",
}


def table() -> dict:
    return json.loads(TABLE.read_text()) if TABLE.exists() else {}


def tier(chosen: dict | None, answers: list[dict], judge_pick: dict | None) -> tuple[str, dict]:
    """(tier, facts) for the chosen candidate; answers = the attempts' raw answers."""
    if not chosen or not chosen.get("municipality"):
        return "-", {}
    agree = sum(1 for a in answers if a and gem(a.get("municipality")) == gem(chosen["municipality"]))
    reg = chosen["anchor"] in ("building", "address")
    image_ok = bool((chosen.get("check") or {}).get("pass"))
    sure = (judge_pick or {}).get("certainty") != "vermutet"
    facts = {"agree": agree, "register": reg, "image": image_ok, "judge_sure": sure}
    if image_ok and reg and agree >= 2 and sure:
        return "A", facts
    if sum([image_ok, reg, agree >= 2]) >= 2:
        return "B", facts
    return "C", facts


def value(t: str) -> tuple[float, bool]:
    """(confidence, measured)."""
    cell = table().get(t)
    if cell and cell.get("n", 0) >= 5:
        return cell["rate"], True
    return PRIORS[t], False
