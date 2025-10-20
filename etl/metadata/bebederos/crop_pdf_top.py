#!/usr/bin/env python3
import argparse
from pathlib import Path
import fitz  # PyMuPDF

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="data/mapa_bebederos_providencia.pdf")
ap.add_argument("--dst", default="data/mapa_bebederos_providencia_top.pdf")
ap.add_argument("--page", type=int, default=0, help="índice de página (0=primera)")
ap.add_argument("--top_ratio", type=float, default=0.5, help="fracción superior a conservar (0-1)")
args = ap.parse_args()

src = Path(args.src)
if not src.exists():
    raise SystemExit(f"ERROR: no existe {src}")

doc = fitz.open(src.as_posix())
page = doc.load_page(args.page)
r = page.rect  # (x0,y0,x1,y1)
h = r.height
top_h = h * max(0.0, min(1.0, args.top_ratio))
crop = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + top_h)

# crear nuevo PDF con la página recortada
ndoc = fitz.open()
np = ndoc.new_page(width=crop.width, height=crop.height)
# dibujar sólo el rectángulo superior
np.show_pdf_page(np.rect, doc, args.page, clip=crop)

ndoc.save(args.dst)
ndoc.close()
doc.close()
print(f"OK: {args.dst}")
