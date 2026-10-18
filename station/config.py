"""Station settings, from the environment (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Config:
    name: str = field(default_factory=lambda: _env('STATION_NAME', 'BS-X GX Station'))
    rom_dir: Path = field(default_factory=lambda: Path(_env('STATION_ROM_DIR', 'roms')))
    catalog: Path = field(default_factory=lambda: Path(_env('STATION_CATALOG', 'catalog.yml')))
    cache_dir: Path = field(default_factory=lambda: Path(_env('STATION_CACHE_DIR', 'cache')))
    slot_minutes: int = field(default_factory=lambda: int(_env('STATION_SLOT_MINUTES', '30')))
    games_per_slot: int = field(default_factory=lambda: int(_env('STATION_GAMES_PER_SLOT', '1')))
    seed: str = field(default_factory=lambda: _env('STATION_SEED', 'satellaview'))
    message: str = field(default_factory=lambda: _env('STATION_MESSAGE', 'Welcome to {station}! On air now: {title}.'))
    building: int = field(default_factory=lambda: int(_env('STATION_BUILDING', '2')))
    # a face number (0-16, 16 is the BS-X logo), or 'cycle' for the next face every slot
    mugshot: str = field(default_factory=lambda: _env('STATION_MUGSHOT', 'cycle'))
    autostart: int = field(default_factory=lambda: int(_env('STATION_AUTOSTART', '1')))
    epoch: int = field(default_factory=lambda: int(_env('STATION_EPOCH', '0')))
    # what the guide tells Wiis to enter, when people read it at a different address
    address: str = field(default_factory=lambda: _env('STATION_ADDRESS', ''))
    # an image tiled behind the guide; art taken from the BIOS stays outside the repository, like the ROMs
    background: str = field(default_factory=lambda: _env('STATION_BACKGROUND', ''))
