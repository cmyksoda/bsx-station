"""One broadcast slot: the channel files for whatever is on air, plus the manifest the Wii reads."""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .export import Broadcast, File, Folder, TownStatus, export, lci_sequence
from .romfile import title as rom_title

MANIFEST_VERSION = 1


@dataclass
class Program:
    name: str           # shown in the building, max 20 bytes
    description: str
    data: bytes
    airs: datetime | None = None    # its broadcast's start: the BIOS lists the hours and dates the download
    minutes: int = 60


def timeslot(p: Program) -> dict:
    """The directory's date and broadcast hours for a program that keeps to a broadcast, as File fields."""
    if not p.airs:
        return {}
    end = p.airs + timedelta(minutes=p.minutes)
    # St.GIGA counted past midnight (25:00), and the end hour has five bits for it
    end_hour = end.hour + 24 * (end.date() - p.airs.date()).days
    return dict(month=p.airs.month, day=p.airs.day, hour_start=p.airs.hour, min_start=p.airs.minute,
                hour_end=end_hour, min_end=end.minute)


def build_broadcast(programs: list[Program], message: str, folder_name: str = 'BS-X GX',
                    folder_message: str = 'On air now!', place: int = 2, mugshot: int = 0,
                    autostart: int = 1, radio: bool = False) -> Broadcast:
    lcis = lci_sequence()
    message_lci, town_lci, dir_lci = next(lcis), next(lcis), next(lcis)
    files = [File(p.name, p.description, p.data, file_id=i, lci=next(lcis), program=i * 0x0100, autostart=autostart,
                  **timeslot(p))
             for i, p in enumerate(programs)]
    folder = Folder(folder_name, folder_message, files, place=place, mugshot=mugshot)
    # St.GIGA's radio carried a SoundLink program's hour: with a track to play, the town turns the receiver's audio on
    # and keeps only its sound effects, so the radio isn't played over the town's music
    town = TownStatus(lci=town_lci, apu_setup=1, radio_setup=1) if radio else TownStatus(lci=town_lci)
    return Broadcast(message, message_lci, town, dir_lci, [folder])


def manifest(slot_id: str, files: dict[str, bytes], title: str, next_title: str, ends_in: int, url_prefix: str) -> str:
    """Plain text so the Wii can parse it with sscanf: one `f` line per channel file."""
    lines = [f'bsxgx {MANIFEST_VERSION}', f'slot {slot_id}', f'title {title}', f'next {next_title}',
             f'ends_in {int(ends_in)}', f'files {len(files)}']
    for name in sorted(files):
        lci, index = name[3:7], int(name[8:-4])
        data = files[name]
        lines.append(f'f {lci} {index} {len(data)} {zlib.crc32(data):08x} {url_prefix}/{name}')
    lines.append('end')
    return '\n'.join(lines) + '\n'


def write_slot(out: Path, slot_id: str, export_id: int, programs: list[Program], message: str,
               next_title: str = '', ends_in: int = 1800, url_prefix: str | None = None, **kw) -> dict[str, bytes]:
    files = export(build_broadcast(programs, message, **kw), export_id)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    title = ' / '.join(p.name for p in programs)
    (out / 'now.txt').write_text(manifest(slot_id, files, title, next_title, ends_in,
                                          url_prefix if url_prefix is not None else f'/data/{slot_id}'))
    return files


def program_from_rom(path: Path, name: str | None = None) -> Program:
    data = path.read_bytes()
    label = name or rom_title(data) or path.stem
    return Program(label[:20], path.stem[:60], data)
