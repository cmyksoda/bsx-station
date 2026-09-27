"""The station: what's on air for the Wii, the channel files, and a TV guide for people."""
from __future__ import annotations

import html
import json
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from . import catalog as catalog_mod
from .config import Config
from .schedule import Schedule, Slot
from .slots import SlotCache, manifest

VERSION = '0.1.0'


def create_app(config: Config | None = None, clock=time.time) -> FastAPI:
    config = config or Config()
    entries = catalog_mod.load(config.catalog)
    schedule = Schedule(entries, config.slot_minutes, config.games_per_slot, config.seed, config.epoch)
    cache = SlotCache(config)
    app = FastAPI(title=config.name, version=VERSION, docs_url=None, redoc_url=None)

    def slot_json(s: Slot) -> dict:
        return {'slot_id': s.id, 'start': s.start, 'end': s.end,
                'entries': [{'id': e.id, 'title': e.title, 'description': e.description} for e in s.entries]}

    @app.get('/wii/now.txt', response_class=PlainTextResponse)
    def wii_now():
        now = clock()
        slot = schedule.at(now)
        return PlainTextResponse(manifest(slot, schedule.slot(slot.index + 1), cache.files(slot), now))

    @app.get('/data/{slot_id}/{name}')
    def data(slot_id: str, name: str):
        now = schedule.at(clock())
        # the previous slot stays downloadable so a Wii tuning in at the boundary can finish
        for s in (now, schedule.slot(now.index - 1)):
            if s.id == slot_id:
                path = cache.path(s, name)
                if path:
                    return FileResponse(path, media_type='application/octet-stream')
        raise HTTPException(404)

    @app.get('/api/now')
    def api_now():
        now = clock()
        slot = schedule.at(now)
        return {'station': {'name': config.name, 'version': VERSION}, 'server_time': now,
                'now': {**slot_json(slot), 'seconds_remaining': max(0, int(slot.end - now))},
                'next': [slot_json(s) for s in schedule.upcoming(now, 4)[1:]]}

    @app.get('/api/schedule')
    def api_schedule(count: int = Query(48, ge=1, le=336)):
        return {'slots': [slot_json(s) for s in schedule.upcoming(clock(), count)]}

    @app.get('/healthz')
    def healthz():
        return {'ok': True, 'programs': len(entries)}

    @app.get('/', response_class=HTMLResponse)
    def home():
        now = clock()
        slots = [slot_json(s) for s in schedule.upcoming(now, 24)]
        return HTMLResponse(PAGE.replace('{{name}}', html.escape(config.name))
                            .replace('{{data}}', json.dumps({'now': now, 'slots': slots}).replace('</', '<\\/')))

    return app


PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{name}}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DotGothic16&family=M+PLUS+Rounded+1c:wght@400;700;800&display=swap">
<style>
  :root{--sky:#dcecfb;--paper:#f7fbff;--ink:#1f2350;--soft:#56608f;--faint:#8a93bd;--line:#c5d6ee;--pink:#e0457f;--pink-bg:#fde3ee;
    --blue:#2f7fd1;--blue-bg:#e1eefc;--sun:#f2b632;--sun-bg:#fff2cc;--red:#cf3a3a;
    --pixel:"DotGothic16",ui-monospace,monospace;--round:"M PLUS Rounded 1c",system-ui,sans-serif}
  @media (prefers-color-scheme: dark){:root{color-scheme:dark;--sky:#0f1236;--paper:#171b47;--ink:#e9ecff;--soft:#aab3e6;--faint:#6f79b0;
    --line:#2b3270;--pink:#ff7aa9;--pink-bg:#3a1a3a;--blue:#79b6ff;--blue-bg:#1a2a5c;--sun:#ffd166;--sun-bg:#3a3217;--red:#ff8080}}
  *{box-sizing:border-box} body{margin:0;background:var(--sky);color:var(--ink);font-family:var(--round);line-height:1.6;padding:24px 16px 64px}
  .wrap{max-width:720px;margin:0 auto;display:flex;flex-direction:column;gap:24px}
  header{background:var(--paper);border:3px solid var(--ink);border-radius:18px;padding:18px 20px;box-shadow:6px 6px 0 var(--pink);display:flex;justify-content:space-between;gap:12px;align-items:start}
  h1{font-family:var(--pixel);font-weight:400;font-size:clamp(26px,6vw,38px);margin:0;line-height:1.1}
  .jp{font-family:var(--pixel);color:var(--pink);letter-spacing:.2em;font-size:14px}
  .lamp{font-family:var(--pixel);background:var(--red);color:#fff;border-radius:8px;padding:4px 10px;font-size:13px;letter-spacing:.14em;white-space:nowrap}
  .now{background:var(--sun-bg);border:2px dashed var(--sun);border-radius:16px;padding:16px 18px}
  .now b{font-family:var(--pixel);font-weight:400;letter-spacing:.12em;font-size:13px}
  .now h2{margin:4px 0;font-size:24px;line-height:1.25} .now p{margin:0;color:var(--soft)}
  .clock{font-family:var(--pixel);font-size:30px;color:var(--pink);font-variant-numeric:tabular-nums}
  h3{font-family:var(--pixel);font-weight:400;font-size:18px;margin:0 0 8px}
  .guide{background:var(--paper);border:2px solid var(--ink);border-radius:16px;overflow:hidden}
  .row{display:grid;grid-template-columns:5.5em 1fr;border-top:2px solid var(--line)} .row:first-child{border-top:0}
  .row time{font-family:var(--pixel);color:var(--pink);background:var(--pink-bg);padding:10px;text-align:center;font-variant-numeric:tabular-nums}
  .row div{padding:10px 14px} .row small{display:block;color:var(--faint)}
  .row.live time{background:var(--pink);color:#fff}
  .tune{background:var(--paper);border-left:6px solid var(--blue);border-radius:12px;padding:12px 16px;color:var(--soft)}
  code{background:var(--blue-bg);color:var(--ink);border-radius:6px;padding:1px 6px}
  footer{color:var(--faint);font-size:13px;text-align:center}
</style>
</head>
<body>
<div class="wrap">
  <header><div><div class="jp">サテラビュー放送局</div><h1>{{name}}</h1></div><span class="lamp">ON AIR</span></header>
  <section class="now"><b>NOW ON AIR</b><h2 id="title">…</h2><p id="desc"></p><div class="clock" id="left"></div></section>
  <section class="tune">Tune in with <b>BS-X GX</b> on a Wii: Settings → Network → Station Address <code id="addr"></code>.
    Then walk into the Broadcast Station in the town.</section>
  <section><h3>Program guide</h3><div class="guide" id="guide"></div></section>
  <footer>Broadcast format from SatellaWave by LuigiBlood · BS-X GX</footer>
</div>
<script>
const data = {{data}};
const skew = data.now - Date.now() / 1000;
const fmt = t => new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
document.getElementById('addr').textContent = location.host;
const cur = data.slots[0];
document.getElementById('title').textContent = cur.entries.map(e => e.title).join(' / ');
document.getElementById('desc').textContent = cur.entries.map(e => e.description).join(' · ');
document.getElementById('guide').innerHTML = data.slots.map((s, i) =>
  `<div class="row${i ? '' : ' live'}"><time>${fmt(s.start)}</time><div>${esc(s.entries.map(e => e.title).join(' / '))}` +
  `<small>${esc(s.entries.map(e => e.description).join(' · '))}</small></div></div>`).join('');
function tick() {
  const left = Math.max(0, Math.round(cur.end - (Date.now() / 1000 + skew)));
  document.getElementById('left').textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} left`;
  if (left === 0) setTimeout(() => location.reload(), 3000); else setTimeout(tick, 1000);
}
tick();
</script>
</body>
</html>
'''
