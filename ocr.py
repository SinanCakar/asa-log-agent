"""OCR pipeline shared by the live agent and the synthetic feasibility harness.

Kept separate so capture (mss), parsing (logparse) and OCR each stay testable in
isolation. Preprocessing favors the ARK tribe-log look: light text on a dark,
semi-transparent panel. Heavy deps (Pillow, pytesseract) are imported lazily so
logparse/tests run on machines without them.
"""
from __future__ import annotations

from typing import Optional


def preprocess(img):
    """Return a binarized, upscaled grayscale PIL image tuned for light-on-dark UI text.

    Steps: grayscale -> 2x upscale (helps small UI fonts) -> autocontrast ->
    invert (tesseract prefers dark-on-light) -> threshold.
    """
    from PIL import Image, ImageOps

    g = img.convert("L")
    g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    g = ImageOps.autocontrast(g)
    g = ImageOps.invert(g)
    # Binarize: pixels below midpoint -> black text, rest white.
    g = g.point(lambda p: 0 if p < 140 else 255)
    return g


def image_to_text(img, tesseract_path: Optional[str] = None, lang: str = "eng",
                  do_preprocess: bool = True) -> str:
    """Run tesseract on a PIL image and return raw text."""
    import pytesseract

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    if do_preprocess:
        img = preprocess(img)
    # psm 6: assume a uniform block of text (the log panel is exactly that).
    return pytesseract.image_to_string(img, lang=lang, config="--psm 6")


def grab_region(region):
    """Capture a screen region (x, y, w, h) as a PIL image using mss."""
    import mss
    from PIL import Image

    x, y, w, h = region
    with mss.mss() as sct:
        shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
    return Image.frombytes("RGB", shot.size, shot.rgb)
