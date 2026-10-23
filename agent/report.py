"""CLI: a local HTML report of the cached results, with every earlier run of each photo.

    python -m agent.report [--split challenge] [--priority 1] [--ids a,b] [--watch 20]

Writes agent/.cache/report.html (gitignored) and prints its path. Images are linked from the local data
folder, never embedded or uploaded: the Staatsarchiv photos are not openly licensed, so the file is for
this laptop only. With --watch N it rewrites the file every N seconds and the page reloads itself, so a
running batch can be followed live.
"""

import argparse
import html
import sys
import time
from pathlib import Path

from . import config, consistency, results

OUT = config.CACHE_DIR / "report.html"
FIELDS = [("locality", "Ortschaft"), ("municipality", "Gemeinde"), ("buildings", "Gebäude"),
          ("landscape_features", "See/Fluss/Berg"), ("street", "Strasse")]


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _val(r: dict, name: str) -> str | None:
    v = ((r.get("fields") or {}).get(name) or {}).get("value")
    if isinstance(v, list):
        return ", ".join(v) or None
    return v or None


def _conf(r: dict, name: str) -> float:
    return ((r.get("fields") or {}).get(name) or {}).get("confidence") or 0.0


def _tone(c: float) -> str:
    return "ok" if c >= 0.9 else "mid" if c >= 0.7 else "low" if c > 0 else "none"


def _settings(r: dict) -> str:
    s = r.get("settings") or {}
    return f"{s.get('effort', '?')} effort" if s else "Einstellung unbekannt"


def _image_src(photo_id: str) -> str | None:
    from .server import catalogue

    p = catalogue.image_path(photo_id)
    return p.resolve().as_uri() if p and Path(p).exists() else None


def _photo_ids(split: str | None, priority: int | None, ids: list[str] | None) -> list[str]:
    if ids:
        return ids
    from .server import catalogue

    if split or priority is not None:
        return [r["id"] for r in catalogue.list_records(split, priority=priority)]
    return [r["photo_id"] for r in results.all_results()]


def _card(photo_id: str) -> tuple[str, dict | None]:
    runs = results.history(photo_id)
    if not runs:
        return (f'<article class="card pending"><header><h2>{_esc(photo_id.split(":", 1)[-1])}</h2>'
                f'<span class="chip none">noch nicht analysiert</span></header></article>'), None
    cur, prev = runs[-1], (runs[-2] if len(runs) > 1 else None)
    img = _image_src(photo_id)
    pic = f'<img src="{_esc(img)}" alt="" loading="lazy">' if img else '<div class="noimg">kein Bild lokal</div>'
    accepted = not cur.get("needs_review")
    cons = cur.get("consistency")
    stable = "" if not cons else (
        f' <span class="chip stab" title="{_esc(cons.get("runs"))} Läufe, gleicher Ort">stabil</span>'
        if cons.get("agree") else
        f' <span class="chip unstable" title="{_esc(" / ".join(consistency.place(v) for v in cons.get("values") or []))}">instabil</span>')
    rows = []
    for name, label in FIELDS:
        v, c = _val(cur, name), _conf(cur, name)
        before = ""
        if prev is not None:
            pv, pc = _val(prev, name), _conf(prev, name)
            if pv != v or abs(pc - c) > 1e-9:
                before = (f'<div class="before">vorher: {_esc(pv or "nicht bestimmbar")} '
                          f'<span class="num">{pc:.2f}</span></div>')
        rows.append(f'<tr><th>{label}</th><td>{_esc(v) if v else "<em>nicht bestimmbar</em>"}{before}</td>'
                    f'<td class="num"><span class="pill {_tone(c)}">{c:.2f}</span></td></tr>')
    overall_before = ""
    if prev is not None:
        d = cur["overall_confidence"] - prev["overall_confidence"]
        arrow = "▲" if d > 0 else "▼" if d < 0 else "="
        overall_before = f'<span class="delta {"up" if d > 0 else "down" if d < 0 else ""}">{arrow} {prev["overall_confidence"]:.2f} vorher</span>'
    hist = "".join(
        f'<li><span class="num">{_esc((r.get("created_at") or "")[:16].replace("T", " "))}</span> '
        f'<span class="pill {_tone(r["overall_confidence"])}">{r["overall_confidence"]:.2f}</span> '
        f'{_esc(_val(r, "locality") or "?")} / {_esc(_val(r, "municipality") or "?")} / '
        f'{_esc(_val(r, "buildings") or "-")} <span class="muted">({_esc(_settings(r))}, '
        f'${(r.get("usage") or {}).get("cost_usd", 0):.2f})</span></li>' for r in reversed(runs))
    rejected = "".join(f'<li>{_esc(h.get("value"))}: {_esc(h.get("reason"))}</li>'
                       for h in (cur.get("rejected_hypotheses") or [])[:4])
    card = f'''<article class="card">
  <header><h2>{_esc(photo_id.split(":", 1)[-1])}</h2>
    <span class="chip {"ok" if accepted else "review"}">{"akzeptiert" if accepted else "Prüfung nötig"}</span>{stable}
    <span class="overall num">{cur["overall_confidence"]:.2f}</span>{overall_before}</header>
  <div class="body">
    <div class="pic">{pic}</div>
    <div class="facts">
      <table>{"".join(rows)}</table>
      <p class="why">{_esc(cur.get("confidence_explanation"))}</p>
      {f'<details><summary>Verworfen ({len(cur.get("rejected_hypotheses") or [])})</summary><ul>{rejected}</ul></details>' if rejected else ""}
      <details{" open" if prev is not None else ""}><summary>Verlauf ({len(runs)} {"Lauf" if len(runs) == 1 else "Läufe"})</summary><ul class="hist">{hist}</ul></details>
    </div>
  </div>
</article>'''
    return card, cur


def build(ids: list[str], title: str, refresh: int | None = None) -> str:
    cards, done = [], []
    for pid in ids:
        card, cur = _card(pid)
        cards.append(card)
        if cur:
            done.append(cur)
    accepted = sum(1 for r in done if not r.get("needs_review"))
    changed = sum(1 for pid in ids if len(results.history(pid)) > 1)
    unstable = sum(1 for r in done if (r.get("consistency") or {}).get("agree") is False)
    cost = sum((r.get("usage") or {}).get("cost_usd", 0) for r in done)
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    stamp = time.strftime("%d.%m.%Y %H:%M:%S")
    return f'''<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>Ergebnisbericht</title>
<style>
:root {{ --bg:#f4f6f6; --card:#fff; --ink:#17232b; --muted:#5b6a72; --line:#d8dfdf; --accent:#1f5f7a;
  --ok:#2f7d4f; --ok-bg:#e3f1e8; --mid:#8a6400; --mid-bg:#fbf0d6; --low:#a2402f; --low-bg:#f7e4e0; --none-bg:#e8ecec; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#11181c; --card:#182227; --ink:#e4ebec; --muted:#93a3a9; --line:#2a373d;
  --accent:#6fb3d1; --ok:#74c795; --ok-bg:#1b3326; --mid:#e5b84d; --mid-bg:#3a2f13; --low:#ee8d7b; --low-bg:#3d211c; --none-bg:#232e33; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; padding:24px max(16px, 3vw); }}
h1 {{ margin:0 0 4px; font-size:1.6rem; }} .lede {{ color:var(--muted); margin:0 0 18px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 14px; min-width:120px; }}
.stat b {{ display:block; font-size:1.4rem; font-variant-numeric:tabular-nums; }} .stat span {{ color:var(--muted); font-size:.85rem; }}
.toolbar {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }}
.toolbar button {{ font:inherit; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px; padding:4px 12px; cursor:pointer; }}
.toolbar button.on {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 560px), 1fr)); gap:16px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; min-width:0; }}
.card header {{ display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid var(--line); flex-wrap:wrap; }}
.card h2 {{ margin:0; font-size:1rem; font-family:ui-monospace, Menlo, monospace; }}
.overall {{ margin-left:auto; font-weight:700; font-size:1.1rem; }}
.delta {{ font-size:.8rem; color:var(--muted); }} .delta.up {{ color:var(--ok); }} .delta.down {{ color:var(--low); }}
.body {{ display:grid; grid-template-columns:200px minmax(0,1fr); gap:14px; padding:14px; }}
@media (max-width:640px) {{ .body {{ grid-template-columns:minmax(0,1fr); }} }}
.pic img {{ width:100%; border-radius:6px; display:block; }} .noimg {{ color:var(--muted); font-size:.85rem; }}
table {{ width:100%; border-collapse:collapse; }} th {{ text-align:left; color:var(--muted); font-weight:500; width:110px; vertical-align:top; padding:3px 6px 3px 0; }}
td {{ padding:3px 0; vertical-align:top; }} td em {{ color:var(--muted); }}
.num {{ font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; }}
.pill {{ display:inline-block; min-width:42px; text-align:center; border-radius:999px; padding:0 6px; font-size:.8rem; font-weight:600; }}
.pill.ok {{ background:var(--ok-bg); color:var(--ok); }} .pill.mid {{ background:var(--mid-bg); color:var(--mid); }}
.pill.low {{ background:var(--low-bg); color:var(--low); }} .pill.none {{ background:var(--none-bg); color:var(--muted); }}
.chip {{ font-size:.75rem; font-weight:600; padding:2px 8px; border-radius:999px; }}
.chip.ok {{ background:var(--ok-bg); color:var(--ok); }} .chip.review {{ background:var(--mid-bg); color:var(--mid); }} .chip.none {{ background:var(--none-bg); color:var(--muted); }}
.chip.stab {{ background:var(--ok-bg); color:var(--ok); }} .chip.unstable {{ background:var(--low-bg); color:var(--low); }}
.before {{ font-size:.8rem; color:var(--muted); text-decoration:line-through; text-decoration-color:var(--low); }}
.before .num {{ text-decoration:none; }}
.why {{ color:var(--muted); font-size:.85rem; margin:8px 0; }}
details {{ font-size:.85rem; margin-top:6px; }} summary {{ cursor:pointer; color:var(--accent); }}
ul {{ margin:6px 0 0; padding-left:18px; }} .hist {{ list-style:none; padding:0; }} .hist li {{ padding:2px 0; }} .muted {{ color:var(--muted); }}
.pending {{ opacity:.6; }}
</style></head><body>
<h1>{_esc(title)}</h1>
<p class="lede">Stand {stamp}{" · aktualisiert sich alle " + str(refresh) + " s" if refresh else ""}. Nur lokal: die Bilder werden nicht hochgeladen.</p>
<div class="stats">
  <div class="stat"><b>{len(done)} / {len(ids)}</b><span>analysiert</span></div>
  <div class="stat"><b>{accepted}</b><span>akzeptiert (≥ 0.90)</span></div>
  <div class="stat"><b>{len(done) - accepted}</b><span>Prüfung nötig</span></div>
  <div class="stat"><b>{changed}</b><span>mit Vorher-Nachher</span></div>
  <div class="stat"><b>{unstable}</b><span>instabil (Läufe uneinig)</span></div>
  <div class="stat"><b>${cost:.2f}</b><span>Kosten aktuelle Läufe</span></div>
</div>
<div class="toolbar" role="group" aria-label="Filter">
  <button class="on" data-f="all">Alle</button><button data-f="ok">Akzeptiert</button>
  <button data-f="review">Prüfung nötig</button><button data-f="changed">Vorher-Nachher</button>
  <button data-f="unstable">Instabil</button>
</div>
<div class="grid">{"".join(cards)}</div>
<script>
const cards = [...document.querySelectorAll('.card')];
document.querySelectorAll('.toolbar button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('.toolbar button').forEach(x => x.classList.toggle('on', x === b));
  const f = b.dataset.f;
  cards.forEach(c => {{
    const show = f === 'all' || (f === 'ok' && c.querySelector('.chip.ok')) ||
      (f === 'review' && c.querySelector('.chip.review')) || (f === 'changed' && c.querySelector('.delta')) ||
      (f === 'unstable' && c.querySelector('.chip.unstable'));
    c.hidden = !show;
  }});
}}));
</script>
</body></html>'''


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.report", description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", help="e.g. challenge")
    ap.add_argument("--priority", type=int)
    ap.add_argument("--ids", help="comma-separated photo ids")
    ap.add_argument("--title", default="Ergebnisbericht")
    ap.add_argument("--watch", type=int, metavar="SECONDS", help="rewrite every N seconds (page reloads itself)")
    args = ap.parse_args(argv)
    ids = _photo_ids(args.split, args.priority, args.ids.split(",") if args.ids else None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    while True:
        OUT.write_text(build(ids, args.title, args.watch), encoding="utf-8")
        print(OUT, file=sys.stderr, flush=True)
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
