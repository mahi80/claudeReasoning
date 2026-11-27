"""Compose the chat-UI figure from the browser test's screenshots.

Run from the repository root after:
    SCREENSHOT_DIR=docs/build/out/shots python tests/test_ui_browser.py
If the screenshots are missing, the committed docs/img/ui-flow.png is left as it is.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SHOTS = Path("docs/build/out/shots")
BG = (245, 246, 248)


def crop(name: str) -> Image.Image:
    """Cut the empty page area below the last piece of content."""
    image = Image.open(SHOTS / name).convert("RGB")
    pixels = np.asarray(image).astype(int)
    rows = np.where((np.abs(pixels - pixels[-5, 5]).sum(axis=2) > 12).any(axis=1))[0]
    return image.crop((0, 0, image.width, min(image.height, int(rows.max()) + 60)))


if not (SHOTS / "ui-approval.png").exists():
    print("no screenshots found; keeping the existing docs/img/ui-flow.png")
    sys.exit(0)

start, approval = crop("ui-starting-gpu.png"), crop("ui-approval.png")
plan = Image.open(SHOTS / "ui-plan.png").convert("RGB")
height = max(start.height + plan.height + 150, approval.height)
gap, pad = 70, 24
canvas = Image.new("RGB", (start.width + approval.width + gap + 2 * pad, height + 2 * pad),
                   "white")
draw = ImageDraw.Draw(canvas)
left = Image.new("RGB", (start.width, height), BG)
left.paste(start, (0, 0))
left.paste(plan, (32, start.height + 60))
right = Image.new("RGB", (approval.width, height), BG)
right.paste(approval, (0, 0))
x = pad
for panel in (left, right):
    canvas.paste(panel, (x, pad))
    draw.rectangle([x - 1, pad - 1, x + panel.width, pad + height],
                   outline=(170, 178, 190), width=2)
    x += panel.width + gap
canvas.save("docs/img/ui-flow.png")
print("wrote docs/img/ui-flow.png", canvas.size)
