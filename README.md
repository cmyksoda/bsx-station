# bsx-station

*The broadcast side of [BS-X GX](https://github.com/cmyksoda/BS-X-GX).*

A small server that plays the part of St.GIGA. It works through a catalog of Satellaview programs on a
schedule, turns whatever is on air into satellite channel data in SatellaWave's format, and serves it to
BS-X GX receivers over plain HTTP. It also has a TV-guide page for people.

## What it does

- **A stateless schedule.** The wall clock and a seed decide what's on air, so restarts change nothing and
  every receiver agrees. Each pass through the catalog is freshly shuffled.
- **SatellaWave-compatible data.** `satdata/` is a byte-exact Python port of SatellaWave's export (channel
  map, town status, welcome message, directory, and the flash-friendly header patch for downloads).
- **Built on demand.** A slot's channel files are generated the first time someone asks for them and kept
  in a small disk cache.

## Endpoints

| Path | For |
| --- | --- |
| `/` | TV guide: now on air, countdown, the next 24 slots |
| `/wii/now.txt` | The receiver's manifest: slot, titles, seconds left, one `f` line per channel file |
| `/data/<slot>/<file>` | Channel files for the current (and previous) slot |
| `/api/now`, `/api/schedule?count=48` | JSON for anything else |
| `/healthz` | Liveness |

Responses always carry `Content-Length` and are never chunked; the Wii's HTTP client is deliberately tiny.

### The manifest

Plain ASCII text, one field per line, so the Wii can read it with `sscanf`:

```
bsxgx 1
slot s994725
title Jet Bike Special
next Kirby Pinball
ends_in 1237
files 12
f 0120 0 72 c70d97c7 /data/s994725/BSX0120-0.bin
f 0124 0 84 55247bd0 /data/s994725/BSX0124-0.bin
...
end
```

`f` lines are `lci index size crc32 path`. `ends_in` is relative, so receivers don't need a synced clock.
The Wii fetches every file, checks size and CRC, swaps the whole set in at once, and sleeps until the slot
ends (plus a few seconds of jitter). A new `slot` id is what makes it download again; the BIOS notices new
data through the export id inside the town status.

## Running it

ROMs and the catalog live **outside** this repository. Nothing here contains game data.

```
uv sync
uv run tools/make_catalog.py /path/to/roms > catalog.yml     # then edit titles (20 bytes max)
cp .env.example .env                                          # set STATION_ROM_DIR etc.
set -a; . ./.env; set +a
uv run uvicorn --factory station.app:create_app --host 0.0.0.0 --port 8080
```

On the Wii: BS-X GX → Home → Settings → Network → **Station Address** → `your-host:8080`.

`deploy/bsx-station.service` is a systemd unit to adapt.

## Tests

```
uv run pytest
```

Set `BSX_ROMS=/path/to/roms` to also check header detection across a real ROM set.

## Credits

- SatellaWave by LuigiBlood (MIT, see `satdata/LICENSE-SatellaWave`): the broadcast format this port follows.
- The BS-X Project and everyone who preserved the Satellaview's broadcasts.

---

*This project was made with AI assistance. For more information, see [my AI usage statement](https://github.com/cmyksoda/cmyksoda/blob/main/AI_USAGE.md).*
