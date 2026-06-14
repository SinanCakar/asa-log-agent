#!/usr/bin/env python3
"""Synthetic OCR feasibility harness — the Linux-side proof for Faz 9.1.

Renders realistic ARK tribe-log lines onto a dark, semi-transparent-style panel
(light text), runs the REAL ocr.py + logparse.py pipeline over the image, and
reports how many lines were recovered and correctly classified.

This is NOT the final decision gate — that needs the player's real game screen.
It validates that the preprocessing + OCR + parse chain works end to end and
gives a baseline accuracy on clean synthetic text.

Run:  python tests/make_synth.py
Needs: Pillow, pytesseract, and a tesseract binary on PATH (or TESSERACT env).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logparse  # noqa: E402
import ocr  # noqa: E402

# (line text, expected category)
SAMPLES = [
    ("Day 12345, 09:14:22: Your 'Metal Wall' was destroyed!", "raid"),
    ("Day 12345, 09:15:01: Tribemember Bob - Lvl 105 was killed by Alpha Raptor - Lvl 220!", "kill"),
    ("Day 12345, 10:00:00: Carl was added to the Tribe!", "member"),
    ("Day 12345, 11:30:00: Tribemember Dana - Lvl 88 Tamed a Raptor - Lvl 5!", "tame"),
    ("Day 12345, 12:00:00: Eve demolished a 'Stone Foundation'!", "raid"),
    ("Day 12346, 01:05:10: Your 'Tek Gateway' was destroyed (Red Tribe)!", "raid"),
    ("Day 12346, 02:00:00: Frank was removed from the Tribe!", "member"),
    ("Day 12346, 03:20:00: Grace claimed 'Argentavis'!", "claim"),
]

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int):
    from PIL import ImageFont

    for path in FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render(lines: list[str]) -> "object":
    from PIL import Image, ImageDraw

    font = _font(22)
    pad, lh, w = 20, 34, 1100
    h = pad * 2 + lh * len(lines)
    # Dark panel, light text — ARK tribe-log style.
    img = Image.new("RGB", (w, h), (18, 20, 24))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((pad, pad + i * lh), ln, fill=(220, 224, 230), font=font)
    return img


def main() -> int:
    tpath = os.environ.get("TESSERACT") or None
    texts = [s[0] for s in SAMPLES]
    img = render(texts)
    out_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth_log.png")
    img.save(out_png)

    raw = ocr.image_to_text(img, tpath)
    print("=== OCR raw text ===")
    print(raw)
    events = logparse.parse_text(raw)

    # Match recovered events back to expected samples by day+time.
    by_key = {(e.day, e.time): e for e in events}
    correct = recovered = 0
    print("\n=== per-line result ===")
    for text, expect in SAMPLES:
        ev_exp = logparse.parse_line(text)
        key = (ev_exp.day, ev_exp.time)
        got = by_key.get(key)
        if got:
            recovered += 1
            ok = got.category == expect
            correct += ok
            mark = "OK " if ok else "CAT"
            print(f"  [{mark}] {key} expect={expect} got={got.category}: {got.raw}")
        else:
            print(f"  [MISS] {key} expect={expect}: {text}")

    n = len(SAMPLES)
    print(f"\nRecovered {recovered}/{n} lines ({100*recovered//n}%), "
          f"correct category {correct}/{n} ({100*correct//n}%)")
    print(f"Image: {out_png}")
    # Feasibility gate: >=90% lines recovered AND classified correctly.
    return 0 if correct >= 0.9 * n else 1


if __name__ == "__main__":
    sys.exit(main())
