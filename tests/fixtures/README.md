# SEC Filing Fixtures

Representative SEC filing samples for parser testing.

## Files

| File | Form | Purpose |
|------|------|---------|
| `def14a_standard.html` | DEF 14A | Standard proxy with multi-column Summary Compensation Table, 3 proposals, vote outcomes, meeting date |
| `def14a_tabular.html` | DEF 14A | Tabular-style proxy with `$`-prefixed amounts, 4 proposals, 2 fiscal years, CEO/CFO/EVP rows |
| `def14a_sparse.html` | DEF 14A | Minimal proxy with no machine-parseable governance signals |
| `form4_nonderivative.xml` | Form 4 | Non-derivative open-market sale with 10b5-1 plan footnote |
| `form4_derivative.xml` | Form 4 | Derivative transaction (stock option exercise) with expiration date |
| `form_8k_earnings.html` | 8-K | Item 2.02 earnings release with dollar amounts and Exhibit 99.1 |
| `form_8k_leadership.html` | 8-K | Item 5.02 officer appointment |
| `form_13f_holdings.xml` | 13F | Information table with put/call flags, sole/shared discretion, voting authority |
| `sc_13d.html` | SC 13D | Beneficial ownership initial filing with percent and share count |
| `form_144.xml` | Form 144 | Planned insider sale with broker, shares, and aggregate market value |
| `form_s3.html` | S-3 | Shelf registration statement with dollar amount |
| `form_nt10k.html` | NT 10-K | Late-filing notification |

## Usage

Load fixtures in tests using:

```python
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")
```

## Adding New Fixtures

- Keep fixtures minimal but representative of real SEC filing layouts.
- Cover at least the fields the parser is expected to extract.
- For HTML fixtures, include the top-level HTML structure.
- For XML fixtures, include the standard SEC XML envelope elements.
- Name files with the form type prefix: `def14a_`, `form4_`, `form_8k_`, etc.
