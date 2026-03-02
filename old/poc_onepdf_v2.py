import re
import csv
import sys
import subprocess
from pathlib import Path

TITLE_PHRASES = ["CONTROL POINT TABLE", "CONTROL POINTS TABLE"]

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

def find_pages_with_title(pdf: Path) -> list[int]:
    n = get_page_count(pdf)
    hits = []
    for p in range(1, n + 1):
        txt = page_text(pdf, p).upper()
        if any(t in txt for t in TITLE_PHRASES):
            hits.append(p)
    return hits

def extract_table_region(raw: str) -> list[str]:
    lines = [ln.rstrip("\n") for ln in raw.splitlines()]
    up = [ln.upper() for ln in lines]

    # Find the "CONTROL POINT TABLE" line
    start = None
    for i, ln in enumerate(up):
        if any(t in ln for t in TITLE_PHRASES):
            start = i
            break
    if start is None:
        return []

    # Grab lines after title until we hit a likely stop
    block = []
    empty_run = 0
    for j in range(start + 1, len(lines)):
        ln = lines[j].rstrip()
        if not ln.strip():
            empty_run += 1
            if empty_run >= 3 and block:
                break
            continue
        empty_run = 0

        # stop markers (tweak as needed)
        if any(k in up[j] for k in ["GENERAL NOTES", "LEGEND", "INDEX OF SHEETS", "SUMMARY"]):
            if block:
                break

        block.append(ln)

        if len(block) > 250:
            break

    return block

def find_header_line(block: list[str]) -> tuple[int, str] | tuple[None, None]:
    """
    Find a header line containing key column names.
    """
    for i, ln in enumerate(block):
        u = ln.upper()
        if ("POINT" in u or "PT" in u) and "NORTH" in u and "EAST" in u:
            return i, ln
    return None, None

def compute_slices(header: str) -> dict:
    """
    Use character positions in the header to determine column boundaries.
    Works well when pdftotext preserves fixed-width spacing.
    """
    u = header.upper()

    # Find start positions of key headers
    # (We look for NORTH/EAST/ELEV/DESC if present.)
    cols = {}
    for key, tokens in {
        "point_id": ["POINT", "PT", "POINTID", "POINT ID", "POINT NO.", "POINT NO", "POINT NUMBER"],
        "northing": ["NORTHING", "NORTH"],
        "easting":  ["EASTING", "EAST"],
        "elevation":["ELEVATION", "ELEV", "EL"],
        "desc":     ["DESCRIPTION", "DESC", "REMARKS", "NOTE"],
    }.items():
        pos = None
        for t in tokens:
            p = u.find(t)
            if p != -1:
                pos = p
                break
        if pos is not None:
            cols[key] = pos

    # We at least need point + east + north
    if "easting" not in cols or "northing" not in cols:
        raise RuntimeError("Could not find EASTING/NORTHING in header line. Paste the header line and we’ll adapt.")

    # Sort by position to make slices
    ordered = sorted(cols.items(), key=lambda kv: kv[1])

    # Build slice ranges
    slices = {}
    for idx, (name, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else None
        slices[name] = (start, end)

    return slices

def clean_num(s: str) -> str:
    s = s.replace(",", "").strip()
    # keep only valid numeric-ish chars
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return m.group(0) if m else ""

def parse_rows_fixedwidth(block: list[str]) -> list[dict]:
    hi, header = find_header_line(block)
    if hi is None:
        # Dump first 40 lines for debugging
        preview = "\n".join(block[:40])
        raise RuntimeError("Header line not found. Here’s the start of the captured block:\n" + preview)

    slices = compute_slices(header)

    # data lines start after header
    data_lines = block[hi + 1:]

    rows = []
    for ln in data_lines:
        if not ln.strip():
            continue
        u = ln.upper()

        # skip repeated headers / junk
        if any(t in u for t in TITLE_PHRASES):
            continue
        if ("NORTH" in u and "EAST" in u and ("POINT" in u or "PT" in u)):
            continue

        # slice fields
        def sl(name: str) -> str:
            if name not in slices:
                return ""
            a, b = slices[name]
            return ln[a:b].strip() if b is not None else ln[a:].strip()

        point = sl("point_id")
        north = clean_num(sl("northing"))
        east  = clean_num(sl("easting"))
        elev  = clean_num(sl("elevation")) if "elevation" in slices else ""
        desc  = sl("desc") if "desc" in slices else ""

        # guardrails: require point + at least east/north numbers
        if not point or (not north and not east):
            continue

        rows.append({
            "point_id": point,
            "northing": north,
            "easting": east,
            "elevation": elev,
            "description": desc
        })

    return rows, header, slices

def main():
    if len(sys.argv) < 2:
        print("Usage: python poc_onepdf_v2.py <plan.pdf>")
        raise SystemExit(2)

    pdf = Path(sys.argv[1])
    hits = find_pages_with_title(pdf)
    if not hits:
        print("No CONTROL POINT TABLE found.")
        raise SystemExit(0)

    page = hits[0]
    raw = page_text(pdf, page)
    block = extract_table_region(raw)

    # Save debug block so you can inspect alignment
    dbg = pdf.with_suffix("").name + f"_p{page}_block.txt"
    Path(dbg).write_text("\n".join(block), encoding="utf-8")

    rows, header, slices = parse_rows_fixedwidth(block)

    out_csv = pdf.with_suffix("").name + "_control_points.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "source_pdf", "page",
            "point_id", "northing", "easting", "elevation", "description"
        ])
        w.writeheader()
        for r in rows:
            w.writerow({"source_pdf": pdf.name, "page": page, **r})

    print(f"FOUND pages: {hits} (using {page})")
    print("Header line used:")
    print(header)
    print("Column slices (name: start-end):")
    for k, (a, b) in slices.items():
        print(f"  {k}: {a}-{b if b is not None else 'end'}")
    print(f"Wrote: {out_csv}")
    print(f"Saved debug block: {dbg}")
    print(f"Extracted rows: {len(rows)}")

if __name__ == "__main__":
    main()
