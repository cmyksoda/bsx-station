"""The catalog: what the station can broadcast. ROM files live outside the repository."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from satdata.romfile import prepare_download


@dataclass(frozen=True)
class Entry:
    id: str
    title: str          # shown in the town, max 20 bytes
    rom: str            # relative to the ROM directory
    description: str = ''
    series: str = ''    # a series airs back to back in episode order; one episode with several entries rotates
    episode: int = 0
    # the broadcast's start in Japan time: games that keep to the satellite's clock see the slot as that hour;
    # empty leaves the Wii on its own clock
    airs: str = ''
    minutes: int = 0    # how long its slot runs; 0 for the station's slot length
    radio: str = ''     # the broadcast's radio, a file in the radio directory whose second 0 is the start


def broadcast_time(value) -> str:
    return datetime.fromisoformat(str(value)).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def load(path: Path) -> list[Entry]:
    data = yaml.safe_load(path.read_text()) or {}
    entries = [Entry(str(e['id']), str(e['title'])[:20], str(e['rom']), str(e.get('description', '')),
                     str(e.get('series', '')), int(e.get('episode', 0)), broadcast_time(e.get('airs')),
                     int(e.get('minutes', 0)), str(e.get('radio', '')))
               for e in data.get('programs', [])]
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('catalog ids must be unique')
    return entries


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


PARTS = {'Prelude': 0, 'Zenpen': 1, 'Chuuhen': 2, 'Kouhen': 3, 'Extra Mission': 99}
EPISODES = [
    r'^(?P<s>.+?) - Dai-(?P<n>\d+)-(?:wa|shuu|kai|gou)\b',
    r'^(?P<s>.+?) - (?:Stadium|Chousa|Mission) (?P<n>\d+)\b',
    r'^(?P<s>.+?) - (?P<p>Prelude|Zenpen|Chuuhen|Kouhen|Extra Mission)$',
    r'^(?P<s>.+?) - (?P<n>\d+) Gatsugou$',
    r'^(?P<s>.+?)(?: -)? Vol\. (?P<n>\d+)\b',
    r'^(?P<s>.+?)(?: -)? (?P<m>\d+)-(?P<d>\d+) Gou$',
]


def series_of(name: str) -> tuple[str, int] | None:
    """(series, episode) when a No-Intro name says which part of a run it is."""
    base = name.split(' (')[0]
    if ' + ' in base:
        return None
    for pattern in EPISODES:
        m = re.match(pattern, base)
        if m:
            g = m.groupdict()
            n = PARTS[g['p']] if g.get('p') else int(g['m']) * 100 + int(g['d']) if g.get('m') else int(g['n'])
            return m['s'], n
    return None


def from_rom_dir(rom_dir: Path, good: set[str] = frozenset()) -> list[dict]:
    """A starting catalog from No-Intro style filenames; titles are meant to be edited by hand.
    Bad dumps stay out unless `good` holds their SHA-1, and copies that download identically are kept once."""
    out, seen = [], set()
    # a pack only airs its first program, so the single dump of that program is the one to keep
    for p in sorted(rom_dir.glob('*.sfc'), key=lambda p: (' + ' in p.stem, p.name)):
        data = p.read_bytes()
        if '[b]' in p.name and hashlib.sha1(data).hexdigest() not in good:
            continue
        try:
            payload = prepare_download(data)[0]
        except ValueError:
            payload = data
        digest = hashlib.sha1(payload).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        name = p.stem.replace(' [b]', '')
        base = re.sub(r'\s*\((Japan|En,Ja|Magazine|SoundLink|Standalone Fix|Memory Pack|[0-9-]+)\)', '', name)
        base = re.sub(r'^BS\s+', '', base).strip()
        short = base.split(' - ')[-1] if len(base) > 20 else base
        out.append({'id': slug(p.stem), 'title': short[:20], 'rom': p.name, 'description': name})
    out.sort(key=lambda e: e['rom'])

    # the same program with different data (a revised build, a new week's puzzles) takes turns in one slot
    twins = {}
    for e in out:
        twins.setdefault(undated(e['description']), []).append(e)
    for e in out:
        part = series_of(e['description'])
        if part:
            e['series'], e['episode'] = slug(part[0]), part[1]
        elif len(twins[undated(e['description'])]) > 1:
            e['series'], e['episode'] = slug(undated(e['description'])), 1
    return out


def undated(name: str) -> str:
    return re.sub(r'\s*\(\d+-\d+\)', '', name)


def dat_good(path: Path) -> set[str]:
    """SHA-1s of the dumps a No-Intro dat (clrmamepro or XML) lists as good."""
    games = re.split(r'^\s*game \(|<game\b', path.read_text(), flags=re.M)[1:]
    return {h.lower() for g in games if '[b]' not in g for h in re.findall(r'sha1[ =]"?([0-9A-Fa-f]{40})', g)}
