"""BS content headers: finding them, sizing the download, and making it flash-friendly (SatellaWave's rules)."""
from __future__ import annotations

PSRAM_MAX = 0x80000
FLASH_MAX = 0x100000
DEST_PSRAM, DEST_FLASH_ALL, DEST_FLASH_FREE = 1, 2, 3


def find_header(data: bytes) -> int | None:
    """FindFirstBSContentHeader: offset of the 48-byte header at x7FB0 (LoROM) or xFFB0 (HiROM) of a 128 KB block."""
    for i in range(len(data) // 0x20000):
        for base in (0x7FB0, 0xFFB0):
            o = base + i * 0x20000
            h = data[o:o + 48]
            if len(h) < 48:
                continue
            if (h[0x2C] ^ h[0x2E]) == 0xFF and (h[0x2D] ^ h[0x2F]) == 0xFF and h[0x2A] in (0x33, 0xFF):
                return o
    return None


def header_size(h: bytes) -> int | None:
    """The header's block map: one bit per 128 KB block the content uses."""
    if h[0x20] != 0 and h[0x21] == 0 and h[0x22] == 0 and h[0x23] == 0:
        return 0x20000 * bin(h[0x20]).count('1')
    return None


def title(data: bytes) -> str | None:
    o = find_header(data)
    if o is None:
        return None
    return data[o + 0x10:o + 0x20].decode('cp932', errors='replace').rstrip('\0 ＀')


def prepare_download(data: bytes, dest: int | None = None) -> tuple[bytes, int, int]:
    """Returns (payload, size, dest). dest None picks the free-space pack area when the content fits in 512 KB."""
    o = find_header(data)
    size = len(data)
    lorom = True
    if o is not None:
        lorom = (o & 0xFFFF) == 0x7FB0
        size = header_size(data[o:o + 48]) or size
    if dest is None:
        dest = DEST_FLASH_FREE if size <= 0x80000 else DEST_FLASH_ALL
    limit = {DEST_PSRAM: PSRAM_MAX, DEST_FLASH_ALL: FLASH_MAX, DEST_FLASH_FREE: PSRAM_MAX}.get(dest)
    if limit and size > limit:
        raise ValueError(f'{size} bytes will not fit destination {dest}')

    start = (o & 0xFF0000) if o is not None else 0
    payload = bytearray(data[start:start + size])
    payload += bytes(size - len(payload))
    if o is not None and dest >= 1:
        p = 0x7FD0 | (0 if lorom else 0x8000)
        payload[p:p + 4] = b'\xff\xff\xff\xff'      # erase-state fields the BIOS writes after download
        if payload[p + 5] == 0x80 and payload[p + 4] == 0:
            payload[p + 4] = 0x01                   # a limited-start game gets one start
        payload[p + 6] = payload[p + 7] = payload[p + 0x0A] = 0xFF
    return bytes(payload), size, dest
