"""SatellaWave-compatible export: a broadcast becomes a set of BSX<lci>-<n>.bin channel files.

Ported from SatellaWave (LuigiBlood, MIT; see LICENSE-SatellaWave), Program.ExportBSX and friends.
Byte layouts must stay identical: the BS-X BIOS is the only judge. Event Plaza, scripts, include
files and items aren't ported; the station only broadcasts downloadable files.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .romfile import prepare_download

FRAGMENT = 32768
CHANNEL_MAP_LCI = 0x0124
CHANNEL_MAP_MAX = 1485
DIRECTORY_MAX = 0x4000
TOWN_STATUS_MAX = 256

SERVICE_BSX = 0x0101
SERVICE_GAME = 0x0102
SERVICE_CONTENT = 0x0103

TYPE_NONE, TYPE_MESSAGE, TYPE_TOWN, TYPE_DIRECTORY, TYPE_PATCH, TYPE_FILE, TYPE_DATA = range(7)
DEST_WRAM, DEST_PSRAM, DEST_FLASH_ALL, DEST_FLASH_FREE = range(4)


def bsx_text(s: str, newlines: bool = True) -> bytes:
    s = s.replace('\r\n', '\r').replace('\n', '\r')
    if not newlines:
        s = s.replace('\r', ' ')
    return s.encode('cp932', errors='replace')


def fixed(s: str, n: int) -> bytes:
    b = bsx_text(s)[:n]
    return b + bytes(n - len(b))


def be16(v): return bytes([(v >> 8) & 0xFF, v & 0xFF])
def be24(v): return bytes([(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
def le16(v): return bytes([v & 0xFF, (v >> 8) & 0xFF])


def next_lci(lci: int) -> int:
    """SatellaWave's GetNextLCI step: skips the low values each 32-channel block reserves."""
    t = ((lci & 0x1F) | (lci >> 3)) + 1
    return (t | ((t & 0x3E0) << 3) | 0x20) & 0xFFFF


def lci_sequence(start: int = 0x0120):
    lci = start
    while True:
        yield lci
        lci = next_lci(lci)


def fragments(payload: bytes, lci: int) -> dict[str, bytes]:
    """SaveChannelFile: split into 32 KB data groups with a 10-byte header each."""
    count = -(-len(payload) // FRAGMENT)
    out = {}
    for i in range(count):
        chunk = payload[i * FRAGMENT:(i + 1) * FRAGMENT]
        head = bytes([0, i & 0xFF]) + be24(len(chunk) + 5) + bytes([1, count & 0xFF]) + be24(i * FRAGMENT)
        out[f'BSX{lci:04X}-{i}.bin'] = head + chunk
    return out


@dataclass
class File:
    name: str
    description: str
    data: bytes                     # raw ROM image; header detection and patching happen at export
    file_id: int = 0
    lci: int = 0
    program: int = 0
    service: int = SERVICE_CONTENT
    autostart: int = 1              # 0 no, 1 optional, 2 yes
    dest: int | None = None         # None: pick from the size like the station does
    also_at_home: bool = False
    streamed: bool = False
    month: int = 1
    day: int = 1
    hour_start: int = 0
    min_start: int = 0
    hour_end: int = 23
    min_end: int = 59
    timeout: int = 10


@dataclass
class Folder:
    name: str
    message: str
    files: list[File] = field(default_factory=list)
    purpose: int = 0                # 0 files, 1 shop
    kind: int = 0                   # 0 building, 1 NPC
    place: int = 2                  # building/NPC index (2 = Broadcast Station)
    mugshot: int = 0


@dataclass
class TownStatus:
    lci: int
    apu_setup: int = 3
    radio_setup: int = 0
    npc_flags: list[bool] = field(default_factory=lambda: [False] * 64)
    fountain: int = 0
    season: int = 0
    program: int = 0x0005
    timeout: int = 10


@dataclass
class Broadcast:
    message: str
    message_lci: int
    town: TownStatus
    directory_lci: int
    folders: list[Folder]
    include_time_channel: bool = True
    include_game_time_channel: bool = True


def _cs_shift(n: int) -> int:
    """C# `1 << (n - 1)` on int: the count is masked to 5 bits."""
    return (1 << ((n - 1) & 31)) & 0xFFFFFFFF


def town_status(t: TownStatus, export_id: int, file_ids: list[int]) -> bytes:
    b = bytearray([0, export_id & 0xFF, export_id & 0xFF, 0, 0, 0, 0,
                   ((t.radio_setup << 6) | (t.apu_setup << 4)) & 0xFF, 0])
    for x in range(8):
        b.append(sum(1 << y for y in range(8) if t.npc_flags[x * 8 + y]))
    setup = (_cs_shift(t.fountain) | (_cs_shift(t.season) << 12)) & 0xFFFF
    b += le16(setup) + bytes(4)
    b.append(len(file_ids) & 0xFF)
    b += bytes(file_ids)
    if len(b) > TOWN_STATUS_MAX:
        raise ValueError(f'town status is {len(b)} bytes, the BIOS takes {TOWN_STATUS_MAX}')
    return bytes(b)


def directory(folders: list[Folder], export_id: int, prepared: dict[int, tuple[bytes, int, int]]) -> bytes:
    b = bytearray([export_id & 0xFF, len(folders) & 0xFF, 0, 0, 0])
    for fo in folders:
        if len(fo.files) >= 256:
            raise ValueError(f'folder {fo.name!r} has more than 255 files')
        msg = bsx_text(fo.message)
        b += bytes([0, len(fo.files)]) + fixed(fo.name, 20) + b'\0'
        b += bytes([(len(msg) + 1) & 0xFF]) + msg + b'\0'
        b += bytes([(fo.purpose | (fo.kind << 1)) & 0xFF, fo.place & 0xFF, 0, 0, fo.mugshot & 0xFF, 0, 0, 0])
        for f in fo.files:
            _, size, dest = prepared[id(f)]
            desc = bsx_text(f.description)
            b += bytes([f.file_id & 0xFF, 0]) + fixed(f.name, 20) + b'\0'
            b += bytes([(len(desc) + 1) & 0xFF]) + desc + b'\0'
            b += be16(f.service) + be16(f.program) + be24(size) + bytes(3)
            b.append(((not f.also_at_home) << 2 | f.streamed << 3) & 0xFF)
            b += bytes([0, (f.autostart | (dest << 2)) & 0xFF, 0, 0])
            b += bytes([(f.month << 4) & 0xFF, (f.day << 3) & 0xFF,
                        ((f.hour_start << 3) | (f.min_start >> 3)) & 0xFF,
                        ((f.min_start << 5) | f.hour_end) & 0xFF,
                        (f.min_end << 2) & 0xFF])
            b += bytes(4) + bytes(2)    # no include file, then two unknown bytes
    b.append(0)                         # no expansion entries
    if len(b) > DIRECTORY_MAX:
        raise ValueError(f'directory is {len(b)} bytes, the BIOS takes {DIRECTORY_MAX}')
    return bytes(b)


def channel_map(entries: list[tuple[int, int, int, int, int, int]]) -> bytes:
    """entries: (service, type, program, timeout, autostart_byte, lci) in SatellaWave's ChannelList order."""
    services = []
    for e in entries:
        if e[0] not in services:
            services.append(e[0])
    body = bytearray(b'SF\0\0\0\0') + bytes([len(services) & 0xFF])
    body.append(sum(body) & 0xFF)
    for s in services:
        mine = [e for e in entries if e[0] == s]
        body += be16(s) + bytes([len(mine) & 0xFF])
        for _, typ, prog, timeout, auto, lci in mine:
            body += bytes([typ]) + be16(prog) + bytes(5) + be16(timeout) + bytes([auto]) + le16(lci)
    if len(body) > CHANNEL_MAP_MAX:
        raise ValueError(f'channel map is {len(body)} bytes, the BIOS takes {CHANNEL_MAP_MAX}')
    return bytes([0, 0]) + be24(len(body)) + bytes(body)


def export(bc: Broadcast, export_id: int) -> dict[str, bytes]:
    """All channel files of one broadcast, keyed by filename."""
    out: dict[str, bytes] = {}
    prepared = {}
    file_ids = []
    for fo in bc.folders:
        for f in fo.files:
            data, size, dest = prepare_download(f.data, f.dest)
            prepared[id(f)] = (data, size, dest)
            file_ids.append(f.file_id)
            out.update(fragments(data, f.lci))
    out.update(fragments(directory(bc.folders, export_id, prepared), bc.directory_lci))
    out.update(fragments(bsx_text(bc.message) + b'\0', bc.message_lci))
    out.update(fragments(town_status(bc.town, export_id, file_ids), bc.town.lci))

    # SatellaWave's tree order: time, message, town status, then the directory's files before the directory
    entries = []
    if bc.include_time_channel:
        entries.append((SERVICE_BSX, TYPE_NONE, 0x0008, 10, 0, 0x0000))
    if bc.include_game_time_channel:     # 1.2.0.48, which BS games read the broadcast time from
        entries.append((SERVICE_GAME, TYPE_NONE, 0x0030, 10, 0, 0x0000))
    entries.append((SERVICE_BSX, TYPE_MESSAGE, 0x0004, 10, 0, bc.message_lci))
    entries.append((SERVICE_BSX, TYPE_TOWN, bc.town.program, bc.town.timeout, 0, bc.town.lci))
    for fo in bc.folders:
        for f in fo.files:
            entries.append((f.service, TYPE_FILE, f.program, f.timeout,
                            (f.autostart | (prepared[id(f)][2] << 2)) & 0xFF, f.lci))
    entries.append((SERVICE_BSX, TYPE_DIRECTORY, 0x0006, 10, 0, bc.directory_lci))
    out[f'BSX{CHANNEL_MAP_LCI:04X}-0.bin'] = channel_map(entries)
    return out
