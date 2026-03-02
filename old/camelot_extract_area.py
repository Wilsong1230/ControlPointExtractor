import sys
from pathlib import Path
import camelot
import pandas as pd

def norm(s: str) -> str:
    return " ".join(str(s).replace("\n"," ").split()).strip()

if len(sys.argv) < 3:
    print("Usage: python camelot_extract_area.py <pdf> <page>")
    print("Then edit TABLE_AREA in the script.")
    raise SystemExit(2)

pdf_path = sys.argv[1]
page = str(sys.argv[2])

# TODO: EDIT THIS after you look at page_31_grid.png
# format: "x1,y1,x2,y2" in PDF points (bottom-left origin)
TABLE_AREA = "40,740,660,80" 

if TABLE_AREA is None:
    print("Set TABLE_AREA in the script first.")
    raise SystemExit(2)

tables = camelot.read_pdf(
    pdf_path,
    pages=page,
    flavor="lattice",              # since it has lines
    table_areas=[TABLE_AREA],
)

if tables.n == 0:
    print("No tables found in that area.")
    raise SystemExit(0)

df = tables[0].df.copy()

# Two-row header: often header spans 2 rows. We'll merge first 2 rows.
# If your table has: row0 = ['POINT NO.', 'COORDINATES', ...], row1 = ['','NORTH','EAST',...]
# combine them.
if df.shape[0] >= 2:
    h0 = [norm(x) for x in df.iloc[0].tolist()]
    h1 = [norm(x) for x in df.iloc[1].tolist()]
    cols = []
    for a,b in zip(h0,h1):
        if a and b: cols.append(f"{a}_{b}")
        elif a: cols.append(a)
        elif b: cols.append(b)
        else: cols.append("")
    df = df[2:].reset_index(drop=True)
    df.columns = cols
else:
    df.columns = [norm(x) for x in df.iloc[0].tolist()]
    df = df[1:].reset_index(drop=True)

# Clean blank columns
df = df.loc[:, [c for c in df.columns if c.strip() != ""]]

out = Path(pdf_path).stem + f"_p{page}_LEFTTABLE.csv"
df.to_csv(out, index=False)
print("Saved:", out, "rows:", len(df), "cols:", list(df.columns))
