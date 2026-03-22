import pathlib

p = pathlib.Path("docs/sec-expansion-checklist.md")
text = p.read_text(encoding="utf-8")

# The three lines have \+TAB+word because PowerShell backtick-substitution ran during the first fix.
# "\\\t" in Python = backslash + TAB; need to replace with backtick character.

replacements = [
    (
        "representative filings (see \\\tests/fixtures/\\).",
        "representative filings (see `tests/fixtures/`).",
    ),
    (
        "NT filings (see \\\tests/fixtures/README.md\\).",
        "NT filings (see `tests/fixtures/README.md`).",
    ),
    (
        "ingestion (fixture-backed tests in \\\tests/test_proxy_parser.py\\).",
        "ingestion (fixture-backed tests in `tests/test_proxy_parser.py`).",
    ),
]

changed = 0
for old, new in replacements:
    if old in text:
        text = text.replace(old, new)
        changed += 1
        print(f"Fixed: ...{old[20:60]}...")
    else:
        # Try with just the backslash+tab pattern
        print(f"NOT FOUND: {ascii(old[:60])}")

p.write_text(text, encoding="utf-8")
print(f"Applied {changed} fixes")
