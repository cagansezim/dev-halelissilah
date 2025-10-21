import io
from paddleocr import PaddleOCR
import pytesseract
from PIL import Image
import numpy as np

class OCREngine:
    def __init__(self, name: str):
        self.name = name
        self.paddle = PaddleOCR(lang="turkish") if name=="paddleocr" else None
    def text(self, png: bytes) -> str:
        if self.name=="paddleocr" and self.paddle:
            arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            res = self.paddle.ocr(arr, cls=True)
            out = []
            for page in res:
                for _, t in page:
                    out.append(t[0])
            return "\n".join(out)
        if self.name=="tesseract":
            return pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang="tur+eng")
        raise RuntimeError("Unsupported OCR engine")

def build_ocr(name: str) -> OCREngine:
    return OCREngine(name)
