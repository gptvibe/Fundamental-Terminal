import pathlib

p = pathlib.Path("docs/sec-expansion-checklist.md")
text = p.read_text(encoding="utf-8")

# The file has backslash-backtick escaping: \`something\` -> `something`
# Fix the specific lines by replacing the escaped backticks with plain ones

bad1 = "see \\`tests/fixtures/\\`"
good1 = "see `tests/fixtures/`"

bad2 = "see \\`tests/fixtures/README.md\\`"
good2 = "see `tests/fixtures/README.md`"

bad3 = "in \\`tests/test_proxy_parser.py\\`"
good3 = "in `tests/test_proxy_parser.py`"

count = 0
for old, new in [(bad1, good1), (bad2, good2), (bad3, good3)]:
    if old in text:
        text = text.replace(old, new)
        count += 1
        print(f"Fixed: {old[:60]}")
    else:
        print(f"NOT FOUND: {old[:60]}")

p.write_text(text, encoding="utf-8")
print(f"Applied {count} fixes")
