"""Builds each slot's channel files once, on first request, and keeps a few around on disk."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import zlib
from pathlib import Path

from satdata.export import export
from satdata.slot import MANIFEST_VERSION, Program, build_broadcast

from .config import Config
from .schedule import Slot

KEEP = 4
FACES = 16   # 10h is the BS-X logo and 11h and up crash the BIOS (fullsnes, folder Clerk/Avatar)


class SlotCache:
    def __init__(self, config: Config):
        self.config = config
        self.root = config.cache_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def files(self, slot: Slot) -> list[dict]:
        """[{name, lci, index, size, crc}] for the slot, building it if needed."""
        index = self._dir(slot) / 'files.json'
        if index.exists():
            return json.loads(index.read_text())
        with self.lock:
            if not index.exists():
                self._build(slot)
                self._prune(slot)
        return json.loads(index.read_text())

    def path(self, slot: Slot, name: str) -> Path | None:
        if not any(f['name'] == name for f in self.files(slot)):
            return None
        return self._dir(slot) / name

    def _dir(self, slot: Slot) -> Path:
        # what went into a build is part of its name, so a new catalog or new settings rebuild the slot on air
        c = self.config
        made_of = repr((slot.entries, c.name, c.message, c.building, c.mugshot, c.autostart))
        return self.root / f'{slot.id}-{hashlib.sha1(made_of.encode()).hexdigest()[:8]}'

    def _build(self, slot: Slot):
        c = self.config
        programs = [Program(e.title, e.description or e.title, (c.rom_dir / e.rom).read_bytes()) for e in slot.entries]
        title = ' / '.join(e.title for e in slot.entries)
        message = c.message.format(station=c.name, title=title)
        mugshot = slot.index % FACES if c.mugshot == 'cycle' else int(c.mugshot)
        broadcast = build_broadcast(programs, message, folder_name=c.name[:20], folder_message='On air now!',
                                    place=c.building, mugshot=mugshot, autostart=c.autostart)
        files = export(broadcast, slot.index & 0xFF)   # a new export id is how the BIOS notices new data
        final = self._dir(slot)
        tmp = self.root / f'.{final.name}.tmp'
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        listing = []
        for name, data in sorted(files.items()):
            (tmp / name).write_bytes(data)
            listing.append({'name': name, 'lci': name[3:7], 'index': int(name[8:-4]), 'size': len(data),
                            'crc': f'{zlib.crc32(data):08x}'})
        (tmp / 'files.json').write_text(json.dumps(listing))
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)

    def _prune(self, keep_from: Slot):
        # several builds can share a slot number (the catalog changed mid-slot), so age breaks ties
        built = sorted((p for p in self.root.glob('s*') if p.is_dir() and re.match(r's\d+', p.name)),
                       key=lambda p: (int(re.match(r's(\d+)', p.name)[1]), p.stat().st_mtime_ns))
        for p in built[:-KEEP]:
            if p != self._dir(keep_from):
                shutil.rmtree(p, ignore_errors=True)


def manifest(slot: Slot, next_slot: Slot, files: list[dict], now: float) -> str:
    title = ' / '.join(e.title for e in slot.entries)
    next_title = ' / '.join(e.title for e in next_slot.entries)
    lines = [f'bsxgx {MANIFEST_VERSION}', f'slot {slot.id}', f'title {title}', f'next {next_title}',
             f'ends_in {max(0, int(slot.end - now))}', f'files {len(files)}']
    airs = next((e.airs for e in slot.entries if e.airs), '')
    if airs:
        # the broadcast's start and how far in it is: the Wii runs the satellite clock on from there
        lines.append(f'clock {airs} {int((now - slot.start) * 1000)}')
    lines += [f"f {f['lci']} {f['index']} {f['size']} {f['crc']} /data/{slot.id}/{f['name']}" for f in files]
    lines.append('end')
    return '\n'.join(lines) + '\n'
