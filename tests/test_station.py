import hashlib
import zlib

import pytest
import yaml
from fastapi.testclient import TestClient

from station import slots as slots_mod
from station.app import create_app
from station.catalog import Entry, dat_good, from_rom_dir, load, series_of
from station.config import Config
from station.schedule import Schedule
from tests.test_satdata import fake_rom


@pytest.fixture
def station(tmp_path):
    roms = tmp_path / 'roms'
    roms.mkdir()
    programs = []
    for i in range(3):
        data, _ = fake_rom(size_blocks=1 + i)
        (roms / f'game{i}.sfc').write_bytes(data)
        programs.append({'id': f'g{i}', 'title': f'Game {i}', 'rom': f'game{i}.sfc', 'description': f'Test game {i}'})
    catalog = tmp_path / 'catalog.yml'
    catalog.write_text(yaml.safe_dump({'programs': programs}))
    config = Config(rom_dir=roms, catalog=catalog, cache_dir=tmp_path / 'cache', slot_minutes=30, seed='test')
    now = [1_800_000_000.0 + 60]
    client = TestClient(create_app(config, clock=lambda: now[0]))
    return client, now


def parse(text):
    head, files = {}, []
    for line in text.splitlines():
        key, _, rest = line.partition(' ')
        if key == 'f':
            lci, index, size, crc, url = rest.split()
            files.append((lci, int(index), int(size), crc, url))
        else:
            head[key] = rest
    return head, files


def test_schedule_is_deterministic_and_visits_everything():
    entries = [Entry(f'g{i}', f'G{i}', f'{i}.sfc') for i in range(5)]
    a = Schedule(entries, 30, 1, 'seed')
    b = Schedule(entries, 30, 1, 'seed')
    assert [a.slot(i).entries for i in range(20)] == [b.slot(i).entries for i in range(20)]
    for cycle in range(3):
        assert {a.slot(cycle * 5 + i).entries[0].id for i in range(5)} == {e.id for e in entries}
    assert a.at(a.slot(7).start + 5).index == 7


def test_series_air_back_to_back_in_episode_order():
    singles = [Entry(f'g{i}', f'G{i}', f'{i}.sfc') for i in range(12)]
    run = [Entry(f'z{n}', f'Z{n}', f'z{n}.sfc', series='zelda', episode=n) for n in (3, 1, 4, 2)]
    s = Schedule(singles + run, 30, 1, 'seed')
    starts = set()
    for cycle in range(6):
        aired = [s.slot(cycle * 16 + i).entries[0].id for i in range(16)]
        first = aired.index('z1')
        assert aired[first:first + 4] == ['z1', 'z2', 'z3', 'z4']
        starts.add(first)
    assert len(starts) > 1


def test_builds_of_one_episode_take_turns():
    a = Entry('a', 'A', 'a.sfc', series='x', episode=1)
    b = Entry('b', 'B', 'b.sfc', series='x', episode=1)
    s = Schedule([a, b, Entry('c', 'C', 'c.sfc')], 30, 1, 'seed')
    aired = [s.slot(i).entries[0].id for i in range(8)]
    assert s.episodes == 2 and aired.count('a') == aired.count('b') == 2 and aired.count('c') == 4


def test_nothing_airs_twice_in_a_row_across_passes():
    s = Schedule([Entry(f'g{i}', f'G{i}', f'{i}.sfc') for i in range(3)], 30, 1, 'seed')
    aired = [s.slot(i).entries[0].id for i in range(300)]
    assert all(x != y for x, y in zip(aired, aired[1:]))


@pytest.mark.parametrize('name,part', [
    ('BS Zelda no Densetsu - Dai-1-wa (Japan) (Rerun) (SoundLink)', ('BS Zelda no Densetsu', 1)),
    ('BS Zelda no Densetsu - Map 2 - Dai-1-wa (Japan) (SoundLink)', ('BS Zelda no Densetsu - Map 2', 1)),
    ('BS Fire Emblem - Akaneia Senki Hen - Dai-4-wa - Hajimari no Toki (Japan) (4-28) (SoundLink)',
     ('BS Fire Emblem - Akaneia Senki Hen', 4)),
    ('Excitebike - Bunbun Mario Battle - Stadium 3 (Japan) (11-5) (SoundLink)', ('Excitebike - Bunbun Mario Battle', 3)),
    ('BS Tantei Club - Yuki ni Kieta Kako - Kouhen (Japan) (SoundLink)', ('BS Tantei Club - Yuki ni Kieta Kako', 3)),
    ('Spriggan Powered BS - Prelude (Japan) (SoundLink)', ('Spriggan Powered BS', 0)),
    ('Sousa Sentai Wappers - Extra Mission (Japan) (Magazine)', ('Sousa Sentai Wappers', 99)),
    ('GoodsPress - 6 Gatsugou (Japan) (Magazine)', ('GoodsPress', 6)),
    ('Do-Re-Mi de Faa 2~! Vol. 8 - 5-10 Gou (Japan) (Magazine)', ('Do-Re-Mi de Faa 2~!', 8)),
    ('Digital Magazine Busters BS - 6-21 Gou (Japan) (Magazine)', ('Digital Magazine Busters BS', 621)),
    ('Kirby no Omochabako - Pinball (Japan)', None),
    ('Tamori no Picross (7-14) + SatellaQ + Machi Magazine (7-21) (Japan)', None),
])
def test_series_from_no_intro_names(name, part):
    assert series_of(name) == part


def test_manifest_matches_the_data(station):
    client, now = station
    head, files = parse(client.get('/wii/now.txt').text)
    assert head['bsxgx'] == '1' and head['slot'].startswith('s') and 'end' in head
    assert int(head['ends_in']) == 30 * 60 - 60 and int(head['files']) == len(files)
    assert any(f[0] == '0124' for f in files)
    for lci, index, size, crc, url in files:
        r = client.get(url)
        assert r.status_code == 200 and int(r.headers['content-length']) == size == len(r.content)
        assert f'{zlib.crc32(r.content):08x}' == crc
        assert 'transfer-encoding' not in r.headers


def test_previous_slot_stays_downloadable_but_older_ones_do_not(station):
    client, now = station
    _, files = parse(client.get('/wii/now.txt').text)
    url = files[0][4]
    now[0] += 30 * 60
    assert client.get(url).status_code == 200
    now[0] += 30 * 60
    assert client.get(url).status_code == 404


def test_api_and_page(station):
    client, _ = station
    j = client.get('/api/now').json()
    assert j['now']['entries'][0]['title'].startswith('Game') and len(j['next']) == 3
    assert len(client.get('/api/schedule?count=10').json()['slots']) == 10
    page = client.get('/')
    assert page.status_code == 200 and 'NOW ON AIR' in page.text
    assert client.get('/healthz').json() == {'ok': True, 'programs': 3}


def test_each_slot_gets_the_next_face(station, monkeypatch):
    client, now = station
    faces = []
    real = slots_mod.build_broadcast
    monkeypatch.setattr(slots_mod, 'build_broadcast', lambda *a, **kw: faces.append(kw['mugshot']) or real(*a, **kw))
    for _ in range(3):
        client.get('/wii/now.txt')
        now[0] += 30 * 60
    assert faces[1] == (faces[0] + 1) % 16 and faces[2] == (faces[0] + 2) % 16


def test_starting_catalog_drops_repeats_and_finds_series(tmp_path):
    data, o = fake_rom()

    def rom(name, date=0, first=0xAA):
        d = bytearray(data)
        d[o + 0x26], d[0] = date, first
        (tmp_path / f'{name}.sfc').write_bytes(bytes(d))
        return hashlib.sha1(bytes(d)).hexdigest()

    rom('Game A (Japan) (1-2)', date=0x10)
    rom('Game A (Japan) (1-3)', date=0x18)       # another day's date stamp, same download
    rom('Game B (Japan) (1-2)', first=1)
    rom('Game B (Japan) (5-9)', first=2)         # different data: the two take turns
    bad = rom('Game C (Japan) [b]', first=3)
    rom('Game D - Dai-2-wa (Japan)', first=4)
    rom('Game D - Dai-1-wa (Japan)', first=5)
    plain = {e['rom']: e for e in from_rom_dir(tmp_path)}
    assert sorted(plain) == ['Game A (Japan) (1-2).sfc', 'Game B (Japan) (1-2).sfc', 'Game B (Japan) (5-9).sfc',
                             'Game D - Dai-1-wa (Japan).sfc', 'Game D - Dai-2-wa (Japan).sfc']
    assert {(e['series'], e['episode']) for e in plain.values() if 'Game B' in e['rom']} == {('game-b-japan', 1)}
    assert plain['Game D - Dai-2-wa (Japan).sfc']['episode'] == 2 and 'series' not in plain['Game A (Japan) (1-2).sfc']
    vouched = {e['rom']: e for e in from_rom_dir(tmp_path, good={bad})}
    assert vouched['Game C (Japan) [b].sfc']['description'] == 'Game C (Japan)'


def test_dat_lists_only_good_dumps(tmp_path):
    a, b, c = 'A' * 40, 'b' * 40, 'C' * 40
    clr = tmp_path / 'a.dat'
    clr.write_text(f'clrmamepro (\n\tname "x"\n)\n\ngame (\n\tname "One (Japan)"\n\trom ( name "One.bs" sha1 {a} )\n)\n'
                   f'game (\n\tname "Two (Japan) [b]"\n\trom ( name "Two.bs" sha1 {b} )\n)\n')
    xml = tmp_path / 'b.dat'
    xml.write_text(f'<datafile><game name="Three (Japan)"><rom name="Three.bs" sha1="{c}"/></game></datafile>')
    assert dat_good(clr) == {a.lower()} and dat_good(xml) == {c.lower()}


def test_catalog_reads_series(tmp_path):
    p = tmp_path / 'c.yml'
    p.write_text(yaml.safe_dump({'programs': [{'id': 'a', 'title': 'A', 'rom': 'a', 'series': 'z', 'episode': 2},
                                              {'id': 'b', 'title': 'B', 'rom': 'b'}]}))
    a, b = load(p)
    assert (a.series, a.episode) == ('z', 2) and (b.series, b.episode) == ('', 0)


def test_catalog_rejects_duplicate_ids(tmp_path):
    p = tmp_path / 'c.yml'
    p.write_text(yaml.safe_dump({'programs': [{'id': 'a', 'title': 'A', 'rom': 'a'},
                                              {'id': 'a', 'title': 'B', 'rom': 'b'}]}))
    with pytest.raises(ValueError):
        load(p)
