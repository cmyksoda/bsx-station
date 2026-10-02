import zlib

import pytest
import yaml
from fastapi.testclient import TestClient

from station.app import create_app
from station.catalog import Entry, load
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


def test_catalog_rejects_duplicate_ids(tmp_path):
    p = tmp_path / 'c.yml'
    p.write_text(yaml.safe_dump({'programs': [{'id': 'a', 'title': 'A', 'rom': 'a'},
                                              {'id': 'a', 'title': 'B', 'rom': 'b'}]}))
    with pytest.raises(ValueError):
        load(p)
