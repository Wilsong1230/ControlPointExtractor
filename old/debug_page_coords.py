import sys
import pdfplumber
from PIL import Image, ImageDraw, ImageFont

pdf_path = sys.argv[1]
page_num = int(sys.argv[2])

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[page_num - 1]
    im = page.to_image(resolution=150).original.convert("RGB")

w, h = im.size
draw = ImageDraw.Draw(im)

# draw a light grid to help estimate coordinates
step = 200
for x in range(0, w, step):
    draw.line([(x, 0), (x, h)], width=1)
    draw.text((x+2, 2), str(x), fill=(0,0,0))
for y in range(0, h, step):
    draw.line([(0, y), (w, y)], width=1)
    draw.text((2, y+2), str(y), fill=(0,0,0))

out = f"page_{page_num}_grid.png"
im.save(out)
print("Saved:", out)
print("Image size (px):", (w, h))
print("PDF size (pts):", (page.width, page.height))
