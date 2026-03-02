import sys
import re
from pathlib import Path

import pdfplumber
import pandas as pd

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

def median(vals):
    vals = sorted(vals)
    if not vals:
        return None
    n = len(vals)
    return vals[n//2] if n % 2 else 0.5*(vals[n//2-1] + vals[n//2])

def main():
    if len(sys.argv) < 4:
        print("Usage: python extract_by_xy.py <pdf> <page_num> <out.csv>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    out_csv = sys.argv[3]

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        W, H = page.width, page.height
        mid_x = W / 2

        # Extract words with positions
        words = page.extract_words(
            keep_blank_chars=False,
            use_text_flow=True,
            extra_attrs=["x0", "x1", "top", "bottom"]
        )

        # Focus on left half to avoid the right-side table
        left_words = [w for w in words if w["x0"] < mid_x]

        # Find header row: look for POINT and NO near each other on left
        header_candidates = [w for w in left_words if norm(w["text"]) in {"POINT", "NO.", "NO", "POINTNO.", "POINTNO"}]
        if not header_candidates:
            print("Could not find POINT/NO header tokens on left side. Try a different page or loosen the filter.")
            sys.exit(0)

        # Pick the y-level that contains POINT and NO
        # Cluster by 'top' (pdfplumber uses top from top of page)
        # We'll find a row band where both exist.
        # Convert to a coarse bucket (10 pt)
        buckets = {}
        for w in header_candidates:
            b = int(w["top"] // 10)
            buckets.setdefault(b, []).append(w)

        header_bucket = None
        for b, ws in buckets.items():
            texts = {norm(x["text"]) for x in ws}
            if "POINT" in texts and ("NO" in texts or "NO." in texts):
                header_bucket = b
                break

        if header_bucket is None:
            # fallback: just take bucket with most header-like tokens
            header_bucket = max(buckets.items(), key=lambda kv: len(kv[1]))[0]

        header_y_top = header_bucket * 10
        header_y_bottom = header_y_top + 20  # include two-line header band

        header_words = [w for w in left_words if header_y_top <= w["top"] <= header_y_bottom]

        # Determine column x starts by locating known header labels
        # The table headers in your screenshot:
        # POINT NO | NORTH | EAST | ELEVATION | STATION | OFFSET | DESCRIPTION
        labels = {
            "POINT": None,
            "NORTH": None,
            "EAST": None,
            "ELEVATION": None,
            "STATION": None,
            "OFFSET": None,
            "DESCRIPTION": None,
        }

        # Sometimes "COORDINATES" sits above NORTH/EAST; ignore it.
        for w in header_words:
            t = norm(w["text"])
            for k in list(labels.keys()):
                if labels[k] is None and (t == k or (k == "NORTH" and t == "NORTHING")):
                    labels[k] = w["x0"]

        # If NORTH/EAST didn’t appear because header is split, search a bit below header band
        if labels["NORTH"] is None or labels["EAST"] is None:
            below = [w for w in left_words if header_y_bottom <= w["top"] <= header_y_bottom + 40]
            for w in below:
                t = norm(w["text"])
                if labels["NORTH"] is None and (t == "NORTH" or t == "NORTHING"):
                    labels["NORTH"] = w["x0"]
                if labels["EAST"] is None and (t == "EAST" or t == "EASTING"):
                    labels["EAST"] = w["x0"]

        # Keep only labels we found; require at least POINT/NORTH/EAST/DESCRIPTION-ish
        found = {k:v for k,v in labels.items() if v is not None}
        print("Detected header x positions:", found)

        if labels["POINT"] is None or labels["NORTH"] is None or labels["EAST"] is None:
            print("Missing essential columns (POINT/NORTH/EAST). We can still proceed if you paste the header band text.")
            sys.exit(0)

        # Build column boundaries from sorted x positions
        col_order = ["POINT", "NORTH", "EAST", "ELEVATION", "STATION", "OFFSET", "DESCRIPTION"]
        x_starts = [(k, labels[k]) for k in col_order if labels[k] is not None]
        x_starts.sort(key=lambda kv: kv[1])

        # Convert starts into boundaries (midpoints between starts)
        boundaries = []
        for i, (k, x0) in enumerate(x_starts):
            x1 = x_starts[i+1][1] if i+1 < len(x_starts) else mid_x  # stop at mid-page
            boundaries.append((k, x0, x1))

        # Data region: below header
        data_words = [w for w in left_words if w["top"] > header_y_bottom + 5]

        # Group words into rows by y (use 'top' buckets)
        # Table rows have consistent y; bucket by 6 pts works well
        rows = {}
        for w in data_words:
            b = int(w["top"] // 6)
            rows.setdefault(b, []).append(w)

        # Build records: only keep rows that look like they start with a point number (digits)
        records = []
        for b, ws in sorted(rows.items(), key=lambda kv: kv[0]):
            # Sort left-to-right
            ws_sorted = sorted(ws, key=lambda w: w["x0"])

            # Quick filter: must contain a point number token near POINT column
            # We'll find tokens in POINT column band and see if any are numeric
            point_tokens = []
            for w in ws_sorted:
                for (k, x0, x1) in boundaries:
                    if k == "POINT" and x0 <= w["x0"] < x1:
                        point_tokens.append(norm(w["text"]))
            if not any(re.fullmatch(r"\d{2,6}", t) for t in point_tokens):
                continue

            row = {k: [] for (k, _, _) in boundaries}
            for w in ws_sorted:
                for (k, x0, x1) in boundaries:
                    if x0 <= w["x0"] < x1:
                        row[k].append(w["text"])
                        break

            # Join tokens per column
            rec = {}
            for k in row:
                rec[k] = " ".join(row[k]).strip()

            # Map to final names; some columns may be missing
            records.append({
                "POINT_NO": rec.get("POINT", ""),
                "NORTHING": rec.get("NORTH", ""),
                "EASTING": rec.get("EAST", ""),
                "ELEVATION": rec.get("ELEVATION", ""),
                "STATION": rec.get("STATION", ""),
                "OFFSET": rec.get("OFFSET", ""),
                "DESCRIPTION": rec.get("DESCRIPTION", ""),
            })

        df = pd.DataFrame(records)

        # Clean: drop obvious junk rows where coordinates are missing
        df = df[df["POINT_NO"].str.match(r"^\d{2,6}$", na=False)]
        df = df[df["NORTHING"].str.contains(r"\d", na=False)]
        df = df[df["EASTING"].str.contains(r"\d", na=False)]

        df.to_csv(out_csv, index=False)
        print("Wrote:", out_csv, "rows:", len(df))

if __name__ == "__main__":
    main()
