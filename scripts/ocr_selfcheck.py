#!/usr/bin/env python3
import os, shutil, subprocess

def have(cmd):
    return shutil.which(cmd) is not None

print("Tesseract:", shutil.which("tesseract"))
print("poppler-utils (pdftoppm):", shutil.which("pdftoppm"))

try:
    import pytesseract, pdf2image, PyPDF2, paddleocr  # noqa
    print("Python OCR deps import OK")
except Exception as e:
    print("Python OCR deps import WARN:", e)

# Quick “is tesseract callable” check
if have("tesseract"):
    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True)
        print(out.stdout.splitlines()[0])
    except Exception as e:
        print("tesseract --version failed:", e)
