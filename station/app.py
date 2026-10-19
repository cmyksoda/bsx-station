"""The station: what's on air for the Wii, the channel files, and a TV guide for people."""
from __future__ import annotations

import html
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from . import catalog as catalog_mod
from .config import Config
from .schedule import Schedule, Slot
from .slots import SlotCache, manifest

VERSION = '0.1.0'
STATIC = Path(__file__).parent / 'static'


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
        return PlainTextResponse(manifest(slot, schedule.slot(slot.index + 1), cache.files(slot), now, cache.radio(slot)))

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

    radio_names = {e.radio for e in entries if e.radio}

    @app.get('/radio/{name}')
    def radio(name: str):
        path = config.radio_dir / name
        if name not in radio_names or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='audio/ogg')

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

    @app.get('/dot.woff2')
    def font():
        return FileResponse(STATIC / 'dot.woff2', media_type='font/woff2', headers={'Cache-Control': 'max-age=86400'})

    if config.background:
        @app.get('/bg.png')
        def background():
            return FileResponse(config.background, media_type='image/png', headers={'Cache-Control': 'max-age=86400'})

    @app.get('/', response_class=HTMLResponse)
    def home():
        now = clock()
        data = {'now': now, 'address': config.address, 'slots': [slot_json(s) for s in schedule.upcoming(now, 24)]}
        bg = 'url(bg.png) 0 0/256px 128px' if config.background else ''
        return HTMLResponse(PAGE.replace('{{name}}', html.escape(config.name)).replace('{{bg}}', bg)
                            .replace('{{data}}', json.dumps(data).replace('</', '<\\/')))

    return app


PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{name}}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DotGothic16&display=swap">
<style>
  @font-face{font-family:"Station Dot";src:url(dot.woff2) format("woff2");unicode-range:U+20-7E,U+B7}
  :root{--navy:#00296b;--gold:#a58400;--gold-hi:#ffff7b;--brown:#6b3100;--paper:#fff;--gray:#bdbdbd;--ink:#000;
    --dim:#4a4a5e;--red:#942918;--lamp:#ff0033;--purple:#7339bd;--pixel:"Station Dot","DotGothic16",ui-monospace,monospace}
  *{box-sizing:border-box} h1,h2,h3,b{font-weight:400}
  body{margin:0;color:var(--ink);font-family:var(--pixel);font-size:16px;line-height:1.6;padding:24px 16px 64px;
    background:var(--purple) {{bg}};image-rendering:pixelated}
  .wrap{max-width:720px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
  /* the town's two window kinds: navy with a gold frame, and white message boxes */
  header,h3,.guide,footer{background:var(--navy);color:#fff;border:2px solid var(--gold);
    box-shadow:inset 0 0 0 2px var(--gold-hi),inset 0 0 0 4px var(--gold),inset 0 0 0 6px var(--brown)}
  .now,.tune{background:var(--paper);border:2px solid var(--ink);box-shadow:inset 0 0 0 2px var(--gray)}
  header,h3,.guide,footer,.now,.tune{clip-path:polygon(2px 0,calc(100% - 2px) 0,100% 2px,100% calc(100% - 2px),
    calc(100% - 2px) 100%,2px 100%,0 calc(100% - 2px),0 2px)}
  header{padding:18px 22px;display:flex;justify-content:space-between;gap:12px;align-items:start}
  h1{font-size:clamp(28px,7vw,40px);margin:0;line-height:1.1}
  .jp{color:var(--gold-hi);letter-spacing:.1em}
  .lamp{background:var(--lamp);color:#fff;border:2px solid var(--ink);padding:2px 10px;letter-spacing:.1em;white-space:nowrap}
  .now,.tune{padding:16px 22px}
  .now b,.tune b{color:var(--red);letter-spacing:.1em}
  .now h2{margin:4px 0;font-size:24px;line-height:1.3} .now p{margin:0;color:var(--dim)}
  .dots{background:linear-gradient(90deg,var(--gray) 50%,transparent 0) 0 0/4px 2px repeat-x}
  .clock{font-size:32px;color:var(--red);font-variant-numeric:tabular-nums;margin-top:10px;padding-top:6px}
  .tune p{margin:4px 0 0;color:var(--dim)}
  code{font-family:var(--pixel);background:var(--navy);color:var(--gold-hi);padding:1px 8px}
  h3{display:inline-block;font-size:18px;margin:0 0 8px;padding:6px 20px 8px}
  .guide{padding:6px}
  .row{display:grid;grid-template-columns:7.5em 1fr}
  .row+.row{background:linear-gradient(90deg,var(--gold) 50%,transparent 0) 0 0/4px 2px repeat-x}
  .row time{color:var(--gold-hi);padding:10px 0 10px 12px;font-variant-numeric:tabular-nums;white-space:nowrap}
  .row div{padding:10px 14px 10px 4px} .row small{display:block;color:var(--gray)}
  .row.live{background-color:var(--red)} .row.live small{color:#f2c9bd}
  .row.live time::before{content:"";display:inline-block;width:22px;height:22px;margin:0 6px 0 -6px;vertical-align:-5px;
    background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 11 11' shape-rendering='crispEdges'%3E%3Cpath d='M0 3h5V0l5.5 5.5L5 11V8H0z'/%3E%3Cpath d='M1 4h5V2.5l3 3-3 3V7H1z' fill='%23ff5577'/%3E%3C/svg%3E")}
  footer{color:#fff;padding:12px 22px}
  /* below 16px a dot is under a pixel, so narrow letters need one more to stay apart */
  .row small,footer{font-size:14px;letter-spacing:1px}
</style>
</head>
<body>
<div class="wrap">
  <header><div><div class="jp">サテラビュー放送局</div><h1>{{name}}</h1></div><span class="lamp">ON AIR</span></header>
  <section class="now"><b>NOW ON AIR</b><h2 id="title">…</h2><p id="desc"></p><div class="clock dots" id="left"></div></section>
  <section class="tune"><b>HOW TO TUNE IN</b><p>On a Wii with BS-X GX: Settings → Network → Station Address →
    <code id="addr"></code><br>Then, walk into the Broadcast Station in the town.</p></section>
  <section><h3>Program guide</h3><div class="guide" id="guide"></div></section>
  <footer>Broadcast format from SatellaWave by LuigiBlood · BS-X GX</footer>
</div>
<script>
const data = {{data}};
const skew = data.now - Date.now() / 1000;
const fmt = t => new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
document.getElementById('addr').textContent = data.address || location.host;
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
