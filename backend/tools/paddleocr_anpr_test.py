"""
SmartPark ANPR - PaddleOCR isolated proof-of-concept.

This file deliberately does NOT modify SmartPark application code.
It lets us benchmark PaddleOCR against a saved camera frame before
integrating it into the ANPR simulator.

Usage:
    python tools/paddleocr_anpr_test.py path\to\capture.jpg

The script runs several image variants through PaddleOCR and prints
all detected text, confidence, and a Kenyan-style 3-3-1 candidate.
"""

from __future__ import annotations

import os
import re
import sys

# PaddlePaddle 3.3.x currently has a CPU oneDNN/PIR inference bug that can
# raise ConvertPirAttribute2RuntimeAttribute for PP-OCR models. Disable both
# paths before importing PaddleOCR so this isolated benchmark can run on CPU.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from paddleocr import PaddleOCR


PLATE_PATTERN = re.compile(r"^[A-Z]{3}[0-9]{3}[A-Z]$")

# Common OCR confusions for a constrained plate alphabet.
CONFUSIONS = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "Z": "2",
        "S": "5",
        "G": "6",
        "B": "8",
    }
)


def normalize_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def plate_candidates(text: str) -> list[str]:
    compact = normalize_text(text)
    candidates = [compact]

    if len(compact) == 7:
        candidates.append(compact[:3] + compact[3:6] + compact[6:])

    # Try position-aware OCR correction only when the 3-3-1 shape is met.
    if len(compact) == 7:
        chars = list(compact)
        for index in (3, 4, 5):
            chars[index] = chars[index].translate(CONFUSIONS)
        candidate = "".join(chars)
        candidates.append(candidate)

    return list(dict.fromkeys(candidates))


def best_plate(text: str) -> str | None:
    for candidate in plate_candidates(text):
        if PLATE_PATTERN.fullmatch(candidate):
            return candidate
    return None


def make_variants(image: Image.Image) -> list[tuple[str, np.ndarray]]:
    rgb = image.convert("RGB")

    gray = ImageOps.grayscale(rgb)
    gray = ImageOps.autocontrast(gray)

    # Keep three channels because PaddleOCR's image pipeline expects
    # a normal image array rather than a single-channel image.
    gray_rgb = Image.merge("RGB", (gray, gray, gray))

    contrast = ImageEnhance.Contrast(gray_rgb).enhance(2.2)
    sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)

    # A deliberately strong threshold variant for faint handwriting.
    threshold = gray.point(lambda p: 255 if p > 165 else 0)
    threshold_rgb = Image.merge("RGB", (threshold, threshold, threshold))

    variants = [
        ("original", rgb),
        ("autocontrast", gray_rgb),
        ("contrast_sharp", sharp),
        ("threshold", threshold_rgb),
    ]

    return [
        (name, np.asarray(img))
        for name, img in variants
    ]


def extract_result(result) -> tuple[list[str], list[float]]:
    """
    PaddleOCR 3.x exposes the structured result through the `json`
    property. Keep a defensive fallback so minor result-object
    changes don't make this diagnostic unusable.
    """
    data = getattr(result, "json", None)

    if callable(data):
        data = data()

    if isinstance(data, str):
        import json
        data = json.loads(data)

    if isinstance(data, dict) and "res" in data:
        data = data["res"]

    if not isinstance(data, dict):
        return [], []

    texts = data.get("rec_texts") or []
    scores = data.get("rec_scores") or []

    return (
        [str(value) for value in texts],
        [float(value) for value in scores],
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python tools/paddleocr_anpr_test.py "
            "path\\to\\capture.jpg"
        )
        return 2

    image_path = Path(sys.argv[1])

    if not image_path.is_file():
        print(f"ERROR: Image not found: {image_path}")
        return 2

    try:
        image = Image.open(image_path)
        image.load()
    except Exception as exc:
        print(f"ERROR: Could not open image: {exc}")
        return 2

    print("=" * 72)
    print("SmartPark ANPR — PaddleOCR isolated benchmark")
    print("=" * 72)
    print(f"Image: {image_path}")
    print(f"Size : {image.width} x {image.height}")
    print()

    print("Loading PaddleOCR...")
    ocr = PaddleOCR(
        lang="en",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )

    all_hits: list[tuple[str, str, float]] = []

    for variant_name, image_array in make_variants(image):
        print()
        print(f"--- {variant_name} ---")

        try:
            results = ocr.predict(image_array)

            variant_found = False

            for result in results:
                texts, scores = extract_result(result)

                for text, score in zip(texts, scores):
                    variant_found = True
                    print(f"  {text!r}  confidence={score:.4f}")
                    all_hits.append((variant_name, text, score))

                    plate = best_plate(text)
                    if plate:
                        print(f"  >>> PLATE CANDIDATE: {plate}")

            if not variant_found:
                print("  No text detected.")

        except Exception as exc:
            print(f"  OCR ERROR: {type(exc).__name__}: {exc}")

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)

    candidates: list[tuple[str, str, float]] = []

    for variant_name, text, score in all_hits:
        plate = best_plate(text)
        if plate:
            candidates.append((plate, variant_name, score))

    if candidates:
        candidates.sort(key=lambda item: item[2], reverse=True)
        print("Plate candidates:")
        for plate, variant_name, score in candidates:
            print(
                f"  {plate} | {variant_name} | "
                f"confidence={score:.4f}"
            )
        print()
        print(f"BEST CANDIDATE: {candidates[0][0]}")
    else:
        print("No Kenyan-style 3-3-1 plate candidate was produced.")

    print()
    print("This is an isolated OCR test only.")
    print("No SmartPark session, reservation, payment, or database")
    print("operation is performed by this script.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
