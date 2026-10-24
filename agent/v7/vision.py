"""Google Cloud Vision web detection: web pages and entities that show the same scene.

The photo goes to Google (no training on it, not stored on disk per Google's data usage terms; agreed by
the team on 24 Oct). Results are cached in data/v7/vision/<photo>.json, so each photo is sent once.
Without GOOGLE_VISION_KEY this returns None and the pipeline runs without web hints.
"""

import base64
import json
import os

import httpx

from .common import V7_DIR, jpeg

URL = "https://vision.googleapis.com/v1/images:annotate"
CACHE = V7_DIR / "vision"


def detect(photo_id: str, path) -> dict | None:
    """{entities: [{name, score}], labels: [str], pages: [{title, url}], full_matches: [url]} or None."""
    p = CACHE / f"{photo_id.replace(':', '_')}.json"
    if p.exists():
        return json.loads(p.read_text())
    k = os.environ.get("GOOGLE_VISION_KEY")
    if not k:
        return None
    body = {"requests": [{"image": {"content": base64.b64encode(jpeg(path, 1600, 90)).decode()},
                          "features": [{"type": "WEB_DETECTION", "maxResults": 20}],
                          "imageContext": {"webDetectionParams": {"includeGeoResults": True}}}]}
    r = httpx.post(URL, params={"key": k}, json=body, timeout=60)
    r.raise_for_status()
    w = (r.json().get("responses") or [{}])[0].get("webDetection") or {}
    out = {
        "entities": [{"name": e["description"], "score": round(e.get("score", 0), 3)}
                     for e in w.get("webEntities", []) if e.get("description")],
        "labels": [b["label"] for b in w.get("bestGuessLabels", []) if b.get("label")],
        "pages": [{"title": _clean(pg.get("pageTitle")), "url": pg.get("url"),
                   "full": bool(pg.get("fullMatchingImages"))} for pg in w.get("pagesWithMatchingImages", [])][:12],
        "full_matches": [m["url"] for m in w.get("fullMatchingImages", [])][:5],
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False))
    return out


def _clean(t: str | None) -> str | None:
    import re
    return re.sub(r"<[^>]+>", "", t).strip() if t else None


def summary(v: dict | None) -> str:
    """German text block for the prompt, or '' when there is nothing."""
    if not v or not v["pages"]:  # labels alone ("snow", "house") say nothing about the place
        return ""
    lines = ["Websuche nach dem Bild (Google, Seiten mit ähnlichen oder gleichen Bildern; kann danebenliegen):"]
    if v["labels"]:
        lines.append("Beste Vermutung: " + ", ".join(v["labels"]))
    if v["entities"]:
        lines.append("Begriffe: " + ", ".join(f"{e['name']} ({e['score']})" for e in v["entities"][:12]))
    for pg in v["pages"][:8]:
        if pg["title"]:
            lines.append(f"- {'gleiches Bild: ' if pg['full'] else ''}{pg['title']} ({pg['url']})")
    return "\n".join(lines)
