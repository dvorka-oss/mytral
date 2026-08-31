#!/usr/bin/env python3
"""
Generate SEO / social assets for mytral.mindforger.com

Outputs (into the site root):
  - og-image.png : a 1200x630 landscape card, the format social networks and
                   product directories scrape for link previews and listings.
  - favicon.ico  : a multi-size icon browsers and directories request by default.

The visual language (navy gradient, blue/purple glows, radar motif, fonts)
mirrors media/banners/make_banners.py so all MyTraL artwork stays consistent.
"""

import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
WWW = REPO_ROOT / "webs" / "mytral.mindforger.com"
IMAGES = WWW / "images"

FONT_BOLD = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
FONT_REG = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"

OG_W, OG_H = 1200, 630
FAVICON_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64)]


def hgrad3(c1, c2, c3, w, h):
    """Horizontal 3-stop gradient as an RGBA image."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    mid = w // 2
    for x in range(w):
        if x <= mid:
            factor = x / mid
            src, dst = c1, c2
        else:
            factor = (x - mid) / max(w - mid, 1)
            src, dst = c2, c3
        arr[:, x] = [round(src[i] + (dst[i] - src[i]) * factor) for i in range(3)]
    return Image.fromarray(arr).convert("RGBA")


def radial_glow(canvas, cx, cy, radius, color, blur=90):
    """Composite a soft radial glow onto the canvas."""
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)], fill=color
    )
    return Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(blur)))


def load_img(path, target_h, rotate=0):
    """Load an image scaled to target height, optionally rotated."""
    img = Image.open(path).convert("RGBA")
    scale = target_h / img.height
    img = img.resize((int(img.width * scale), target_h), Image.LANCZOS)
    if rotate:
        img = img.rotate(rotate, expand=True, resample=Image.BICUBIC)
    return img


def with_shadow(canvas, img, x, y, offset=14, blur=20, alpha=150):
    """Paste an image with a soft drop shadow."""
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_img = Image.new("RGBA", img.size, (0, 0, 0, alpha))
    shadow.paste(shadow_img, (x + offset, y + offset), img.split()[3])
    canvas = Image.alpha_composite(
        canvas, shadow.filter(ImageFilter.GaussianBlur(blur))
    )
    canvas.paste(img, (x, y), img)
    return canvas


def text(draw, string, x, y, font_path, size, color):
    """Draw text with a truetype font."""
    draw.text((x, y), string, font=ImageFont.truetype(font_path, size), fill=color)


def make_og_image():
    """Render the 1200x630 Open Graph card."""
    canvas = hgrad3((2, 6, 23), (12, 19, 40), (24, 32, 58), OG_W, OG_H)
    canvas = radial_glow(
        canvas, int(OG_W * 0.16), int(OG_H * 0.32), 300, (14, 165, 233, 60)
    )
    canvas = radial_glow(
        canvas, int(OG_W * 0.84), int(OG_H * 0.85), 300, (139, 92, 246, 60)
    )

    # radar concentric circles behind the screenshot
    draw = ImageDraw.Draw(canvas)
    cx, cy = 940, 315
    for radius in range(50, 430, 42):
        opacity = max(6, 24 - radius // 30)
        draw.ellipse(
            [(cx - radius, cy - radius), (cx + radius, cy + radius)],
            outline=(14, 165, 233, opacity),
            width=1,
        )

    # product screenshot, right side
    shot = load_img(IMAGES / "feature.radar.png", 360, rotate=4)
    x_shot = OG_W - shot.width - 40
    canvas = with_shadow(canvas, shot, x_shot, (OG_H - shot.height) // 2 - 6, alpha=150)

    # logo + wordmark, top left
    draw = ImageDraw.Draw(canvas)
    logo = load_img(WWW / "mytral-logo.png", 60)
    canvas.paste(logo, (60, 52), logo)
    draw = ImageDraw.Draw(canvas)
    text(draw, "MyTraL", 134, 60, FONT_BOLD, 44, (255, 255, 255, 255))

    # headline
    text(draw, "Train Smarter.", 60, 178, FONT_BOLD, 70, (255, 255, 255, 255))
    text(draw, "Not Just Harder", 62, 258, FONT_BOLD, 70, (14, 165, 233, 255))

    # tagline
    text(
        draw,
        "Private, open-source athlete training log",
        63,
        368,
        FONT_REG,
        25,
        (203, 213, 225, 220),
    )
    text(
        draw,
        "for deeper insights and smarter progress",
        63,
        405,
        FONT_REG,
        25,
        (203, 213, 225, 220),
    )

    # divider + url
    draw.rectangle([(63, 466), (470, 470)], fill=(14, 165, 233, 180))
    text(draw, "mytral.mindforger.com", 63, 482, FONT_REG, 24, (100, 116, 139, 210))

    out = WWW / "og-image.png"
    canvas.convert("RGB").save(out, "PNG", optimize=True, compress_level=9)
    print(f"  og-image.png  {OG_W}x{OG_H}  {out.stat().st_size // 1024} KB")


def make_favicon():
    """Render a multi-size favicon.ico from the site logo."""
    logo = Image.open(WWW / "mytral-logo.png").convert("RGBA")
    out = WWW / "favicon.ico"
    logo.save(out, sizes=FAVICON_SIZES)
    print(f"  favicon.ico   {out.stat().st_size // 1024} KB")


def main():
    print("Generating SEO assets...")
    make_og_image()
    make_favicon()
    print("Done.")


if __name__ == "__main__":
    main()
