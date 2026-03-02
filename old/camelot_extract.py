import sys
from pathlib import Path
import re
import camelot
import pandas as pd

def norm(s: str) -> str:
    return " ".join(str(s).replace("\n", " ").split()).strip()

def nonempty_cell_count(df: pd.DataFrame) -> int:
    # Count cells that are not empty after normalization, without applymap
    if df is None or df.empty:
        return 0
    vals = df.astype(str).to_numpy().ravel()
    return sum(1 for v in vals if norm(v) != "")

def table_score(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    nonempty = nonempty_cell_count(df)
    # Bonus if table contains key words
    flat = " ".join(norm(x).upper() for x in df.astype(str).to_numpy().ravel()[:400])
    bonus = 2000 if ("POINT" in flat and ("NORTH" in flat or "EAST" in flat)) else 0
    return nonempty + bonus

def read_tables(pdf_path: str, page: str):
    tables = []
    try:
        t = camelot.read_pdf(pdf_path, pages=page, flavor="lattice")
        tables += list(t)
    except Exception as e:
        print("[warn] lattice failed:", type(e).__name__, e)

    try:
        t = camelot.read_pdf(pdf_path, pages=page, flavor="stream")
        tables += list(t)
    except Exception as e:
        print("[warn] stream failed:", type(e).__name__, e)

    return tables

def make_unique(cols):
    seen = {}
    out = []
    for c in cols:
        c = norm(c)
        if c in seen:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

def find_point_col(cols):
    for c in cols:
        u = c.upper()
        if "POINT" in u and ("NO" in u or "NUMBER" in u):
            return c
    for c in cols:
        if "POINT" in c.upper():
            return c
    return cols[0] if cols else None

def main():
    if len(sys.argv) < 3:
        print("Usage: python camelot_extract.py <pdf> <page>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    page = str(sys.argv[2])

    tables = read_tables(pdf_path, page)
    if not tables:
        print("No tables found by Camelot.")
        sys.exit(0)

    scored = []
    for idx, t in enumerate(tables):
        df = t.df
        s = table_score(df)
        scored.append((s, idx, t))
    scored.sort(reverse=True, key=lambda x: x[0])

    best_score, best_idx, best_table = scored[0]
    df = best_table.df.copy()
    print(f"Picked table #{best_idx} with score {best_score}, shape={df.shape}, flavor={best_table.flavor}")

    # Use first row as header; make unique even if blanks
    df.columns = make_unique(df.iloc[0].tolist())
    df = df[1:].reset_index(drop=True)
    df.columns = make_unique(df.columns.tolist())

    print("Detected columns:", df.columns.tolist())

    point_col = find_point_col(df.columns.tolist())
    if point_col is None:
        print("Could not determine point column.")
        sys.exit(0)

    # If duplicate col names cause df[point_col] to be DataFrame, take first column
    series = df[point_col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]

    s = series.astype(str).map(norm)
    df = df[s != ""].copy()

    # Rename columns to GIS-friendly if detectable
    rename = {}
    for c in df.columns:
        u = c.upper()
        if "POINT" in u and ("NO" in u or "NUMBER" in u): rename[c] = "POINT_NO"
        elif "NORTH" in u: rename[c] = "NORTHING"
        elif "EAST" in u: rename[c] = "EASTING"
        elif "ELEV" in u: rename[c] = "ELEVATION"
        elif "STATION" in u: rename[c] = "STATION"
        elif "OFFSET" in u: rename[c] = "OFFSET"
        elif "DESCRIPT" in u: rename[c] = "DESCRIPTION"

    df = df.rename(columns=rename)

    out = Path(pdf_path).stem + f"_p{page}_control_points.csv"
    df.to_csv(out, index=False)
    print("Saved:", out, "rows:", len(df))

if __name__ == "__main__":
    main()
