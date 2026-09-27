#!/usr/bin/env python3
"""make_catalog.py ROM_DIR > catalog.yml — a starting catalog to edit by hand (titles max 20 bytes)."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from station.catalog import from_rom_dir  # noqa: E402

print(yaml.safe_dump({'programs': from_rom_dir(Path(sys.argv[1]))}, allow_unicode=True, sort_keys=False), end='')
