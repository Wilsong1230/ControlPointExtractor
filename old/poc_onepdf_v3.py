import re
import csv
import sys
import subprocess
from pathlib import Path

TITLE_PHRASES = [
    "CONTROL POINT TABLE",
    "CONTROL POINTS TABLE",
    "VERTICAL CONTROL POINT",
    "HORIZONTAL CONTROL POINT",
    "CONTROL POINT",
]

def get_page_count(pdf: Path) -> int:
    info = subprocess.check_output(["pdfinfo", str(pdf)], text=True, errors="ignore")
    m = re.search(r"Pages:\s+(\d+)", info)
    return int(m.group(1)) if m else 300

def page_text(pdf: Path, page_num: int) -> str:
    res = subprocess.run(
        ["pdftotext", "-f", str(page_num), "-l", str(page_num), str(pdf), "-"],
        capture_output=True, text=True, errors="ignore"
    )
    return res.stdout or ""

def find_pages_with_any_title(pdf: Path) -> list[int]:
    n = get_page_count(pdf)
    hits = []
    for p in range(1, n + 1):
        txt = page_text(pdf, p).upper()
        if any(t in txt for t in TITLE_PHRASES):
            hits.append(p)
    return hits

def extract_table_region(raw: str) -> list[str]:
    lines = [ln.strip() for ln in raw.splitlines()]
    # remove totally empty
    return [ln for ln in lines if ln]

NUM = r"[-+]?\d+(?:\.\d+)?"

def looks_like_alignment(s: str) -> bool:
    # examples: BL_ALICO, ALIGN_1, etc.
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", s))

def looks_like_point_id(s: str) -> bool:
    # examples: BL5, BL6, CP12, P501 (tweak later)
    return bool(re.fullmatch(r"[A-Z]{1,4}\d{1,4}", s))

def looks_like_coord(s: str) -> bool:
    # your coords look like 6 digits + decimals
    return bool(re.fullmatch(r"\d{5,8}\.\d{2,6}", s))

def parse_records(lines: list[str]) -> list[dict]:
    """
    Parse plan text where table columns are stacked vertically.
    We look for repeating pattern:
      alignment (e.g. BL_ALICO)
      point_id (e.g. BL5)
      north (coord)
      east (coord)
      then other fields
      description = text until next point_id
    """
    records = []
    i = 0
    current_alignment = ""

    while i < len(lines):
        tok = lines[i]

        # Track alignment tokens
        if looks_like_alignment(tok) and tok not in {"NORTH", "EAST", "ELEVATION", "COORDINATES"}:
            current_alignment = tok
            i += 1
            continue

        # Record start: point id like BL5
        if looks_like_point_id(tok):
            point_id = tok
            alignment = current_alignment

            # Collect next ~25 tokens to find coords + fields
            window = lines[i+1:i+30]

            # Find first two coordinate-looking numbers in the window
            coords = [w for w in window if looks_like_coord(w)]
            northing = coords[0] if len(coords) >= 1 else ""
            easting  = coords[1] if len(coords) >= 2 else ""

            # Find elevation if present: usually a smaller number like 23.24
            elev = ""
            for w in window:
                if re.fullmatch(r"\d{1,3}\.\d{1,3}", w):
                    elev = w
                    break

            # Find station like 219+54.23 (common)
            station = ""
            for w in window:
                if re.fullmatch(r"\d{1,4}\+\d{1,2}\.\d{1,2}", w):
                    station = w
                    break

            # Find offset: could be numeric like 17.98 or integer like 501/502
            offset = ""
            for w in window:
                if re.fullmatch(r"\d{1,4}(?:\.\d{1,3})?", w) and w != elev:
                    # don't accidentally grab PI/POT etc
                    # heuristic: take first numeric after station if station exists
                    offset = w
                    break

            # Description: collect lines after this point id until next point id/alignment header
            desc_parts = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if looks_like_point_id(nxt) and j != i + 1:
                    break
                # stop if another alignment starts (often repeats)
                if looks_like_alignment(nxt) and nxt == current_alignment and desc_parts:
                    # alignment repeats between rows; stop when we see it again after collecting something
                    break

                # skip obvious non-desc tokens
                if nxt.upper() in {"NORTH", "EAST", "ELEVATION", "COORDINATES", "ALIGNMENT", "STATION", "OFFSET", "DESCRIPTION"}:
                    j += 1
                    continue
                if looks_like_coord(nxt):
                    j += 1
                    continue

                desc_parts.append(nxt)
                j += 1

                # cap description length
                if len(desc_parts) > 30:
                    break

            description = " ".join(desc_parts).strip()
            description = re.sub(r"\s{2,}", " ", description)

            # Only keep plausible rows
            if northing and easting:
                records.append({
                    "alignment": alignment,
                    "point_id": point_id,
                    "northing": northing,
                    "easting": easting,
                    "elevation": elev,
                    "station": station,
                    "offset": offset,
                    "description": description,
                })

            i = j
            continue

        i += 1

    return records

def main():
    if len(sys.argv) < 2:
        print("Usage: python poc_onepdf_v3.py <plan.pdf>")
        raise SystemExit(2)

    pdf = Path(sys.argv[1])
    if not pdf.exists():
        print("File not found:", pdf)
        raise SystemExit(2)

    hits = find_pages_with_any_title(pdf)
    if not hits:
        print("No control-point-related pages found.")
        raise SystemExit(0)

    # POC: try pages in order until we get records
    all_records = []
    used_page = None
    debug_file = None

    for page in hits:
        raw = page_text(pdf, page)
        lines = extract_table_region(raw)

        dbg = pdf.with_suffix("").name + f"_p{page}_lines.txt"
        Path(dbg).write_text("\n".join(lines[:400]), encoding="utf-8")
        debug_file = dbg

        recs = parse_records(lines)
        if recs:
            all_records = recs
            used_page = page
            break

    if not all_records:
        print("Found candidate pages:", hits)
        print("But did not parse any rows.")
        print("Saved debug text (first 400 non-empty lines) to:", debug_file)
        raise SystemExit(0)

    out_csv = pdf.with_suffix("").name + "_control_points.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "source_pdf", "page",
            "alignment", "point_id",
            "northing", "easting", "elevation",
            "station", "offset",
            "description"
        ])
        w.writeheader()
        for r in all_records:
            w.writerow({"source_pdf": pdf.name, "page": used_page, **r})

    print("Candidate pages:", hits)
    print("Parsed page:", used_page)
    print("Rows:", len(all_records))
    print("Wrote:", out_csv)

if __name__ == "__main__":
    main()
