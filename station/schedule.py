"""A stateless schedule: the wall clock alone decides what is on air, so restarts change nothing."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .catalog import Entry


@dataclass(frozen=True)
class Slot:
    index: int
    start: int          # unix seconds
    end: int
    entries: tuple[Entry, ...]

    @property
    def id(self) -> str:
        return f's{self.index}'


class Schedule:
    def __init__(self, entries: list[Entry], slot_minutes: int, games_per_slot: int, seed: str, epoch: int = 0):
        if not entries:
            raise ValueError('the catalog is empty')
        self.length = slot_minutes * 60
        self.per_slot = max(1, min(games_per_slot, len(entries)))
        self.epoch = epoch
        self.entries = entries
        self.seed = seed

    def _order(self, cycle: int) -> list[Entry]:
        # a fresh shuffle for every pass through the catalog, reproducible from the seed
        rng = random.Random(hashlib.sha256(f'{self.seed}/{cycle}'.encode()).digest())
        order = list(self.entries)
        rng.shuffle(order)
        return order

    def slot(self, index: int) -> Slot:
        n = len(self.entries)
        picks = []
        for k in range(self.per_slot):
            pos = index * self.per_slot + k
            picks.append(self._order(pos // n)[pos % n])
        start = self.epoch + index * self.length
        return Slot(index, start, start + self.length, tuple(picks))

    def at(self, t: float) -> Slot:
        return self.slot(int((t - self.epoch) // self.length))

    def upcoming(self, t: float, count: int) -> list[Slot]:
        first = self.at(t).index
        return [self.slot(first + i) for i in range(count)]
