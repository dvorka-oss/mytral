#!/usr/bin/env python3
"""Generate 3 Snapcraft feature banners for MyTraL at 2160x720 (3:1)."""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 2160, 720
FONT_BOLD = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
FONT_REG = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"
FONT_MONO = "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf"
IMG = "/home/dvorka/p/mytral/git/mytral/webs/www.mytral.fitness/images/"
ROOT = "/home/dvorka/p/mytral/git/mytral/webs/www.mytral.fitness/"
OUT = "/home/dvorka/p/mytral/git/mytral/media/banners/"

MAX_BYTES = 2 * 1024 * 1024


def hgrad(c1, c2, w=W, h=H):
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        t = x / max(w - 1, 1)
        arr[:, x] = [round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)]
    return Image.fromarray(arr, "RGB").convert("RGBA")


def hgrad3(c1, c2, c3, w=W, h=H):
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    mid = w // 2
    for x in range(w):
        if x <= mid:
            t = x / mid
            src, dst = c1, c2
        else:
            t = (x - mid) / max(w - mid, 1)
            src, dst = c2, c3
        arr[:, x] = [round(src[i] + (dst[i] - src[i]) * t) for i in range(3)]
    return Image.fromarray(arr, "RGB").convert("RGBA")


def load_img(path, target_h, rotate=0):
    img = Image.open(path).convert("RGBA")
    scale = target_h / img.height
    img = img.resize((int(img.width * scale), target_h), Image.LANCZOS)
    if rotate:
        img = img.rotate(rotate, expand=True, resample=Image.BICUBIC)
    return img


def with_shadow(canvas, img, x, y, offset=18, blur=22, alpha=155):
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mask = img.split()[3]
    shadow_img = Image.new("RGBA", img.size, (0, 0, 0, alpha))
    shadow.paste(shadow_img, (x + offset, y + offset), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(img, (x, y), img)
    return canvas


def t(draw, text, x, y, font_path, size, color):
    draw.text((x, y), text, font=ImageFont.truetype(font_path, size), fill=color)


def save(canvas, name):
    path_png = OUT + name + ".png"
    canvas.convert("RGB").save(path_png, "PNG", optimize=True, compress_level=9)
    sz = os.path.getsize(path_png)
    if sz > MAX_BYTES:
        path_jpg = OUT + name + ".jpg"
        canvas.convert("RGB").save(path_jpg, "JPEG", quality=88, optimize=True)
        os.remove(path_png)
        print(f"  {name}.jpg  {os.path.getsize(path_jpg)//1024} KB")
    else:
        print(f"  {name}.png  {sz//1024} KB")

#
# Banner: Train Smarter — athletic, purple-to-crimson, radar science
#
def banner3_train_smarter():
    canvas = hgrad3((14, 10, 44), (48, 14, 84), (128, 24, 44))
    draw = ImageDraw.Draw(canvas)

    # radar concentric circles + radial lines (decorative)
    cx, cy = 1560, 360
    for radius in range(70, 780, 65):
        opacity = max(7, 28 - radius // 32)
        draw.ellipse(
            [(cx - radius, cy - radius), (cx + radius, cy + radius)],
            outline=(255, 140, 50, opacity),
            width=1,
        )
    for deg in range(0, 360, 20):
        rad = math.radians(deg)
        draw.line(
            [(cx, cy), (int(cx + 780 * math.cos(rad)), int(cy + 780 * math.sin(rad)))],
            fill=(255, 140, 50, 10),
            width=1,
        )

    # radar + trimp screenshots overlapping
    img_trimp = load_img(IMG + "feature.trimp.png", 500, rotate=-4)
    img_radar = load_img(IMG + "feature.radar.png", 572, rotate=5)

    x_radar = W - img_radar.width - 14
    x_trimp = x_radar - img_trimp.width + 96

    canvas = with_shadow(canvas, img_trimp, x_trimp, (H - img_trimp.height) // 2 + 28)
    canvas = with_shadow(canvas, img_radar, x_radar, (H - img_radar.height) // 2 - 18, alpha=140)

    draw = ImageDraw.Draw(canvas)

    logo = load_img(ROOT + "mytral-logo.png", 76)
    canvas.paste(logo, (88, 50), logo)
    draw = ImageDraw.Draw(canvas)

    t(draw, "Train Smarter.", 88, 158, FONT_BOLD, 100, (255, 255, 255, 255))
    t(draw, "Not Just Harder", 90, 270, FONT_BOLD, 100, (251, 115, 22, 255))

    t(draw, "Sovereign athlete training log", 93, 404, FONT_REG, 32, (178, 138, 220, 215))
    t(draw, "for deeper insights & smarter progress", 93, 448, FONT_REG, 32, (178, 138, 220, 215))

    # orange divider line
    draw.rectangle([(88, 518), (690, 522)], fill=(251, 115, 22, 180))
    t(draw, "mytral.fitness", 93, 535, FONT_REG, 25, (178, 138, 220, 168))

    save(canvas, "banner-train-smarter-purple")


#
# Banner variant: same content, website dark-navy color scheme
#
def banner3_train_smarter_web():
    # bg matches website: --darker #020617 → --bg #0f172a → --card-bg #1e293b
    canvas = hgrad3((2, 6, 23), (12, 19, 40), (24, 32, 58))

    # blue radial glow at 20 % left / 50 % height (body::before, primary #0ea5e9, 15 % opacity)
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [(int(W * 0.20) - 400, H // 2 - 400), (int(W * 0.20) + 400, H // 2 + 400)],
        fill=(14, 165, 233, 38),
    )
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(110)))

    # purple radial glow at 80 % right / 80 % height (body::before, secondary #8b5cf6, 15 % opacity)
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [(int(W * 0.80) - 400, int(H * 0.80) - 400), (int(W * 0.80) + 400, int(H * 0.80) + 400)],
        fill=(139, 92, 246, 38),
    )
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(110)))

    # radar concentric circles + radial lines in primary blue
    draw = ImageDraw.Draw(canvas)
    cx, cy = 1560, 360
    for radius in range(70, 780, 65):
        opacity = max(7, 28 - radius // 32)
        draw.ellipse(
            [(cx - radius, cy - radius), (cx + radius, cy + radius)],
            outline=(14, 165, 233, opacity),
            width=1,
        )
    for deg in range(0, 360, 20):
        rad = math.radians(deg)
        draw.line(
            [(cx, cy), (int(cx + 740 * math.cos(rad)), int(cy + 780 * math.sin(rad)))],
            fill=(14, 165, 233, 10),
            width=1,
        )

    # radar + trimp screenshots overlapping (same layout as original)
    img_trimp = load_img(IMG + "feature.trimp.png", 500, rotate=-4)
    img_radar = load_img(IMG + "feature.radar.png", 572, rotate=5)

    x_radar = W - img_radar.width - 14
    x_trimp = x_radar - img_trimp.width + 96

    canvas = with_shadow(canvas, img_trimp, x_trimp, (H - img_trimp.height) // 2 + 28)
    canvas = with_shadow(canvas, img_radar, x_radar, (H - img_radar.height) // 2 - 18, alpha=140)

    draw = ImageDraw.Draw(canvas)
    logo = load_img(ROOT + "mytral-logo.png", 76)
    canvas.paste(logo, (88, 50), logo)
    draw = ImageDraw.Draw(canvas)

    # white headline, primary-blue second line — mirrors hero gradient direction
    t(draw, "Train Smarter.", 88, 158, FONT_BOLD, 100, (255, 255, 255, 255))
    t(draw, "Not Just Harder", 90, 270, FONT_BOLD, 100, (14, 165, 233, 255))

    # --light-gray #cbd5e1 subtitle
    t(draw, "Sovereign athlete training log", 93, 404, FONT_REG, 32, (203, 213, 225, 215))
    t(draw, "for deeper insights & smarter progress", 93, 448, FONT_REG, 32, (203, 213, 225, 215))

    # primary-blue divider, --gray #64748b url
    draw.rectangle([(88, 518), (690, 522)], fill=(14, 165, 233, 180))
    t(draw, "mytral.fitness", 93, 535, FONT_REG, 25, (100, 116, 139, 168))

    save(canvas, "banner-train-smarter")


os.makedirs(OUT, exist_ok=True)
print("Generating banners...")
# banner3_train_smarter()
banner3_train_smarter_web()
print("Done.")
