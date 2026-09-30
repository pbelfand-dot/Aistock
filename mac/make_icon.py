"""Makes the Kestrel app icon from mac/kestrel.svg: mac/AppIcon.icns, docs/app-icon.png and the
dashboard's header logo. Run by hand when the logo changes (needs Pillow and Playwright's Chromium).

    python mac/make_icon.py [path/to/chromium]
"""
import asyncio
import base64
import io
import struct
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent


def render(svg: Path, size: int = 1024, chromium: str = None) -> Image.Image:
    """Draws the SVG with a headless browser (it handles the gradients and glows exactly)."""
    from playwright.async_api import async_playwright

    async def shot() -> bytes:
        async with async_playwright() as p:
            browser = await p.chromium.launch(**({"executable_path": chromium} if chromium else {}))
            page = await browser.new_page(viewport={"width": size, "height": size})
            data = base64.b64encode(svg.read_bytes()).decode()
            await page.set_content(f'<body style="margin:0"><img src="data:image/svg+xml;base64,{data}" '
                                   f'width="{size}" height="{size}"></body>')
            await page.wait_for_timeout(300)
            png = await page.screenshot(omit_background=True)
            await browser.close()
            return png

    return Image.open(io.BytesIO(asyncio.run(shot()))).convert("RGBA")


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
    picture = render(HERE / "kestrel.svg", chromium=sys.argv[1] if len(sys.argv) > 1 else None)
    (HERE / "AppIcon.icns").write_bytes(icns(picture))
    picture.resize((512, 512), Image.LANCZOS).save(HERE.parent / "docs" / "app-icon.png")
    header = HERE.parent / "trader" / "aitrader" / "web" / "kestrel-icon.png"
    picture.crop((100, 100, 924, 924)).resize((96, 96), Image.LANCZOS).save(header, optimize=True)
    print("wrote mac/AppIcon.icns, docs/app-icon.png and the dashboard's header logo")
