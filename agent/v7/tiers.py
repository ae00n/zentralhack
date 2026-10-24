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
from .check import PASS_INLIERS
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


def monotone(cells: dict) -> dict:
    """Shown rate per tier, (hits + 1) / (n + 2), never below the next weaker tier's. A tier's conditions
    include the weaker tier's, so when its own small sample comes out lower (A 11/11 = 0.923 against
    B 24/24 = 0.962) it is pooled with the weaker tier: A = (11 + 24 + 1) / (11 + 24 + 2) = 0.973."""
    out: dict = {}
    prev = None  # the next weaker tier: its shown rate and the sample behind it
    for t in ("C", "B", "A"):
        c = cells.get(t)
        if not c or not c.get("n"):
            continue
        n, hits = c["n"], c["hits"]
        if prev and (hits + 1) / (n + 2) < prev["rate"]:
            n, hits = n + prev["n"], hits + prev["hits"]
        prev = {"n": n, "hits": hits, "rate": (hits + 1) / (n + 2)}
        out[t] = {"n": c["n"], "hits": c["hits"], "rate": round(prev["rate"], 3)}
    return out


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


FIELD_DE = {"locality": "Ortschaft", "municipality": "Gemeinde", "buildings": "Gebäude",
            "landscape_features": "See/Fluss/Berg", "street": "Strasse"}


def explain(t: str, facts: dict, fields: dict, anchor: str | None, inliers: int | None, conf: float,
            measured: bool, upload: bool = False) -> str:
    """One German sentence per photo: which independent checks agree, how the number was measured, what
    stays open. "Stufe B, 96 %: 3 von 3 Untersuchungen nennen Schwyz, Gebäude im amtlichen Register;
    Bildvergleich vor Ort nicht eindeutig (19 Punkte). Gemessen: 24 von 24 Stufe-B-Fotos richtig."""
    if t == "-" or not facts:
        return "Kein belastbarer Hinweis auf den Ort: alle Felder offen gelassen."
    gemeinde = fields.get("municipality", {}).get("value") or "dieselbe Gemeinde"
    yes, no = [], []
    if facts.get("agree"):
        yes.append(f"{facts['agree']} von 3 Untersuchungen {'nennt' if facts['agree'] == 1 else 'nennen'} {gemeinde}")
    if facts.get("register"):
        named = anchor == "building" and fields.get("buildings", {}).get("value")
        yes.append("Gebäude im amtlichen Register" if named else "Adresse im amtlichen Register")
    else:
        no.append("kein Registereintrag am Ort")
    if facts.get("image"):
        yes.append(f"Bildvergleich vor Ort bestätigt ({inliers} Punkte)" if inliers else "Bildvergleich vor Ort bestätigt")
    elif inliers:
        no.append(f"Bildvergleich vor Ort unter der Schwelle ({inliers} von {PASS_INLIERS} Punkten)")
    else:
        no.append("kein Vergleichsfoto vor Ort")
    s = f"Stufe {t}, {round(conf * 100)} %: {', '.join(yes) or 'nur Claudes Einschätzung des Bildes'}"
    if no:
        s += f"; {', '.join(no)}"
    cell = table().get(t) or {}
    if measured and upload:
        s += f". Gemessen auf den Prio-1-Fotos ({cell.get('hits')} von {cell.get('n')} Stufe-{t}-Fotos richtig), für hochgeladene Fotos nicht eigens"
    elif measured:
        s += f". Gemessen: {cell.get('hits')} von {cell.get('n')} Stufe-{t}-Fotos von Hand bestätigt"
    else:
        s += ". Schätzwert, noch nicht gemessen"
    empty = [de for k, de in FIELD_DE.items() if fields.get(k, {}).get("value") in (None, [], "")]
    return s + (f". Offen: {', '.join(empty)}." if empty else ".")


def value(t: str) -> tuple[float, bool]:
    """(confidence, measured)."""
    cell = table().get(t)
    if cell and cell.get("n", 0) >= 5:
        return cell["rate"], True
    return PRIORS[t], False
