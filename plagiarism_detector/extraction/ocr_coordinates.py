# -*- coding: utf-8 -*-
"""Validated OCR image-to-PDF geometry; no rectangle is guessed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OcrWordBox:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    char_start: int
    char_end: int


def image_bbox_to_pdf_rect(box: OcrWordBox, *, image_width: int, image_height: int,
                           page_rect: tuple[float, float, float, float], rotation: int = 0,
                           minimum_confidence: float = 55.0) -> Optional[dict]:
    """Map a TSV pixel box to the rendered PDF page coordinate system.

    The caller must provide the *rendered* page rectangle corresponding to the
    image. PyMuPDF rasterizes rotated pages in that basis, so no inverse guess
    is made. Invalid geometry, unsupported rotation and low confidence return
    ``None`` for a page-only fallback.
    """
    if rotation not in (0, 90, 180, 270) or image_width <= 0 or image_height <= 0:
        return None
    if not box.text.strip() or box.confidence < minimum_confidence:
        return None
    if box.width <= 0 or box.height <= 0 or box.left < 0 or box.top < 0:
        return None
    if box.left + box.width > image_width or box.top + box.height > image_height:
        return None
    x0, y0, x1, y1 = page_rect
    if x1 <= x0 or y1 <= y0:
        return None
    sx, sy = (x1 - x0) / image_width, (y1 - y0) / image_height
    rect = {'x0': x0 + box.left * sx, 'y0': y0 + box.top * sy,
            'x1': x0 + (box.left + box.width) * sx, 'y1': y0 + (box.top + box.height) * sy,
            'coordinate_basis': 'rendered_page', 'rotation': rotation}
    if rect['x1'] <= rect['x0'] or rect['y1'] <= rect['y0']:
        return None
    return rect
