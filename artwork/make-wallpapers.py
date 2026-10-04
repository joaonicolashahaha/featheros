#!/usr/bin/env python3
"""Generate the FeatherOS wallpapers (original artwork, CC0).

Soft overlapping colour fields with a few gentle "feather" curves.
Output: archiso/airootfs/usr/share/featheros/wallpapers/{light,dark}.jpg

    python3 artwork/make-wallpapers.py      (needs python-numpy, python-pillow)
"""
import os

import numpy as np
from PIL import Image

W, H = 1920, 1200          # 16:10, like the laptop's 1280x800 panel
OUT = os.path.join(os.path.dirname(__file__), "..", "archiso", "airootfs",
                   "usr", "share", "featheros", "wallpapers")

y, x = np.mgrid[0:H, 0:W].astype(np.float32)
x /= W
y /= H


def blob(cx, cy, rx, ry):
    return np.exp(-(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2))


def band(a, b, c, width):
    """Soft band along the curve y = a*x^2 + b*x + c."""
    d = y - (a * x * x + b * x + c)
    return np.exp(-(d / width) ** 2)


def render(base, fields, curve_color, curve_alpha):
    img = np.empty((H, W, 3), np.float32)
    img[:] = base
    for color, weight in fields:
        img += (np.array(color, np.float32) - img) * weight[..., None]
    for a, b, c, w in [(-0.55, 0.95, 0.38, 0.06), (-0.45, 0.80, 0.52, 0.035),
                       (-0.60, 1.05, 0.62, 0.02)]:
        img += (np.array(curve_color, np.float32) - img) * \
            (curve_alpha * band(a, b, c, w))[..., None]
    # A touch of noise prevents banding on 6-bit laptop panels.
    rng = np.random.default_rng(7)
    img += rng.normal(0, 1.2, img.shape).astype(np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


light = render(
    (236, 240, 248),
    [((140, 200, 250), 0.85 * blob(0.15, 0.20, 0.45, 0.55)),
     ((180, 160, 245), 0.70 * blob(0.85, 0.30, 0.40, 0.50)),
     ((255, 200, 170), 0.65 * blob(0.60, 0.95, 0.50, 0.40))],
    (255, 255, 255), 0.45)
dark = render(
    (14, 18, 34),
    [((30, 80, 150), 0.85 * blob(0.15, 0.20, 0.45, 0.55)),
     ((75, 45, 130), 0.75 * blob(0.85, 0.30, 0.40, 0.50)),
     ((140, 70, 80), 0.55 * blob(0.60, 0.95, 0.50, 0.40))],
    (120, 170, 255), 0.22)

os.makedirs(OUT, exist_ok=True)
light.save(os.path.join(OUT, "light.jpg"), quality=90, optimize=True)
dark.save(os.path.join(OUT, "dark.jpg"), quality=90, optimize=True)
print("wrote", OUT)
