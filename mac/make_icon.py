"""Draws the app icon and writes mac/AppIcon.icns (run by hand when the icon changes; needs Pillow).

    python mac/make_icon.py
"""
import io
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

S = 4096                                   # draw big, then shrink: smooth edges


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # The rounded square (Apple's icon grid: 824 of 1024, centered), navy top to bottom.
    inset, radius = S * 100 // 1024, S * 185 // 1024
    top, bottom = (22, 70, 122), (8, 30, 56)
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([inset, inset, S - inset, S - inset], radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # A rising price line with a soft blue wash under it, and a bright dot at "today".
    u = S / 1024
    pts = [(235, 690), (385, 560), (500, 620), (640, 440), (790, 330)]
    pts = [(x * u, y * u) for x, y in pts]
    shape = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shape).polygon(pts + [(pts[-1][0], 800 * u), (pts[0][0], 800 * u)], fill=255)
    fade = Image.new("L", (S, S), 0)                     # strongest under the line, gone at the bottom
    fd = ImageDraw.Draw(fade)
    for y in range(round(300 * u), round(800 * u)):
        fd.line([(0, y), (S, y)], fill=round(130 * (1 - (y - 300 * u) / (500 * u))))
    wash = Image.new("RGBA", (S, S), (57, 135, 229, 0))
    wash.putalpha(ImageChops.darker(fade, shape))       # the fade, only inside the shape
    img.alpha_composite(wash)
    d = ImageDraw.Draw(img)
    d.line(pts, fill=(255, 255, 255, 255), width=round(54 * u), joint="curve")
    for x, y in pts[:1]:
        r = 27 * u
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
    x, y = pts[-1]
    for r, color in ((70 * u, (255, 255, 255, 255)), (46 * u, (57, 135, 229, 255))):
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    return img


def icns(img: Image.Image) -> bytes:
    # Apple's icon types, each holding a PNG of the given size.
    kinds = [("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic08", 256), ("ic09", 512),
             ("ic10", 1024), ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512)]
    body = b""
    for kind, size in kinds:
        buf = io.BytesIO()
        img.resize((size, size), Image.LANCZOS).save(buf, "PNG", optimize=True)
        png = buf.getvalue()
        body += kind.encode() + struct.pack(">I", len(png) + 8) + png
    return b"icns" + struct.pack(">I", len(body) + 8) + body


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    picture = draw()
    (here / "AppIcon.icns").write_bytes(icns(picture))
    picture.resize((512, 512), Image.LANCZOS).save(here.parent / "docs" / "app-icon.png")
    print("wrote mac/AppIcon.icns and docs/app-icon.png")
