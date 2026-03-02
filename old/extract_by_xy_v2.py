import sys
import re
from pathlib import Path
import pdfplumber
import pandas as pd

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def has_point_no(token: str) -> bool:
    t = norm(token)
    return ("POINT" in t) and ("NO" in t)  # catches "POINT NO.", "POINTNO.", etc.

def has_word(token: str, w: str) -> bool:
    return w in norm(token)

def main():
    if len(sys.argv) < 4:
        print("Usage: python extract_by_xy_v2.py <pdf> <page_num> <out.csv>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    out_csv = sys.argv[3]

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        W, H = page.width, page.height

        # Extract words with positions. use_text_flow=False tends to preserve table structure better.
        words = page.extract_words(
            keep_blank_chars=False,
            use_text_flow=False,
            extra_attrs=["x0", "x1", "top", "bottom"]
        )

        if not words:
            print("No words extracted from page.")
            sys.exit(0)

        # ---- Find the header row bucket anywhere on page ----
        # Look for a row containing either:
        #  - a merged token containing "POINT" and "NO"
        #  - OR separate tokens where one has POINT and another has NO
        bucket_size = 6
        buckets = {}
        for w in words:
            b = int(w["top"] // bucket_size)
            buckets.setdefault(b, []).append(w)

        header_bucket = None
        for b, ws in buckets.items():
            texts = [norm(x["text"]) for x in ws]
            merged = any(("POINT" in t and "NO" in t) for t in texts)
            separate = ("POINT" in texts) and any(t in {"NO", "NO."} for t in texts)
            if merged or separate:
                # Prefer buckets that also contain NORTH/EAST somewhere (helps avoid false matches)
                if any("NORTH" in t for t in texts) or any("EAST" in t for t in texts) or any("ELEV" in t for t in texts):
                    header_bucket = b
                    break
                # Otherwise keep as fallback
                if header_bucket is None:
                    header_bucket = b

        if header_bucket is None:
            # Diagnostic: show the most "POINT"-like tokens so you can see what pdfplumber extracted
            point_like = [(w["text"], w["x0"], w["top"]) for w in words if "POINT" in norm(w["text"])]
            print("Could not find header bucket containing POINT/NO.")
            print("POINT-like tokens (text, x0, top):")
            for t in point_like[:30]:
                print(" ", t)
            sys.exit(0)

        header_top = header_bucket * bucket_size
        header_bottom = header_top + 18  # include multi-line header band

        header_words = [w for w in words if header_top <= w["top"] <= header_bottom]

        # ---- Decide left table region AFTER header found ----
        # On your 1224-pt wide page, right table is on the far right.
        # We'll keep only words left of 60% width for extraction.
        left_cut = W * 0.60
        left_words = [w for w in words if w["x0"] < left_cut]

        # Recompute header words for left side only (now that we know where header is)
        header_words_left = [w for w in left_words if header_top <= w["top"] <= header_bottom]

        # ---- Detect column x start positions from header band ----
        # We’ll accept tokens that contain the label (because headers can be split/stacked)
        labels = ["POINT", "NORTH", "EAST", "ELEVATION", "STATION", "OFFSET", "DESCRIPTION"]
        x_start = {}

        for w in header_words_left:
            t = norm(w["text"])
            for lab in labels:
                if lab in t and lab not in x_start:
                    x_start[lab] = w["x0"]

        # If NORTH/EAST are on the next line (under COORDINATES), search slightly below
        if "NORTH" not in x_start or "EAST" not in x_start:
            below = [w for w in left_words if header_bottom <= w["top"] <= header_bottom + 40]
            for w in below:
                t = norm(w["text"])
                if "NORTH" not in x_start and ("NORTH" in t or "NORTHING" in t):
                    x_start["NORTH"] = w["x0"]
                if "EAST" not in x_start and ("EAST" in t or "EASTING" in t):
                    x_start["EAST"] = w["x0"]

        print("Header bucket top range:", (header_top, header_bottom))
        print("Detected x starts:", {k: round(v, 1) for k, v in x_start.items()})

        if "POINT" not in x_start or "NORTH" not in x_start or "EAST" not in x_start:
            print("Missing essential columns (POINT/NORTH/EAST).")
            print("Header words (left) were:")
            for w in sorted(header_words_left, key=lambda z: z["x0"]):
                print(f"  {w['text']!r} x0={w['x0']:.1f} top={w['top']:.1f}")
            sys.exit(0)

        # Build boundaries from found starts, in left table only
        order = [k for k in labels if k in x_start]
        order.sort(key=lambda k: x_start[k])

        boundaries = []
        for i, k in enumerate(order):
            x0 = x_start[k]
            x1 = x_start[order[i+1]] if i+1 < len(order) else left_cut
            boundaries.append((k, x0, x1))

        # ---- Extract data words below header ----
        data_words = [w for w in left_words if w["top"] > header_bottom + 5]

        # Group into rows by y bucket
        row_bucket = 5
        rows = {}
        for w in data_words:
            b = int(w["top"] // row_bucket)
            rows.setdefault(b, []).append(w)

        records = []
        for b, ws in sorted(rows.items(), key=lambda kv: kv[0]):
            ws_sorted = sorted(ws, key=lambda z: z["x0"])

            # Collect tokens by column band
            row = {k: [] for (k, _, _) in boundaries}
            for w in ws_sorted:
                for (k, x0, x1) in boundaries:
                    if x0 <= w["x0"] < x1:
                        row[k].append(w["text"])
                        break

            # Filter: must have a numeric point number in POINT column
            point_text = " ".join(row.get("POINT", [])).strip()
            if not re.search(r"\b\d{2,6}\b", point_text):
                continue

            rec = {
                "POINT_NO": point_text,
                "NORTHING": " ".join(row.get("NORTH", [])).strip(),
                "EASTING": " ".join(row.get("EAST", [])).strip(),
                "ELEVATION": " ".join(row.get("ELEVATION", [])).strip(),
                "STATION": " ".join(row.get("STATION", [])).strip(),
                "OFFSET": " ".join(row.get("OFFSET", [])).strip(),
                "DESCRIPTION": " ".join(row.get("DESCRIPTION", [])).strip(),
            }
            records.append(rec)

        df = pd.DataFrame(records)

        # Clean obvious junk: keep rows where north/east look numeric-ish
        def has_digit(s): return isinstance(s, str) and any(ch.isdigit() for ch in s)
        if not df.empty:
            df = df[df["NORTHING"].map(has_digit) & df["EASTING"].map(has_digit)]

        df.to_csv(out_csv, index=False)
        print("Wrote:", out_csv, "rows:", len(df))

if __name__ == "__main__":
    main()
