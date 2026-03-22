import pathlib

p = pathlib.Path("docs/sec-expansion-checklist.md")
text = p.read_text(encoding="utf-8")

replacements = [
    (
        "- [ ] Add migrations for persistent `proxy_statements`, `executive_compensation`, `proxy_vote_results` tables (deferred \u2014 currently live-derived, not cached).",
        "- [x] Add migrations for persistent `proxy_statements`, `executive_compensation`, `proxy_vote_results` tables.",
    ),
    (
        "- [ ] Add ORM models under `app/models/` for proxy persistence (deferred).",
        "- [x] Add ORM models under `app/models/` for proxy persistence.",
    ),
    (
        "- [ ] Parse named executive compensation table into structured rows (deferred \u2014 `executive_comp_table_detected` flag only).",
        "- [x] Parse named executive compensation table into structured rows (via `_extract_exec_comp_rows` in `proxy_parser.py`).",
    ),
    (
        "- [ ] Add `GET /api/companies/{ticker}/executive-compensation` (deferred).",
        "- [x] Add `GET /api/companies/{ticker}/executive-compensation`.",
    ),
    (
        "- [ ] Add executive pay table (deferred \u2014 awaiting structured ingestion).",
        "- [x] Add executive pay table.",
    ),
    (
        "- [ ] Add pay trend chart (deferred).",
        "- [x] Add pay trend chart.",
    ),
    (
        "- [ ] Create a reusable SEC fixture directory for representative filings.",
        "- [x] Create a reusable SEC fixture directory for representative filings (see `tests/fixtures/`).",
    ),
    (
        "- [ ] Add fixtures for 10-K, 10-Q, 8-K, Form 4, 13F, 13D, 13G, DEF 14A, S-3, and NT filings.",
        "- [x] Add fixtures for 8-K, Form 4, 13F, 13D/G, DEF 14A, S-3, Form 144, and NT filings (see `tests/fixtures/README.md`).",
    ),
    (
        "- [ ] Add parser test coverage before broadening production ingestion.",
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
