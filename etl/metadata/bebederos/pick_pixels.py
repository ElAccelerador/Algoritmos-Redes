#!/usr/bin/env python3
import matplotlib.pyplot as plt
from pathlib import Path
import yaml, fitz
from PIL import Image

cfg = yaml.safe_load(Path("etl/metadata/bebederos/bebederos_config.yaml").read_text())
pdf, page, dpi = cfg["pdf_path"], cfg["page_index"], cfg["dpi"]

doc = fitz.open(pdf)
pix = doc.load_page(page).get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)
img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
doc.close()

fig, ax = plt.subplots()
ax.imshow(img); ax.set_title("Click en puntos de referencia (intersecciones, esquinas). Cierra la ventana al terminar.")
pts=[]
def onclick(ev):
    if ev.xdata is None or ev.ydata is None: return
    x=int(round(ev.xdata)); y=int(round(ev.ydata))
    pts.append((x,y))
    ax.plot(x,y,'rx'); ax.text(x+3,y+3,f"{x},{y}",color='r',fontsize=8)
    fig.canvas.draw()
cid = fig.canvas.mpl_connect('button_press_event', onclick)
plt.show()
print("PX coords (col,row):")
for i,(x,y) in enumerate(pts,1):
    print(f"- px: [{x}, {y}]  # P{i}")
