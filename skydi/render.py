"""Turn an uploaded file into page images and scale Document Intelligence polygons to them."""

from __future__ import annotations

import base64
import io

import pymupdf
from PIL import Image

DPI = 150


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


def page_data_url(img: Image.Image, max_width: int = 1100) -> str:
    """A compact JPEG data URL of one page, for the in-browser viewer."""
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def norm_polygon(poly: list[float], page: dict, img: Image.Image) -> list[float]:
    """Polygon as 0..1 fractions of the page, so it lines up with the image at any display size."""
    w, h = page.get("width") or img.width, page.get("height") or img.height
    return [round(v / (w if j % 2 == 0 else h), 5) for j, v in enumerate(poly)]
