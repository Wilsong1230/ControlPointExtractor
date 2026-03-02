import sys, csv, re
from pathlib import Path

def split_vals(s: str):
    s = s.strip()
    # split on whitespace, but keep things like 219+54.23 intact
    return [x for x in re.split(r"\s+", s) if x]

def main():
    if len(sys.argv) < 3:
        print("Usage: python normalize_flat_table.py <input.csv> <output.csv>")
        sys.exit(1)

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])

    # Read first non-empty line(s) from the input CSV
    # Your data appears to be one huge row of comma-separated “columns” where each column
    # contains many whitespace-separated values.
    with inp.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        rows = [r for r in reader if any(cell.strip() for cell in r)]

    if not rows:
        print("No data rows found.")
        sys.exit(0)

    # Find the first “real” row with lots of content
    row = max(rows, key=lambda r: sum(1 for c in r if c.strip()))

    # Heuristic: columns correspond to:
    # [header-ish stuff, point list, north list, east list, elev list, station list, offset list, description list]
    # We’ll try to locate them by keyword presence.
    joined = [c.strip() for c in row]

    def find_col_index(keyword):
        for i, c in enumerate(joined):
            if keyword in c.upper():
                return i
        return None

    # These often exist inside the first big “header” column, so we can’t rely on it.
    # Instead: assume the *lists* are later columns that look numeric-heavy.
    # We’ll pick columns by content pattern.
    def score_points(c):
        vals = split_vals(c)
        return sum(1 for v in vals if re.fullmatch(r"\d{2,6}", v))  # 500, 4005 etc

    def score_coords(c):
        vals = split_vals(c)
        return sum(1 for v in vals if re.fullmatch(r"\d{5,8}\.\d+", v))

    def score_elev(c):
        vals = split_vals(c)
        return sum(1 for v in vals if re.fullmatch(r"\d{1,3}\.\d+", v))

    def score_station(c):
        vals = split_vals(c)
        return sum(1 for v in vals if re.fullmatch(r"\d{1,4}\+\d{1,2}\.\d{1,2}", v))

    def score_offset(c):
        vals = split_vals(c)
        return sum(1 for v in vals if re.fullmatch(r"-?\d+(?:\.\d+)?", v))

    # Find best candidates among columns
    candidates = list(range(len(joined)))

    point_i = max(candidates, key=lambda i: score_points(joined[i]))
    north_i = max(candidates, key=lambda i: score_coords(joined[i]))
    # pick east as best coords column that's not north_i
    east_i  = max([i for i in candidates if i != north_i], key=lambda i: score_coords(joined[i]))
    elev_i  = max(candidates, key=lambda i: score_elev(joined[i]))
    stat_i  = max(candidates, key=lambda i: score_station(joined[i]))
    off_i   = max(candidates, key=lambda i: score_offset(joined[i]))
    # description tends to be the longest text column
    desc_i  = max(candidates, key=lambda i: len(joined[i]))

    points = split_vals(joined[point_i])
    norths = split_vals(joined[north_i])
    easts  = split_vals(joined[east_i])
    elevs  = split_vals(joined[elev_i])
    stats  = split_vals(joined[stat_i])
    offs   = split_vals(joined[off_i])

    # Descriptions are tricky: they might be one long quoted string containing repeated phrases.
    # For your case, it's a sequence of descriptions separated by ' SET ' patterns etc.
    # First pass: split on ' SET ' while keeping 'SET' back.
    desc_raw = joined[desc_i].strip().strip('"')
    # common delimiter in your data: repeating "SET ..." / "FOUND ..."
    # We'll split where a new description likely starts.
    desc_parts = re.split(r'(?=(?:SET|FOUND|BM)\b)', desc_raw)
    descs = [d.strip().strip(",") for d in desc_parts if d.strip()]

    n = min(len(points), len(norths), len(easts), len(elevs), len(stats), len(offs))
    # If desc count doesn't match, we’ll pad/truncate
    if len(descs) < n:
        descs += [""] * (n - len(descs))
    if len(descs) > n:
        descs = descs[:n]

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "POINT_NO","NORTHING","EASTING","ELEVATION","STATION","OFFSET","DESCRIPTION"
        ])
        w.writeheader()
        for i in range(n):
            w.writerow({
                "POINT_NO": points[i],
                "NORTHING": norths[i],
                "EASTING": easts[i],
                "ELEVATION": elevs[i],
                "STATION": stats[i],
                "OFFSET": offs[i],
                "DESCRIPTION": descs[i],
            })

    print("Wrote:", out)
    print("Counts:")
    print("  points:", len(points))
    print("  north :", len(norths))
    print("  east  :", len(easts))
    print("  elev  :", len(elevs))
    print("  stat  :", len(stats))
    print("  off   :", len(offs))
    print("  desc  :", len(descs))
    print("  rows  :", n)

if __name__ == "__main__":
    main()
