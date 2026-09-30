"""
join_parts.py: unpacks a zip that was split into parts (name.z01, name.z02, ..., name.zip).

    python research/tjr/join_parts.py OUT_DIR part.z01 part.z02 part.zip

The parts are put in order by their endings (.z01, .z02, ... then .zip), joined, and each file
inside is extracted and checked against its CRC. (The `zip -s 0` route mangled these archives.)
"""
import re
import struct
import sys
import zlib
from pathlib import Path


def order(parts):
    def key(p):
        m = re.search(r"\.z(\d+)$", p.name, re.I)
        return int(m.group(1)) if m else 10 ** 6                  # the .zip part is always last
    return sorted(parts, key=key)


def extract(parts, out_dir: Path) -> list:
    blob = b"".join(p.read_bytes() for p in order(parts))
    pos = 4 if blob[:4] == b"PK\x07\x08" else 0                    # split-archive marker
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    while blob[pos:pos + 4] == b"PK\x03\x04":                     # one local file header per file
        _, _, flag, method, _, _, crc, csize, usize, nlen, xlen = struct.unpack("<IHHHHHIIIHH", blob[pos:pos + 30])
        name = blob[pos + 30:pos + 30 + nlen].decode("utf-8", errors="replace")
        start = pos + 30 + nlen + xlen
        if flag & 0x08:
            raise ValueError(f"{name}: sizes are stored after the data; not supported")
        data = blob[start:start + csize]
        if method == 8:
            data = zlib.decompressobj(-15).decompress(data)
        elif method != 0:
            raise ValueError(f"{name}: compression method {method} not supported")
        if zlib.crc32(data) & 0xFFFFFFFF != crc or len(data) != usize:
            raise ValueError(f"{name}: damaged (checksum or size doesn't match)")
        target = out_dir / Path(name).name
        target.write_bytes(data)
        written.append(target)
        pos = start + csize
    if not written:
        raise ValueError("no files found in these parts")
    return written


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    for f in extract([Path(p) for p in sys.argv[2:]], Path(sys.argv[1])):
        print(f"ok: {f} ({f.stat().st_size:,} bytes, checksum verified)")
