#!/usr/bin/env python3
"""gen_slot.py OUT ROM [ROM...] [--slot s1] [--export-id 1] [--message TEXT] [--place N] [--mugshot N]

Writes one broadcast slot (BSX*.bin channel files + now.txt) for desktop or Dolphin tests.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from satdata.slot import program_from_rom, write_slot  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', type=Path)
    ap.add_argument('roms', nargs='+', type=Path)
    ap.add_argument('--slot', default='s1')
    ap.add_argument('--export-id', type=int, default=1)
    ap.add_argument('--message', default='Welcome to BS-X GX!')
    ap.add_argument('--name', action='append', default=[], help='display name per ROM, in order')
    ap.add_argument('--place', type=int, default=2, help='building index (2 = Broadcast Station)')
    ap.add_argument('--mugshot', type=int, default=0)
    ap.add_argument('--url-prefix', default=None)
    a = ap.parse_args()
    programs = [program_from_rom(p, a.name[i] if i < len(a.name) else None) for i, p in enumerate(a.roms)]
    files = write_slot(a.out, a.slot, a.export_id, programs, a.message, place=a.place, mugshot=a.mugshot,
                       url_prefix=a.url_prefix)
    print(f'{len(files)} channel files, {sum(map(len, files.values()))} bytes -> {a.out}')


if __name__ == '__main__':
    main()
