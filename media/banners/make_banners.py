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


# ─── Banner 1: AI Coach — dark, futuristic, electric-blue ────────────────────
def banner1_ai_coach():
    canvas = hgrad((10, 14, 30), (22, 42, 90))
    draw = ImageDraw.Draw(canvas)

    # subtle diagonal speed-lines
    for i in range(-H, W + H, 68):
        draw.line([(i, 0), (i + H, H)], fill=(255, 255, 255, 11), width=1)

    # left vertical accent bar
    draw.rectangle([(72, 150), (76, 648)], fill=(79, 157, 232, 220))

    # two AI-coach screenshots overlapping, slightly rotated
    img_back = load_img(IMG + "feature.ai-coach.02.png", 530, rotate=-3)
    img_front = load_img(IMG + "feature.ai-coach.01.png", 598, rotate=4)

    x_front = W - img_front.width - 18
    x_back = x_front - img_back.width + 90

    canvas = with_shadow(canvas, img_back, x_back, (H - img_back.height) // 2 + 24)
    canvas = with_shadow(canvas, img_front, x_front, (H - img_front.height) // 2 - 22, offset=14)

    draw = ImageDraw.Draw(canvas)

    logo = load_img(ROOT + "mytral-logo.png", 74)
    canvas.paste(logo, (88, 50), logo)
    draw = ImageDraw.Draw(canvas)

    t(draw, "MyTraL", 88, 150, FONT_BOLD, 108, (255, 255, 255, 255))
    t(draw, "Your Personal AI", 88, 288, FONT_REG, 54, (96, 165, 250, 255))
    t(draw, "Fitness Coach", 88, 348, FONT_BOLD, 54, (96, 165, 250, 255))

    t(draw, "· AI coaching powered by Claude & GPT", 92, 444, FONT_REG, 27, (148, 163, 184, 220))
    t(draw, "· TRIMP · CTL · ATL · TSB science metrics", 92, 484, FONT_REG, 27, (148, 163, 184, 220))
    t(draw, "· 100% private — runs on your machine", 92, 524, FONT_REG, 27, (148, 163, 184, 220))

    t(draw, "mytral.fitness", 92, 636, FONT_REG, 25, (55, 85, 135, 170))

    save(canvas, "banner-ai-coach")


# ─── Banner 2: Matrix Rabbit — own your data, green hacker aesthetic ──────────
def banner2_matrix_rabbit():
    canvas = hgrad((3, 10, 3), (6, 26, 10))
    draw = ImageDraw.Draw(canvas)

    # matrix grid
    for x in range(0, W, 44):
        draw.line([(x, 0), (x, H)], fill=(0, 255, 65, 14), width=1)
    for y in range(0, H, 44):
        draw.line([(0, y), (W, y)], fill=(0, 255, 65, 14), width=1)

    # deterministic "rain" dots
    for i in range(320):
        rx = (i * 137 + i * i * 7) % W
        ry = (i * 97 + i * 31) % H
        alpha = 18 + (i * 41) % 90
        r = 1 + (i % 2)
        draw.ellipse([(rx - r, ry - r), (rx + r, ry + r)], fill=(0, 255, 65, alpha))

    # radial glow behind rabbit
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([(1390, 10), (2158, 710)], fill=(0, 180, 50, 45))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    canvas = Image.alpha_composite(canvas, glow)

    # matrix rabbit — green-tinted
    rabbit = Image.open(ROOT + "matrix-rabbit.png").convert("RGBA")
    rabbit = rabbit.resize((648, 648), Image.LANCZOS)
    rc, gc, bc, ac = rabbit.split()
    rc = rc.point(lambda p: int(p * 0.22))
    bc = bc.point(lambda p: int(p * 0.22))
    gc = gc.point(lambda p: min(255, int(p * 1.1 + 18)))
    canvas.paste(Image.merge("RGBA", (rc, gc, bc, ac)), (1490, 36), ac)

    draw = ImageDraw.Draw(canvas)

    # logo — green tinted
    logo = Image.open(ROOT + "mytral-logo.png").convert("RGBA")
    logo = logo.resize((70, 70), Image.LANCZOS)
    lr, lg, lb, la = logo.split()
    lr = lr.point(lambda p: int(p * 0.18))
    lb = lb.point(lambda p: int(p * 0.18))
    lg = lg.point(lambda p: min(255, int(p * 1.05 + 35)))
    canvas.paste(Image.merge("RGBA", (lr, lg, lb, la)), (88, 48), la)
    draw = ImageDraw.Draw(canvas)

    t(draw, "YOUR DATA.", 88, 150, FONT_BOLD, 130, (0, 255, 65, 255))
    t(draw, "YOUR RULES.", 88, 300, FONT_BOLD, 130, (255, 255, 255, 255))

    t(draw, "No cloud.  No subscriptions.", 92, 472, FONT_MONO, 33, (0, 205, 55, 205))
    t(draw, "No telemetry.  Open source.", 92, 518, FONT_MONO, 33, (0, 205, 55, 205))

    t(draw, "mytral.fitness", 92, 630, FONT_REG, 25, (0, 115, 30, 155))

    save(canvas, "banner-matrix-rabbit")


# ─── Banner 3: Train Smarter — athletic, purple-to-crimson, radar science ─────
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

    save(canvas, "banner-train-smarter")


os.makedirs(OUT, exist_ok=True)
print("Generating banners...")
banner1_ai_coach()
banner2_matrix_rabbit()
banner3_train_smarter()
print("Done.")
