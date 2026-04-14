"""Generate simple PNG icons for PWA. Pure Python, no external deps."""

import struct
import zlib
from pathlib import Path


def create_png(width: int, height: int, pixels_fn) -> bytes:
    """Create an RGB PNG from a pixel function: (x, y) -> (r, g, b)."""

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    sig = b"\x89PNG\r\n\x1a\n"
    # 8-bit RGBA
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        for x in range(width):
            r, g, b, a = pixels_fn(x, y, width, height)
            raw.extend([r, g, b, a])

    idat = chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def poop_icon_pixel(x: int, y: int, w: int, h: int) -> tuple:
    """Brown circle with darker poop swirl shape on warm background."""
    cx, cy = w / 2, h / 2
    r = w * 0.42
    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5

    if dist <= r:
        # Inside circle - brown gradient
        t = dist / r
        base_r = int(121 - 40 * t)
        base_g = int(85 - 30 * t)
        base_b = int(72 - 25 * t)
        # Add a subtle swirl highlight
        highlight = ((x - cx * 0.8) ** 2 + (y - cy * 0.7) ** 2) ** 0.5
        if highlight < r * 0.35:
            base_r = min(255, base_r + 25)
            base_g = min(255, base_g + 18)
            base_b = min(255, base_b + 15)
        return (base_r, base_g, base_b, 255)
    elif dist <= r + 2:
        # Anti-alias edge
        alpha = max(0, int(255 * (1 - (dist - r) / 2)))
        return (78, 52, 46, alpha)
    else:
        return (0, 0, 0, 0)


def generate(output_dir: str = "static") -> None:
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    for size in (180, 192, 512):
        data = create_png(size, size, poop_icon_pixel)
        path = out / f"icon-{size}.png"
        path.write_bytes(data)
        print(f"Generated {path} ({len(data)} bytes)")


if __name__ == "__main__":
    generate()
