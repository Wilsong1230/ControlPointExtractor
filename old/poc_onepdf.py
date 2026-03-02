import re
import csv
import sys
import subprocess
from pathlib import Path

PHRASES = [
    "CONTROL POINT TABLE",
    "CONTROL POINTS TABLE",
]

def get_page_count(pdf: Path) -> int:
    info = subprocess.check_output(["pdfinfo", str(pdf)], text=True, errors="ignore")
    m = re.search(r"Pages:\s+(\d+)", info)
    if not m:
        raise RuntimeError("Could not detect page count via pdfinfo")
    return int(m.group(1))

def page_text(pdf: Path, page_num: int) -> str:
    # Extract only one page to stdout
    res = subprocess.run(
        ["pdftotext", "-f", str(page_num), "-l", str(page_num), str(pdf), "-"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    return res.stdout or ""

def find_control_point_pages(pdf: Path, max_pages: int | None = None) -> list[int]:
    n = get_page_count(pdf)
    if max_pages:
        n = min(n, max_pages)

    hits = []
    for p in range(1, n + 1):
        txt = page_text(pdf, p).upper()
        if any(ph in txt for ph in PHRASES):
            hits.append(p)
    return hits

def extract_table_block(raw_text: str) -> list[str]:
    """
    Heuristic: find the line containing 'CONTROL POINT TABLE'
    then capture subsequent non-empty lines until a 'stop' condition.
    This is intentionally simple for POC.
    """
    lines = [ln.rstrip() for ln in raw_text.splitlines()]
    up = [ln.upper() for ln in lines]

    # Find header line index
    start_idx = None
    for i, ln in enumerate(up):
        if "CONTROL POINT TABLE" in ln or "CONTROL POINTS TABLE" in ln:
            start_idx = i
            break
    if start_idx is None:
        return []

    # Skip a few lines after title (often the column headers come next)
    i = start_idx + 1

    # Collect lines that look like table content
    block = []
    empty_run = 0
    for j in range(i, len(lines)):
        ln = lines[j].strip()
        if not ln:
            empty_run += 1
            # two empty lines usually means we're past the table area
            if empty_run >= 2 and block:
                break
            continue
        empty_run = 0

        # stop markers (common in plan sheets)
        if any(k in up[j] for k in ["GENERAL NOTES", "LEGEND", "INDEX OF SHEETS", "SUMMARY", "BENCHMARK"]):
            if block:
                break

        block.append(ln)

        # Safety cap so we don't grab the whole page
        if len(block) > 200:
            break

    return block

def parse_rows(block_lines: list[str]) -> list[dict]:
    """
    Very forgiving parser:
    - tries to find rows with at least 3 numbers (E/N/Z)
    - keeps leftover as description
    You will likely refine this once you see your real output.
    """
    rows = []
    num = r"[-+]?\d+(?:\.\d+)?"
    for ln in block_lines:
        # Skip obvious header lines
        if re.search(r"\bPOINT\b", ln.upper()) and re.search(r"\bEAST", ln.upper()):
            continue

        # Find numeric fields in line
        nums = re.findall(num, ln)
        if len(nums) < 2:
            continue

        # Point ID is typically first token
        tokens = ln.split()
        point_id = tokens[0]

        # Heuristic: assume last 2-3 numbers are coords/elev
        # Many tables are (N, E, Z) or (E, N, Z). We’ll just store as raw for now.
        # You can standardize later once you confirm column order.
        easting = None
        northing = None
        elevation = None

        if len(nums) >= 3:
            a, b, c = nums[-3], nums[-2], nums[-1]
            # store both possibilities for now; you’ll lock this down after seeing a sample
            northing, easting, elevation = a, b, c
        else:
            a, b = nums[-2], nums[-1]
            northing, easting = a, b

        # Description = remove point id + numeric substrings, keep remainder
        desc = ln
        desc = re.sub(r"^\s*" + re.escape(point_id) + r"\s*", "", desc)
        desc = re.sub(num, "", desc).strip()
        desc = re.sub(r"\s{2,}", " ", desc).strip()

        rows.append({
            "point_id": point_id,
            "northing_guess": northing,
            "easting_guess": easting,
            "elevation_guess": elevation,
            "description": desc
        })
    return rows

def main():
    if len(sys.argv) < 2:
        print("Usage: python poc_onepdf.py <plan.pdf>")
        raise SystemExit(2)

    pdf = Path(sys.argv[1])
    if not pdf.exists():
        print("File not found:", pdf)
        raise SystemExit(2)

    hits = find_control_point_pages(pdf)
    if not hits:
        print("No CONTROL POINT TABLE found in:", pdf.name)
        raise SystemExit(0)

    # POC: take the first match
    page = hits[0]
    raw = page_text(pdf, page)
    block = extract_table_block(raw)
    rows = parse_rows(block)

    out_csv = pdf.with_suffix("").name + "_control_points.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "source_pdf", "page",
            "point_id", "northing_guess", "easting_guess", "elevation_guess",
            "description"
        ])
        w.writeheader()
        for r in rows:
            w.writerow({
                "source_pdf": pdf.name,
                "page": page,
                **r
            })

    print(f"FOUND pages: {hits}")
    print(f"Using page: {page}")
    print(f"Wrote: {out_csv}")
    print(f"Extracted rows: {len(rows)}")

if __name__ == "__main__":
    main()
