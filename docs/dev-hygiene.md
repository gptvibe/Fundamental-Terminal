# Dev Hygiene

Do not commit local or generated test-run artifacts.

- Frontend local test outputs (for example `frontend/vitest-*.json`, `frontend/.vitest-summary.json`, `frontend/test-output.txt`)
- Local Playwright debug outputs (for example `frontend/.playwright_*_output.txt`, `frontend/.tmp_playwright_check.js`)
- Ad hoc local run logs (for example `frontend/requested-tests.log`)
- Local screenshot capture folders (for example `review-shots/`)
- Temporary scratch artifacts (for example `artifacts/temp_*.json`)
