# Calculation Audit Fixtures

This folder contains golden fixtures used by [tests/test_calculation_audit_goldens.py](../../test_calculation_audit_goldens.py).

## Purpose

The fixture set provides deterministic coverage for calculation drift across:

- Derived metrics
- DCF
- Reverse DCF
- ROIC
- Ratios
- Piotroski
- Altman Z

Representative company profiles included in [calculation_audit_v1.json](./calculation_audit_v1.json):

- standard industrial/tech company
- bank
- REIT
- negative FCF company
- missing quarter company
- restated filing company
- ADR/foreign reporting cadence company

The fixture file contains both:

- input data (financial statements, price context)
- expected golden outputs (exact deterministic values and edge-case flags/status)

## Drift Gate Behavior

CI should fail when formulas or model behavior change unexpectedly because tests compare current outputs against this golden fixture.

Formula/version drift is explicitly gated by a version contract inside the fixture:

- derived metrics formula version
- DCF calculation version
- reverse DCF calculation version
- Piotroski calculation version
- ROIC model version
- Ratios model version
- Altman Z model version

Any version change requires a fixture update to keep tests passing intentionally.

## Update Process

1. Intentionally change formulas/model logic.
2. Run the audit tests and inspect failing diffs:
   - `pytest tests/test_calculation_audit_goldens.py -q`
3. Recompute and validate expected outputs for affected cases.
4. Update [calculation_audit_v1.json](./calculation_audit_v1.json):
   - expected numeric values where deterministic
   - expected statuses/flags where values are not the right assertion surface
   - `formula_versions` contract when version bumps are intentional
5. Re-run tests until green.

Only update these goldens when drift is intended.
