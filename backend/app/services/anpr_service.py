"""
SmartPark ANPR OCR service.

This service provides isolated Kenyan vehicle-registration recognition using
PaddleOCR. It intentionally performs OCR only; it does not create parking
sessions, reservations, payments, or database records.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from dataclasses import dataclass
from io import BytesIO
from typing import Any

# PaddlePaddle 3.3.x can hit a CPU oneDNN/PIR runtime-attribute error with
# PP-OCR models. These flags must be set before PaddleOCR/PaddlePaddle is
# imported so the local CPU inference path remains stable.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


PLATE_PATTERN = re.compile(r"^[A-Z]{3}[0-9]{3}[A-Z]$")

# Conservative OCR substitutions used only when a 7-character candidate has
# the Kenyan 3-3-1 shape. This prevents arbitrary prose from being rewritten
# into a plate value.
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


@dataclass(frozen=True)
class OCRHit:
    variant: str
    text: str
    confidence: float
    plate: str | None


@dataclass(frozen=True)
class ANPRResult:
    registration: str | None
    confidence: float | None
    variant: str | None
    formatted_registration: str | None
    candidates: list[dict[str, Any]]
    detections: list[dict[str, Any]]


class ANPRService:
    """Thread-safe, lazily initialized PaddleOCR service."""

    _ocr: Any = None
    _ocr_lock = threading.Lock()
    _inference_lock = threading.Lock()

    max_image_bytes = 10 * 1024 * 1024
    max_image_dimension = 1280
    minimum_plate_confidence = 0.70

    @classmethod
    def _get_ocr(cls) -> Any:
        if cls._ocr is not None:
            return cls._ocr

        with cls._ocr_lock:
            if cls._ocr is None:
                try:
                    from paddleocr import PaddleOCR
                except ImportError as exc:
                    raise RuntimeError(
                        "PaddleOCR is not installed. Install the backend OCR "
                        "dependencies before using ANPR recognition."
                    ) from exc

                cls._ocr = PaddleOCR(
                    lang="en",
                    device="cpu",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    enable_mkldnn=False,
                )

        return cls._ocr

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", value.upper())

    @classmethod
    def _best_plate(cls, text: str) -> str | None:
        compact = cls._normalize_text(text)

        if PLATE_PATTERN.fullmatch(compact):
            return compact

        # Only attempt constrained character correction for exactly seven
        # alphanumeric characters. The position rules mirror the Kenyan
        # 3-letter / 3-digit / 1-letter registration format used by SmartPark.
        if len(compact) != 7:
            return None

        chars = list(compact)
        for index in (0, 1, 2, 6):
            # Do not force a correction into a character unless the OCR output
            # is one of the known ambiguous symbols.
            chars[index] = chars[index].translate(
                str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"})
            )
        for index in (3, 4, 5):
            chars[index] = chars[index].translate(CONFUSIONS)

        candidate = "".join(chars)
        return candidate if PLATE_PATTERN.fullmatch(candidate) else None

    @classmethod
    def _make_variants(cls, image: Image.Image) -> list[tuple[str, np.ndarray]]:
        rgb = image.convert("RGB")

        # Camera frames are normally small. Cap unusually large uploads to
        # protect CPU inference time while preserving aspect ratio.
        largest = max(rgb.width, rgb.height)
        if largest > cls.max_image_dimension:
            scale = cls.max_image_dimension / largest
            rgb = rgb.resize(
                (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
                Image.Resampling.LANCZOS,
            )

        gray = ImageOps.grayscale(rgb)
        gray = ImageOps.autocontrast(gray)
        gray_rgb = Image.merge("RGB", (gray, gray, gray))

        contrast = ImageEnhance.Contrast(gray_rgb).enhance(2.2)
        sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)

        threshold = gray.point(lambda pixel: 255 if pixel > 165 else 0)
        threshold_rgb = Image.merge("RGB", (threshold, threshold, threshold))

        # CPU performance matters for live operator ANPR. The benchmark showed
        # that autocontrast and contrast+sharp are the two successful variants
        # for the target handwriting. Keep original and threshold as fallback
        # strategies rather than running all four for every camera capture.
        variants = [
            ("autocontrast", gray_rgb),
            ("contrast_sharp", sharp),
            ("original", rgb),
            ("threshold", threshold_rgb),
        ]

        return [(name, np.asarray(img)) for name, img in variants]

    @staticmethod
    def _extract_result(result: Any) -> tuple[list[str], list[float]]:
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

    @classmethod
    def _recognize_sync(cls, image: Image.Image) -> ANPRResult:
        ocr = cls._get_ocr()
        hits: list[OCRHit] = []
        detections: list[dict[str, Any]] = []

        # PaddleOCR CPU inference is computationally heavy. Serialize model
        # calls so simultaneous operator captures do not contend for the same
        # model instance or exhaust the host CPU.
        with cls._inference_lock:
            for variant_name, image_array in cls._make_variants(image):
                results = ocr.predict(image_array)

                variant_hits: list[OCRHit] = []

                for result in results:
                    texts, scores = cls._extract_result(result)
                    for text, score in zip(texts, scores):
                        score = max(0.0, min(1.0, float(score)))
                        plate = cls._best_plate(text)
                        hit = OCRHit(
                            variant=variant_name,
                            text=text,
                            confidence=score,
                            plate=plate,
                        )
                        variant_hits.append(hit)
                        hits.append(hit)
                        detections.append(
                            {
                                "variant": variant_name,
                                "text": text,
                                "confidence": round(score, 4),
                                "plate": plate,
                            }
                        )

                # Fast path: the first successful preprocessing variant is
                # sufficient for a live ANPR admission decision. The next
                # variants remain fallbacks for difficult captures. This
                # avoids four expensive CPU PaddleOCR passes on every request.
                if any(
                    hit.plate is not None
                    and hit.confidence >= cls.minimum_plate_confidence
                    for hit in variant_hits
                ):
                    break

        candidates = [
            hit
            for hit in hits
            if hit.plate is not None
            and hit.confidence >= cls.minimum_plate_confidence
        ]

        if not candidates:
            return ANPRResult(
                registration=None,
                confidence=None,
                variant=None,
                formatted_registration=None,
                candidates=[],
                detections=detections,
            )

        # Prefer repeated agreement across preprocessing variants, then the
        # strongest confidence. This prevents a single noisy variant from
        # winning when multiple variants agree on the same plate.
        grouped: dict[str, list[OCRHit]] = {}
        for hit in candidates:
            assert hit.plate is not None
            grouped.setdefault(hit.plate, []).append(hit)

        ranked = sorted(
            grouped.items(),
            key=lambda item: (
                len(item[1]),
                max(hit.confidence for hit in item[1]),
                sum(hit.confidence for hit in item[1]) / len(item[1]),
            ),
            reverse=True,
        )

        registration, matching_hits = ranked[0]
        best_hit = max(matching_hits, key=lambda hit: hit.confidence)
        confidence = best_hit.confidence

        candidate_summary = []
        for plate, plate_hits in ranked:
            best = max(plate_hits, key=lambda hit: hit.confidence)
            candidate_summary.append(
                {
                    "registration": plate,
                    "confidence": round(best.confidence, 4),
                    "variant": best.variant,
                    "agreement_count": len(plate_hits),
                }
            )

        return ANPRResult(
            registration=registration,
            confidence=confidence,
            variant=best_hit.variant,
            formatted_registration=(
                f"{registration[:3]} {registration[3:6]} {registration[6]}"
            ),
            candidates=candidate_summary,
            detections=detections,
        )

    @classmethod
    async def recognize(cls, image_bytes: bytes) -> ANPRResult:
        if not image_bytes:
            raise ValueError("The uploaded image is empty.")

        if len(image_bytes) > cls.max_image_bytes:
            raise ValueError("The ANPR image must not exceed 10 MB.")

        try:
            image = Image.open(BytesIO(image_bytes))
            image.load()
        except Exception as exc:
            raise ValueError("The uploaded file is not a valid image.") from exc

        # Run CPU-bound PaddleOCR outside the asyncio event loop.
        return await asyncio.to_thread(cls._recognize_sync, image)
