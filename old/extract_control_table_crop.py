import sys, re
from pathlib import Path
import pdfplumber

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

NEEDLE = "CONTROL POINT TABLE"

if len(sys.argv) < 3:
    print("Usage: python extract_control_table_crop.py <pdf> <page_num>")
    raise SystemExit(2)

pdf_path = sys.argv[1]
page_num = int(sys.argv[2])

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[page_num - 1]
    W, H = page.width, page.height

    # Search using full-page text
    full_text = page.extract_text() or ""
    if NEEDLE not in norm(full_text):
        print("Did not find CONTROL POINT TABLE in extract_text() on this page.")
        print("First 300 chars:", full_text[:300])
        raise SystemExit(0)

    # Locate bounding box of the phrase using chars (more reliable than words)
    chars = page.chars
    # Build a simple string with positions: we’ll find chars that form the needle in reading order
    # Heuristic: find any char sequence line containing both CONTROL and TABLE
    # We'll instead find all chars near lines that contain 'CONTROL' (by x/y grouping).
    # Group chars into lines by 'top' buckets
    buckets = {}
    for c in chars:
        t = c.get("text", "")
        if not t.strip():
            continue
        b = int(c["top"] // 4)
        buckets.setdefault(b, []).append(c)

    header_line_bucket = None
    for b, cs in buckets.items():
        line = "".join(x["text"] for x in sorted(cs, key=lambda z: z["x0"]))
        u = norm(line)
        if "CONTROL" in u and "POINT" in u and "TABLE" in u:
            header_line_bucket = b
            break

    if header_line_bucket is None:
        print("Could not locate header line in chars, even though text contains it.")
        raise SystemExit(0)

    cs = buckets[header_line_bucket]
    top = min(c["top"] for c in cs)
    bottom = max(c["bottom"] for c in cs)

    # Define a crop region:
    # - start slightly above header
    # - include a big chunk BELOW header where the table lives
    # - limit to left side to avoid the right table
    left_cut = W * 0.62

    crop_bbox = (0, max(top - 10, 0), left_cut, min(top + 560, H))  # (x0, top, x1, bottom) in pdfplumber
    cropped = page.crop(crop_bbox)

    out_txt = Path(pdf_path).stem + f"_p{page_num}_leftcrop.txt"
    Path(out_txt).write_text(cropped.extract_text() or "", encoding="utf-8")

    print("Page size:", (W, H), "rotation:", getattr(page, "rotation", None))
    print("Header line top:", top, "crop bbox:", crop_bbox)
    print("Wrote:", out_txt)
