"""Generate logo PNG and ICO from scratch using Pillow."""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 256

NAVY = (20, 20, 36)
DARK_SURFACE = (26, 26, 46)
GREEN_DARK = (31, 58, 46)
GREEN_MID = (45, 74, 62)
GREEN_LIGHT = (58, 94, 80)
GOLD = (201, 168, 76)
BRIGHT_GOLD = (232, 197, 71)
DARK_GOLD = (160, 120, 40)
BORDER = (42, 42, 64)


def hex_point(cx, cy, r, i):
    """Return (x, y) for vertex i of a flat-top hexagon centered at cx,cy."""
    angle = math.radians(60 * i - 30)
    return (cx + r * math.cos(angle), cy + r * math.sin(angle))


def draw_logo(size: int = SIZE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    R_outer = size * 0.46  # background circle
    R_hex = size * 0.33    # hexagon
    R_star = size * 0.17   # inner star
    R_node = size * 0.025  # connection nodes
    line_len = size * 0.1  # length of connecting lines beyond hex

    # Background circle
    draw.ellipse(
        [cx - R_outer, cy - R_outer, cx + R_outer, cy + R_outer],
        fill=NAVY,
        outline=BORDER,
        width=2,
    )

    # Outer gold ring
    draw.ellipse(
        [cx - R_outer + 4, cy - R_outer + 4, cx + R_outer - 4, cy + R_outer - 4],
        outline=GOLD + (76,),
        width=1,
    )

    # Hexagon vertices
    hex_pts = [hex_point(cx, cy, R_hex, i) for i in range(6)]

    # Connecting lines from hex vertices outward
    for i, (vx, vy) in enumerate(hex_pts):
        angle = math.radians(60 * i - 30)
        ex = cx + (R_hex + line_len) * math.cos(angle)
        ey = cy + (R_hex + line_len) * math.sin(angle)
        draw.line([vx, vy, ex, ey], fill=GOLD + (128,), width=3)

    # Connection endpoint circles
    for i in range(6):
        angle = math.radians(60 * i - 30)
        nx = cx + (R_hex + line_len) * math.cos(angle)
        ny = cy + (R_hex + line_len) * math.sin(angle)
        draw.ellipse(
            [nx - R_node, ny - R_node, nx + R_node, ny + R_node],
            fill=GREEN_DARK,
            outline=GOLD + (180,),
            width=2,
        )

    # Main hexagon
    draw.polygon(hex_pts, fill=GREEN_DARK, outline=GOLD, width=4)

    # Inner hex highlight (smaller)
    inner_pts = [hex_point(cx, cy, R_hex * 0.82, i) for i in range(6)]
    draw.polygon(inner_pts, fill=GREEN_MID, outline=GOLD + (60,), width=1)

    # Gold star in center
    star_pts = []
    for i in range(10):
        angle = math.radians(36 * i - 90)
        r = R_star if i % 2 == 0 else R_star * 0.45
        star_pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(star_pts, fill=BRIGHT_GOLD, outline=DARK_GOLD, width=1)

    # Inner glow dot
    draw.ellipse(
        [cx - R_star * 0.3, cy - R_star * 0.3, cx + R_star * 0.3, cy + R_star * 0.3],
        fill=BRIGHT_GOLD + (60,),
    )

    return img


def main():
    img = draw_logo()

    png_path = ASSETS / "logo.png"
    img.save(png_path, format="PNG")
    print(f"  {png_path}")

    # Generate ICO with multiple sizes
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = ASSETS / "logo.ico"
    img.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"  {ico_path}")

    # Also save resized PNGs for various uses
    for s in [16, 32, 64, 128]:
        resized = img.resize((s, s), Image.LANCZOS)
        out = ASSETS / f"logo_{s}.png"
        resized.save(out, format="PNG")
        print(f"  {out}")

    print("Done.")


if __name__ == "__main__":
    main()
