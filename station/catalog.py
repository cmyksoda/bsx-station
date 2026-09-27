"""The catalog: what the station can broadcast. ROM files live outside the repository."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Entry:
    id: str
    title: str          # shown in the town, max 20 bytes
    rom: str            # relative to the ROM directory
    description: str = ''


def load(path: Path) -> list[Entry]:
    data = yaml.safe_load(path.read_text()) or {}
    entries = [Entry(str(e['id']), str(e['title'])[:20], str(e['rom']), str(e.get('description', '')))
               for e in data.get('programs', [])]
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('catalog ids must be unique')
    return entries


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def from_rom_dir(rom_dir: Path) -> list[dict]:
    """A starting catalog from No-Intro style filenames; titles are meant to be edited by hand."""
    out = []
    for p in sorted(rom_dir.glob('*.sfc')):
        if '[b]' in p.name:
            continue
        base = re.sub(r'\s*\((Japan|En,Ja|Magazine|SoundLink|Standalone Fix|Memory Pack|[0-9-]+)\)', '', p.stem)
        base = re.sub(r'^BS\s+', '', base).strip()
        short = base.split(' - ')[-1] if len(base) > 20 else base
        out.append({'id': slug(p.stem)[:48], 'title': short[:20], 'rom': p.name, 'description': p.stem})
    return out
