#!/usr/bin/env python3
"""make_catalog.py ROM_DIR [NO_INTRO_DAT] > catalog.yml — a starting catalog to edit by hand (titles max 20 bytes).
With a dat, files the set calls bad dumps come back when the dat now lists them as good."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from station.catalog import dat_good, from_rom_dir  # noqa: E402

good = dat_good(Path(sys.argv[2])) if len(sys.argv) > 2 else set()
print(yaml.safe_dump({'programs': from_rom_dir(Path(sys.argv[1]), good)}, allow_unicode=True, sort_keys=False), end='')
