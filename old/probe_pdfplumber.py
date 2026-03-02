import sys, re
import pdfplumber

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()

pdf_path = sys.argv[1]
page_num = int(sys.argv[2])

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[page_num - 1]
    print("page size (pts):", (page.width, page.height), "rotation:", getattr(page, "rotation", None))

    # Try extract_text first
    txt = page.extract_text() or ""
    print("\n--- extract_text() first 400 chars ---")
    print(txt[:400])

    # Now extract_words
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    print("\nwords extracted:", len(words))
    if words:
        # show some samples
        print("\n--- first 60 words (text,x0,top) ---")
        for w in words[:60]:
            print(f"{w['text']!r}\tx0={w['x0']:.1f}\ttop={w['top']:.1f}")

        # show any word containing key strings
        keys = ["POINT", "NO", "NORTH", "EAST", "ELEV", "STATION", "OFFSET", "DESCRIPTION", "COORD"]
        print("\n--- keyword hits ---")
        hits = 0
        for w in words:
            t = norm(w["text"])
            if any(k in t for k in keys):
                print(f"{w['text']!r}\tx0={w['x0']:.1f}\ttop={w['top']:.1f}")
                hits += 1
                if hits >= 80:
                    break
        if hits == 0:
            print("(none)")

    # If words failed, look at chars
    chars = page.chars
    print("\nchars extracted:", len(chars))
    # show a small sample of chars that are letters (often headers are char-by-char)
    sample = []
    for c in chars:
        t = c.get("text","")
        if t.isalpha():
            sample.append((t, c.get("x0",0), c.get("top",0)))
        if len(sample) >= 80:
            break
    if sample:
        print("\n--- first 80 alpha chars (char,x0,top) ---")
        for t,x0,top in sample:
            print(f"{t!r}\tx0={x0:.1f}\ttop={top:.1f}")
