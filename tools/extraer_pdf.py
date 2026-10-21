"""Extrae el texto del PDF página por página para revisar o ampliar el banco de preguntas.

Uso:  python tools/extraer_pdf.py ["Sistemas Operativos.pdf"] > texto.txt
Indica también cuántas imágenes tiene cada página, porque su contenido no se extrae como texto.
"""

import sys
from pathlib import Path

import pymupdf

pdf = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "Sistemas Operativos.pdf")
doc = pymupdf.open(pdf)
for number, page in enumerate(doc, start=1):
    text = page.get_text()
    print(f"===== PÁGINA {number} · {len(text.split())} palabras · {len(page.get_images())} imágenes =====")
    print(text)
