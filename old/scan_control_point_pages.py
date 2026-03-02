import sys
from pathlib import Path
import pdfplumber

NEEDLES = [
    "CONTROL POINT TABLE",
    "CONTROL POINT",
]

def scan_pdf(pdf_path: Path, max_pages: int = 15):
    hits = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            text = (page.extract_text() or "").upper()
            if any(n in text for n in NEEDLES):
                hits.append(i + 1)
    return hits

def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_control_point_pages.py <file.pdf | folder>")
        raise SystemExit(2)

    target = Path(sys.argv[1])
    pdfs = [target] if target.is_file() else sorted(target.glob("*.pdf"))

    if not pdfs:
        print("No PDFs found.")
        return

    for pdf in pdfs:
        pages = scan_pdf(pdf)
        if pages:
            print(f"{pdf.name}: found on pages {pages}")
        else:
            print(f"{pdf.name}: not found in first 15 pages")

if __name__ == "__main__":
    main()
