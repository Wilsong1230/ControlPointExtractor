import re

def clean_description(s: str) -> str:
    if s is None:
        return ""

    # Normalize whitespace/newlines/tabs
    s = str(s)
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Fix double-double quotes that show up from PDF extraction: 1"" -> 1"
    s = s.replace('""', '"')

    # Remove space before punctuation
    s = re.sub(r"\s+([,.;:])", r"\1", s)

    # Normalize common tokens
    # LB#642, LB #642, LB# 642 -> LB #642
    s = re.sub(r"\bLB\s*#?\s*(\d+)\b", r"LB #\1", s, flags=re.IGNORECASE)

    # Normalize inches like 1" IRON PIPE (keep as-is, but ensure space)
    s = re.sub(r'(\d+)"\s*', r'\1" ', s)

    # Title-case is risky (can break abbreviations), so DON'T.
    # Just keep original casing from PDF.

    return s

if __name__ == "__main__":
    # quick test
    samples = [
        'SET 1"" IRON PIPE AND CAP LB#642   ',
        'FOUND MAG NAIL WITH DISK   TRAV PT',
        'BM 608 N. FACE CONCRETE UTILITY POLE',
    ]
    for x in samples:
        print(clean_description(x))
