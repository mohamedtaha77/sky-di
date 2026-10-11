import io

from PIL import Image

from skydi import render

SQ = [1, 1, 2, 1, 2, 2, 1, 2]


def test_scale_handles_inches_and_pixels():
    img = Image.new("RGB", (1275, 1650), "white")
    assert render.scale_for(img, {"width": 8.5}) == 150
    assert render.scale_for(img, {"width": 1275}) == 1


def test_overlay_keeps_size_and_marks_only_this_page():
    img = Image.new("RGB", (400, 400), "white")
    rows = [{"page": 1, "polygon": SQ}, {"page": 2, "polygon": [3, 3, 3.5, 3, 3.5, 3.5, 3, 3.5]}]
    out = render.draw_overlay(img, rows, 1, 100, "line")
    assert out.size == img.size
    assert out.getpixel((150, 150)) != (255, 255, 255)   # inside the page-1 box
    assert out.getpixel((320, 320)) == (255, 255, 255)   # the page-2 box is not drawn


def test_page_images_reads_png_and_pdf():
    buf = io.BytesIO()
    Image.new("RGB", (50, 40), "white").save(buf, "PNG")
    assert render.page_images(buf.getvalue())[0].size == (50, 40)
    pdf = io.BytesIO()
    Image.new("RGB", (50, 40), "white").save(pdf, "PDF")
    assert len(render.page_images(pdf.getvalue())) == 1
