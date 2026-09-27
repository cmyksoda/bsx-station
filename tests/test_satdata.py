import os
from pathlib import Path

import pytest

from satdata import Broadcast, File, Folder, TownStatus, export, fragments, lci_sequence, next_lci
from satdata.export import be24, channel_map, directory, town_status
from satdata.romfile import find_header, header_size, prepare_download

ROMS = Path(os.environ.get('BSX_ROMS', Path(__file__).parents[2] / 'snes9xgx/roms/ni-n-sat'))


@pytest.mark.parametrize('size,count', [(0, 0), (1, 1), (32768, 1), (32769, 2), (65536, 2), (65537, 3)])
def test_fragment_counts(size, count):
    assert len(fragments(bytes(size), 0x0127)) == count


def test_fragment_headers():
    data = bytes(range(256)) * 200            # 51200 bytes: one full group and a short one
    out = fragments(data, 0x0127)
    first, last = out['BSX0127-0.bin'], out['BSX0127-1.bin']
    assert first[:10] == bytes([0, 0]) + be24(32768 + 5) + bytes([1, 2]) + be24(0)
    assert last[:10] == bytes([0, 1]) + be24(51200 - 32768 + 5) + bytes([1, 2]) + be24(32768)
    assert first[10:] + last[10:] == data


def test_lci_sequence_matches_satellawave():
    seq = lci_sequence()
    got = [next(seq) for _ in range(12)]
    assert got == [0x0120, 0x0125, 0x0126, 0x0127, 0x0128, 0x012E, 0x0130, 0x0137, 0x0138, 0x0260, 0x026D, 0x026E]
    assert next_lci(0x07FD) == 0x0920


def test_town_status_layout():
    t = TownStatus(lci=0x0125)
    t.npc_flags[0] = t.npc_flags[9] = True
    b = town_status(t, export_id=7, file_ids=[0, 1])
    assert b[:9] == bytes([0, 7, 7, 0, 0, 0, 0, 3 << 4, 0])
    assert b[9:17] == bytes([1, 2, 0, 0, 0, 0, 0, 0])
    # fountain = season = 0: C# masks the shift, 1 << 31 truncates to 0
    assert b[17:19] == bytes([0, 0])
    assert b[19:23] == bytes(4)
    assert b[23:] == bytes([2, 0, 1])


def test_town_setup_bits():
    t = TownStatus(lci=0x0125, fountain=2, season=3)
    b = town_status(t, 0, [])
    assert b[17:19] == bytes([0x02, 0x40])      # fountain bit 1, season bit 2 << 12 = 0x4000


def test_channel_map_header_and_checksum():
    m = channel_map([(0x0101, 2, 0x0005, 10, 0, 0x0125), (0x0103, 5, 0x0000, 10, 0x0D, 0x0127)])
    body = m[5:]
    assert m[:2] == b'\0\0' and m[2:5] == be24(len(body))
    assert body[:7] == b'SF\0\0\0\0\x02' and body[7] == sum(body[:7]) & 0xFF
    assert body[8:11] == bytes([0x01, 0x01, 1])
    assert body[11:24] == bytes([2, 0x00, 0x05, 0, 0, 0, 0, 0, 0, 10, 0, 0x25, 0x01])


def fake_rom(size_blocks=2, lorom=True):
    data = bytearray(b'\xAA' * 0x100000)
    o = 0x7FB0 if lorom else 0xFFB0
    data[o + 0x10:o + 0x20] = b'TEST GAME       '
    data[o + 0x20] = (1 << size_blocks) - 1   # block map
    data[o + 0x21:o + 0x24] = b'\0\0\0'
    data[o + 0x24] = 0x00
    data[o + 0x25] = 0x80                      # limited starts
    data[o + 0x2A] = 0x33
    data[o + 0x2C:o + 0x30] = bytes([0x12, 0x34, 0xED, 0xCB])
    return bytes(data), o


def test_prepare_download_patches_header():
    data, o = fake_rom()
    payload, size, dest = prepare_download(data)
    assert size == 0x40000 and dest == 3 and len(payload) == size
    p = 0x7FD0
    assert payload[p:p + 4] == b'\xff' * 4
    assert payload[p + 4] == payload[p + 5] == 0   # unlimited starts
    assert payload[p + 6] == payload[p + 7] == payload[p + 0x0A] == 0xFF


def test_prepare_download_full_pack_for_big_games():
    data, _ = fake_rom(size_blocks=8, lorom=False)
    _, size, dest = prepare_download(data)
    assert size == 0x100000 and dest == 2


def test_directory_one_file():
    data, _ = fake_rom()
    f = File('Test', 'A test.', data, file_id=0, lci=0x0127, program=0x0000)
    fo = Folder('Downloads', 'Hi', [f], place=2, mugshot=17)
    prepared = {id(f): prepare_download(data)}
    d = directory([fo], 3, prepared)
    assert d[:5] == bytes([3, 1, 0, 0, 0])
    assert d[5:7] == bytes([0, 1]) and d[7:27] == b'Downloads' + bytes(11) and d[27] == 0
    assert d[28:32] == bytes([3]) + b'Hi\0'
    assert d[32:40] == bytes([0, 2, 0, 0, 17, 0, 0, 0])
    fe = d[40:]
    assert fe[:2] == bytes([0, 0]) and fe[2:22] == b'Test' + bytes(16) and fe[22] == 0
    assert fe[23] == len(b'A test.') + 1 and fe[24:32] == b'A test.\0'
    assert fe[32:36] == bytes([0x01, 0x03, 0x00, 0x00]) and fe[36:39] == be24(0x40000)
    assert fe[39:42] == bytes(3) and fe[42] == 1 << 2 and fe[43] == 0 and fe[44] == 1 | (3 << 2)
    assert fe[45:47] == bytes(2) and fe[47:52] == bytes([1 << 4, 1 << 3, 0, 23, 59 << 2])
    assert fe[52:58] == bytes(6) and d[-1] == 0 and len(fe) == 59


def test_export_has_every_channel():
    data, _ = fake_rom()
    f = File('Test', 'A test.', data, lci=0x0127)
    bc = Broadcast('Hello!', 0x0120, TownStatus(lci=0x0125), 0x0126, [Folder('Downloads', 'Hi', [f])])
    out = export(bc, 1)
    assert set(out) == {'BSX0124-0.bin', 'BSX0120-0.bin', 'BSX0125-0.bin', 'BSX0126-0.bin',
                        *(f'BSX0127-{i}.bin' for i in range(8))}
    assert out['BSX0120-0.bin'][10:] == b'Hello!\0'


@pytest.mark.skipif(not ROMS.is_dir(), reason='local ROM set not present')
def test_headers_found_across_rom_set():
    found = total = 0
    for p in sorted(ROMS.glob('*.sfc')):
        data = p.read_bytes()
        total += 1
        o = find_header(data)
        if o is not None:
            found += 1
            prepare_download(data)             # must not raise for any real game
            assert header_size(data[o:o + 48]) in (None, *(0x20000 * n for n in range(1, 9)))
    assert found / total > 0.9, f'{found}/{total}'


def test_channel_map_carries_both_time_channels():
    data, _ = fake_rom()
    bc = Broadcast('Hi', 0x0120, TownStatus(lci=0x0125), 0x0126, [Folder('F', 'M', [File('T', 'D', data, lci=0x0127)])])
    body = export(bc, 1)['BSX0124-0.bin'][5:]
    assert body[6] == 3                                   # services 0x0101, 0x0102, 0x0103
    game = body.index(bytes([0x01, 0x02, 1]))
    assert body[game + 3:game + 6] == bytes([0, 0x00, 0x30]) and body[game + 14:game + 16] == b'\0\0'
