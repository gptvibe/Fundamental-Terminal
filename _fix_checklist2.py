import pathlib

p = pathlib.Path("docs/sec-expansion-checklist.md")
text = p.read_text(encoding="utf-8")

# Fix triple-backslash + double-backslash escaping introduced by the previous script run
replacements = [
    (
        "- [x] Create a reusable SEC fixture directory for representative filings (see \\`tests/fixtures/\\`).",
        "- [x] Create a reusable SEC fixture directory for representative filings (see `tests/fixtures/`).",
    ),
    (
        "- [x] Add fixtures for 8-K, Form 4, 13F, 13D/G, DEF 14A, S-3, Form 144, and NT filings (see \\`tests/fixtures/README.md\\`).",
        "- [x] Add fixtures for 8-K, Form 4, 13F, 13D/G, DEF 14A, S-3, Form 144, and NT filings (see `tests/fixtures/README.md`).",
    ),
    (
        "- [x] Add parser test coverage before broadening production ingestion (fixture-backed tests in \\`tests/test_proxy_parser.py\\`).",
        "- [x] Add parser test coverage before broadening production ingestion (fixture-backed tests in `tests/test_proxy_parser.py`).",
    ),
]

changed = 0
for old, new in replacements:
    if old in text:
        text = text.replace(old, new)
        changed += 1
    else:
        print(f"NOT FOUND: {old[:100]}")

p.write_text(text, encoding="utf-8")
print(f"Applied {changed}/{len(replacements)} replacements")
