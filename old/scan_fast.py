import sys
from pathlib import Path
from pypdf import PdfReader

NEEDLES = [
    "CONTROL POINT TABLE",
    "CONTROL POINT",
]

def scan_pdf(pdf_path: Path, max_pages: int = 15):
    reader = PdfReader(str(pdf_path))
    hits = []

    n_pages = min(len(reader.pages), max_pages)
    for i in range(n_pages):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception as e:
            # skip pages that error out
            print(f"  [warn] {pdf_path.name} page {i+1}: {type(e).__name__}")
            continue

        up = text.upper()
        if any(n in up for n in NEEDLES):
            hits.append(i + 1)

    return hits

def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_fast.py <file.pdf | folder>")
        raise SystemExit(2)

    target = Path(sys.argv[1])
    pdfs = [target] if target.is_file() else sorted(target.glob("*.pdf"))

    if not pdfs:
        print("No PDFs found.")
        return

    for pdf in pdfs:
        pages = scan_pdf(pdf)
        if pages:
            print(f"{pdf.name}: FOUND on pages {pages}")
        else:
            print(f"{pdf.name}: not found in first 15 pages")

if __name__ == "__main__":
    main()
