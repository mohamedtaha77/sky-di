"""Turn an uploaded file into page images and draw Document Intelligence polygons on them."""

from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageDraw

DPI = 150
BLUE = (37, 99, 235)
KIND_COLOR = {"line": (56, 189, 248), "field": (5, 150, 105), "kv": (99, 102, 241), "table": (245, 158, 11)}


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def page_images(data: bytes) -> list[Image.Image]:
    """One RGB image per page. PDFs are rasterised at 150 DPI; images use their first frame."""
    if is_pdf(data):
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return [Image.open(io.BytesIO(p.get_pixmap(dpi=DPI).tobytes("png"))).convert("RGB") for p in doc]
    img = Image.open(io.BytesIO(data))
    frames = []
    for i in range(getattr(img, "n_frames", 1)):
        img.seek(i)
        frames.append(img.convert("RGB"))
    return frames


def scale_for(img: Image.Image, page: dict) -> float:
    """Pixels per DI unit. DI reports inches for PDFs and pixels for images, so derive it from the width."""
    return img.width / (page.get("width") or img.width)


def draw_overlay(img: Image.Image, rows: list[dict], page_number: int, scale: float, kind: str,
                 selected: int | None = None) -> Image.Image:
    """Draw the polygons of `rows` that sit on this page. If `selected` is a row index, only that row is solid."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    color = KIND_COLOR.get(kind, BLUE)
    for i, r in enumerate(rows):
        poly = r.get("polygon") or []
        if r.get("page") != page_number or len(poly) < 6:
            continue
        pts = [(poly[j] * scale, poly[j + 1] * scale) for j in range(0, len(poly) - 1, 2)]
        if selected is None:
            d.polygon(pts, fill=color + (45,), outline=color + (220,), width=2)
        elif i == selected:
            d.polygon(pts, fill=BLUE + (90,), outline=BLUE + (255,), width=4)
        else:
            d.polygon(pts, outline=color + (60,), width=1)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
