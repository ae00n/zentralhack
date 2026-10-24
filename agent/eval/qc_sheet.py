"""Hand check of the Prio-1 photos: a small page that writes data/splits/challenge_qc.jsonl.

    python -m agent.eval.qc_sheet [--port 8012]     # then https://zhfront.vatra.sh/qc/ (tailnet only)

Per photo: the photo, what v7, v6, v5 and v3 answered (each with Google Maps / Street View links at its point),
and four fields to fill: Ortschaft, Gemeinde, Gebäude, Strasse. "übernehmen" copies a suggestion into the
fields; the checker confirms it on the map before saving. An empty field means "could not tell" and is
skipped by the scorer (data_pipeline.metrics.score_challenge), never counted as wrong.

The photos are Staatsarchiv images without an open licence: this binds to 127.0.0.1 and is reached only
through the tailnet-only gateway vhost, never published anywhere.
"""

import argparse
import html
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from data_pipeline.jsonl import read_jsonl, write_jsonl
from data_pipeline.paths import DATA_DIR, RECORDS
from data_pipeline.qc import QC_FILE, clean_row

VERSIONS = {"v7": DATA_DIR / "results_v7", "v6": DATA_DIR / "results_v6", "v5": DATA_DIR / "results_v5", "v3": DATA_DIR / "results_v3"}
FIELDS = [("locality", "Ortschaft"), ("municipality", "Gemeinde"), ("buildings", "Gebäude"), ("street", "Strasse")]
ID = re.compile(r"^challenge:SG\.CIV\.17\.\d+$")


def _prio1() -> list[dict]:
    recs = [r for r in read_jsonl(RECORDS / "challenge.jsonl") if (r.get("raw") or {}).get("priority") == 1]
    return sorted(recs, key=lambda r: int(r["source_id"].rsplit(".", 1)[1]))


def _answers(pid: str) -> dict:
    out = {}
    for v, d in VERSIONS.items():
        p = d / f"{pid}.json"
        if not p.exists():
            continue
        f = json.loads(p.read_text(encoding="utf-8")).get("fields") or {}
        val = {k: (f.get(k) or {}).get("value") for k, _ in FIELDS}
        val["buildings"] = "; ".join(val["buildings"] or [])
        c = (f.get("coordinates") or {}).get("value")
        out[v] = val | {"lat": c["lat"], "lon": c["lon"]} if c else val
    return out


def _checked() -> dict:
    return {r["id"]: r for r in read_jsonl(QC_FILE)} if QC_FILE.exists() else {}


def page() -> str:
    done = _checked()
    cards = []
    for r in _prio1():
        pid, sig = r["id"], r["source_id"]
        ans, row = _answers(pid), done.get(pid) or {}
        sugg = []
        for v, a in ans.items():
            vals = " · ".join(html.escape(str(a[k])) for k, _ in FIELDS if a.get(k)) or "keine Antwort"
            links = ""
            if a.get("lat"):
                ll = f"{a['lat']},{a['lon']}"
                links = (f' <a href="https://www.google.com/maps/search/?api=1&query={ll}" target="_blank">Karte</a>'
                         f' <a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={ll}" target="_blank">Street View</a>')
            data = html.escape(json.dumps({k: a.get(k) or "" for k, _ in FIELDS}, ensure_ascii=False))
            sugg.append(f'<div class="s"><span class="v">{v}</span> {vals}{links} '
                        f'<button type="button" data-fill="{data}">übernehmen</button></div>')
        inputs = "".join(
            f'<label>{lab}<input name="{k}" value="{html.escape("; ".join(row[k]) if k == "buildings" and row.get(k) else (row.get(k) or ""))}"'
            f'{" list=gem" if k == "municipality" else ""}></label>' for k, lab in FIELDS)
        status = "geprüft" if pid in done else "offen"
        cards.append(f"""<form class="card{' done' if pid in done else ''}" data-id="{pid}">
<img loading="lazy" src="img/{sig}" alt="{sig}">
<div class="body"><div class="t">{sig} <span class="meta">· {html.escape(r['date'].get('raw') or '')} · <b class="st">{status}</b></span></div>
{''.join(sugg)}<div class="f">{inputs}<label>Notiz<input name="note" value="{html.escape(row.get('note') or '')}"></label></div>
<button type="submit">Speichern</button></div></form>""")
    gem = "".join(f"<option value=\"{html.escape(g['name'])}\">" for g in json.loads((DATA_DIR / "gazetteer" / "gemeinden.json").read_text()))
    return TEMPLATE.replace("{cards}", "\n".join(cards)).replace("{gem}", gem).replace(
        "{n}", str(len(done))).replace("{total}", str(len(_prio1())))


TEMPLATE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Handprüfung Prio 1</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--line:#e7e5e4;--card:#fff;--ok:#15803d}
@media (prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#e7e5e4;--mut:#a8a29e;--line:#292524;--card:#1c1917;--ok:#4ade80}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
header{padding:16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:1}
h1{font-size:17px;margin:0}.meta{color:var(--mut);font-size:13px}
main{max-width:1100px;margin:0 auto;padding:16px;display:grid;gap:16px}
.card{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card.done{opacity:.6}.card img{width:100%;border-radius:4px}
.t{font-weight:600;margin-bottom:6px}.s{font-size:13px;margin:4px 0}.v{color:var(--mut);display:inline-block;width:22px}
.s a{color:var(--mut);margin-left:6px}.st{font-weight:500}.done .st{color:var(--ok)}
.f{display:grid;gap:6px;margin:10px 0}label{display:grid;font-size:12px;color:var(--mut)}
input{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
button{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg);cursor:pointer}
button[type=submit]{background:var(--fg);color:var(--bg)}
@media (max-width:720px){.card{grid-template-columns:1fr}}
</style></head><body><header><h1>Handprüfung Prio 1</h1>
<div class="meta"><span id="n">{n}</span> von {total} geprüft · leer lassen, wenn nicht feststellbar · Vorschläge erst auf der Karte prüfen</div></header>
<main>{cards}</main><datalist id="gem">{gem}</datalist>
<script>
document.addEventListener('click',e=>{const d=e.target.dataset.fill;if(!d)return;const f=e.target.closest('form');
const v=JSON.parse(d);for(const k in v){f.elements[k].value=v[k]}});
document.addEventListener('submit',async e=>{e.preventDefault();const f=e.target;const body={id:f.dataset.id};
for(const i of f.querySelectorAll('input'))body[i.name]=i.value;
const r=await fetch('save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const j=await r.json();const st=f.querySelector('.st');
if(r.ok){f.classList.add('done');st.textContent=j.problems.length?'geprüft, prüfen: '+j.problems.join('; '):'geprüft';document.getElementById('n').textContent=j.n}
else st.textContent='Fehler: '+j.error});
</script></body></html>"""


def save(body: dict) -> dict:
    row, problems = clean_row(body, {r["id"] for r in _prio1()})
    if row is None:
        raise ValueError("; ".join(problems))
    row["checked_by"] = "Dijar"
    rows = _checked()
    rows[row["id"]] = row
    write_jsonl(QC_FILE, sorted(rows.values(), key=lambda r: int(r["id"].rsplit(".", 1)[1])))
    return {"n": len(rows), "problems": problems}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0].lstrip("/")
        if path in ("", "index.html"):
            return self._send(200, page().encode(), "text/html; charset=utf-8")
        m = re.fullmatch(r"img/(SG\.CIV\.17\.\d+)", path)
        f = DATA_DIR / "images" / "challenge" / f"{m.group(1)}.jpg" if m else None
        if f and f.exists():
            return self._send(200, f.read_bytes(), "image/jpeg")
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path.split("?", 1)[0].lstrip("/") != "save":
            return self._send(404, b"not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if not ID.match(body.get("id") or ""):
                raise ValueError("unknown photo id")
            out, code = save(body), 200
        except Exception as e:  # shown next to the save button
            out, code = {"error": str(e)}, 400
        self._send(code, json.dumps(out, ensure_ascii=False).encode(), "application/json")

    def log_message(self, *a):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8012)
    a = ap.parse_args()
    print(f"hand check on http://127.0.0.1:{a.port}/ -> {QC_FILE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
