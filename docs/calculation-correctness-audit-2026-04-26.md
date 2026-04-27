# Calculation Correctness Audit - 2026-04-26

## Scope

Focused backend audit across these calculation surfaces:

- `app/services/derived_metrics.py`
- `app/model_engine/models/ratios.py`
- `app/model_engine/models/dcf.py`
- `app/model_engine/models/roic.py`
- nearby API contract tests and calculation audit fixtures

Audit focus areas:

- TTM completeness and metric-specific missing-data behavior
- annualization consistency
- share-count selection
- debt/cash completeness
- DCF cash-flow and equity-bridge consistency
- ROIC denominator construction and proxy signaling
- bank/regulatory gating

## Confirmed Findings

### 1. Ratios model silently zero-filled incomplete debt/cash inputs

File: `app/model_engine/models/ratios.py`

Previous behavior:

- `net_debt_to_fcf` used `current_debt or 0`, `long_term_debt or 0`, and `cash_and_short_term_investments or 0`
- a single present debt field could produce a fully populated ratio even when capital structure was incomplete
- status could remain `supported`

Risk:

- understated or overstated net debt
- silent precision on incomplete inputs
- incorrect screening or comparison output

Fix:

- require complete debt plus cash inputs for net debt
- allow explicit `total_debt` as the complete debt balance when present
- surface blocking capital-structure inputs in `missing_required_fields_last_3y`
- downgrade status to `partial` when the ratio is unavailable due to incomplete inputs

### 2. Derived metrics silently treated missing debt legs as zero for leverage and ROIC proxy

File: `app/services/derived_metrics.py`

Previous behavior:

- `leverage_ratio` used `_sum_non_null(current_debt, long_term_debt)`
- `roic_proxy` used `_sum_non_null(stockholders_equity, current_debt, long_term_debt)`
- missing debt legs, and missing cash in those bridges, still allowed values to be computed

Risk:

- incomplete balance-sheet inputs produced seemingly valid leverage and ROIC proxy values
- degraded calculations were not clearly surfaced at the metric level

Fix:

- require complete debt plus cash inputs for `leverage_ratio` and `roic_proxy`
- allow explicit `total_debt` as the complete debt balance when present
- return `None` when capital structure is incomplete instead of proxying silently
- bump derived-metrics formula version to `sec_metrics_v4`

## Reviewed Areas With No Confirmed Bug

### TTM construction

`app/services/derived_metrics.py` already:

- requires a four-quarter comparable window before producing a valid TTM row
- marks invalid windows for missing quarters, duplicate quarters, mixed fiscal calendars, incompatible statement groups, and restatement ambiguity
- nulls flow fields metric-by-metric when any component quarter is missing

### DCF bridge

`app/model_engine/models/dcf.py` already:

- distinguishes enterprise-value proxy output from full equity-bridge output
- avoids applying the debt/cash bridge when capital structure is incomplete
- surfaces `capital_structure_proxied`, `net_debt_bridge_applied`, and basis warnings

### ROIC model

`app/model_engine/models/roic.py` already had explicit tests and signaling for:

- missing cash proxying
- missing debt components without `total_debt`
- `total_debt` fallback marked as proxy
- capex sign normalization for reinvestment rate

## Versioning

- `app/model_engine/models/ratios.py`: model version `1.2.0` -> `1.2.1`
- `app/services/derived_metrics.py`: formula version `sec_metrics_v3` -> `sec_metrics_v4`

## Tests Added

- `tests/test_valuation_models.py::test_ratios_net_debt_to_fcf_requires_complete_debt_and_cash_inputs`
- `tests/test_derived_metrics.py::test_derived_metrics_require_complete_debt_and_cash_for_leverage_and_roic_proxy`

## Open Questions

1. `working_capital_days` intentionally uses latest balance-sheet accounts against annualized quarterly or TTM revenue. That is common, but if the product wants true average working-capital balances, the metric definition should be versioned explicitly.
2. Bank TTM metrics currently carry latest-period regulatory stock measures with TTM flow denominators. That is internally consistent with the current semantics, but it should remain documented as a snapshot-over-flow construction rather than a multi-period averaged denominator.