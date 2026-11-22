"""Generate the small, dependency-free TURA PWA icon set."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "frontend" / "assets"
NAVY = (11, 31, 58)
INK = (7, 21, 40)
WHITE = (244, 247, 252)
WINDOW = (35, 83, 125)
AMBER = (245, 197, 66)


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _png(size: int) -> bytes:
    image = bytearray(NAVY * (size * size))

    def paint(x: int, y: int, color: tuple[int, int, int]) -> None:
        offset = (y * size + x) * 3
        image[offset:offset + 3] = bytes(color)

    def rounded_box(box: tuple[int, int, int, int], radius: int, color: tuple[int, int, int]) -> None:
        left, top, right, bottom = (round(value * size / 512) for value in box)
        radius = round(radius * size / 512)
        for y in range(top, bottom):
            nearest_y = min(max(y, top + radius), bottom - radius - 1)
            dy = y - nearest_y
            inset = max(0, radius - int((radius * radius - dy * dy) ** 0.5))
            start = left + inset
            end = right - inset
            if start < end:
                row = bytes(color) * (end - start)
                offset = (y * size + start) * 3
                image[offset:offset + len(row)] = row

    def circle(cx: int, cy: int, radius: int, color: tuple[int, int, int]) -> None:
        cx, cy, radius = (round(value * size / 512) for value in (cx, cy, radius))
        for y in range(max(0, cy - radius), min(size, cy + radius + 1)):
            half_width = int((radius * radius - (y - cy) ** 2) ** 0.5)
            start = max(0, cx - half_width)
            end = min(size, cx + half_width + 1)
            row = bytes(color) * (end - start)
            offset = (y * size + start) * 3
            image[offset:offset + len(row)] = row

    rounded_box((116, 88, 396, 397), 54, WHITE)
    rounded_box((147, 132, 365, 259), 24, WINDOW)
    rounded_box((147, 282, 365, 313), 12, INK)
    rounded_box((251, 143, 261, 249), 4, WHITE)
    circle(157, 344, 18, AMBER)
    circle(355, 344, 18, AMBER)
    circle(171, 382, 33, INK)
    circle(341, 382, 33, INK)
    rounded_box((245, 433, 267, 450), 8, AMBER)
    rounded_box((245, 470, 267, 487), 8, AMBER)

    rows = b"".join(b"\0" + image[y * size * 3:(y + 1) * size * 3] for y in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b"")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        (ASSETS / f"pwa-icon-{size}.png").write_bytes(_png(size))


if __name__ == "__main__":
    main()
