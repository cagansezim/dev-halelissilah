import io, fitz
from pdf2image import convert_from_bytes

def pdf_to_images_and_text(pdf_bytes: bytes, dpi: int = 200):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    native = [doc.load_page(i).get_text("text") for i in range(len(doc))]
    doc.close()
    imgs = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")
    pages = []
    for i, im in enumerate(imgs):
        buf = io.BytesIO(); im.save(buf, "PNG")
        pages.append((buf.getvalue(), native[i] if i < len(native) else ""))
    return pages
