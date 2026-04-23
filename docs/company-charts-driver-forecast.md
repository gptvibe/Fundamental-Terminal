# Company Charts Driver Forecast

## Summary

The charts dashboard now prefers a driver-based integrated forecast engine for `/company/[ticker]/charts`.
The payload contract is unchanged: the endpoint still emits base / bull / bear scenario series plus the same assumptions and calculations cards.
When statement coverage is too thin, it still falls back to the older guarded heuristic model instead of fabricating driver inputs.
Before industrial schedules are built, the forecast entrypoint now classifies the issuer as `NONFIN_IB_MODEL`, `REGULATED_FINANCIAL_SEPARATE`, or `UNSURE_REQUIRE_CONSERVATIVE_FALLBACK`.
That gate prevents bank-style and other regulated-financial issuers from being silently modeled with industrial operating-working-capital, sales-to-capital, and capex heuristics.

The driver bundle now also carries backend-only `line_traces` for the core base-scenario projected lines: revenue, cost of revenue, gross profit, operating income, pretax income, income tax, net income, accounts receivable, inventory, accounts payable, deferred revenue, accrued operating liabilities, depreciation and amortization, SBC expense, capex, operating cash flow, free cash flow, diluted shares, and EPS.
Those traces are generated inside the forecast flow from the same schedules and bridge points used to compute the forecast.

The charts dashboard response can now also carry an additive optional `projection_studio` payload built from those existing forecast outputs and trace objects.
That payload remains backend-generated and JSON-serializable in this phase; it is intended for downstream consumers and snapshot persistence rather than a dedicated frontend Studio UI.

## Canonical Capex Note

The canonical implementation keeps `Delta operating working capital` in `OCF`, not in `capex`.
Delta operating working capital flows through OCF, not capex.
`Sales-to-capital` is used only to size positive-growth fixed-capital reinvestment, while maintenance capex is still floored by capex intensity and depreciation.
That split preserves the full `EBIT -> pretax income -> net income -> OCF -> FCF` bridge without double counting working-capital movement.

## Migration Path

1. `build_company_charts_dashboard_response(...)` now loads annual statements, point-in-time-safe earnings-model diagnostics, and point-in-time-safe earnings releases.
2. `build_driver_forecast_bundle(...)` first runs the bank-suitability routing gate.
3. If the issuer is tagged `NONFIN_IB_MODEL`, the industrial driver bundle is built and the payload renders:
   - base / bull / bear revenue, growth, and EPS cases
   - base-case profit and cash-flow schedules
   - separate assumption and calculation cards
4. If the issuer is tagged `REGULATED_FINANCIAL_SEPARATE`, the industrial driver engine is bypassed and the UI surfaces routing metadata instead of silently stretching DSO/DIO/DPO and industrial capex logic onto a bank-style balance sheet.
5. If the issuer is tagged `UNSURE_REQUIRE_CONSERVATIVE_FALLBACK`, the UI stays on the guarded heuristic fallback and surfaces the routing warning in assumptions metadata.
6. If the driver bundle is otherwise unavailable because coverage is thin, the existing heuristic extrapolation path remains active and the payload shape stays valid.

## Core Formulas

- Revenue:
  `Revenue(t) = Revenue(t-1) * (1 + price growth + market growth + market-share change)`
  Year one can then be anchored toward management guidance and clipped by backlog or capacity constraints.
- Bottom-up revenue:
  When segment history exists, each segment is forecast separately and then summed back to company revenue before overlays.
- Operating income:
  `EBIT = Revenue - variable costs - semi-variable costs - fixed costs`
- Pretax bridge:
  `Pretax income = EBIT - interest expense + interest income + other income/expense`
- Taxes:
  `Book tax expense = cash tax + deferred tax expense; cash tax = max(pretax income - NOL usage, 0) x cash tax rate`
- Net income:
  `Net income = Pretax income - taxes`
- Operating working capital:
  `Operating NWC = Accounts receivable + Inventory - Accounts payable - Deferred revenue - Accrued operating liabilities`
- Receivables driver:
  `Accounts receivable = Revenue * DSO / 365`
- Inventory driver:
  `Inventory = Cost of revenue * DIO / 365`
- Payables driver:
  `Accounts payable = Cost of revenue * DPO / 365`
- Deferred revenue / contract liabilities:
  `Deferred revenue = Revenue * deferred-revenue days / 365`
- Accrued operating liabilities:
  `Accrued operating liabilities = Cash operating cost * accrued-liability days / 365`
- Growth reinvestment:
  `Growth reinvestment = max(delta revenue, 0) / sales-to-capital`
- Maintenance capex:
  `Maintenance capex = max(Revenue * capex intensity, D&A)`
- Capex:
  `Capex = max(maintenance capex, D&A + growth reinvestment)`
- Operating cash flow:
  `OCF = Net income + D&A + SBC + deferred tax expense - delta operating working capital`
- Free cash flow:
  `FCF = OCF - Capex`
- Cash and debt support:
  `Ending cash / debt = Opening cash / debt adjusted for free cash flow, target cash buffer, and debt paydown or draw`
- Interest support:
  `Interest expense = Average debt * debt cost`
  `Interest income = Average cash * cash yield`
- Diluted shares:
  `Basic shares(t) = Basic shares(t-1) + RSU / SBC shares + acquisition shares issued - buyback retirement shares`
  `Diluted shares(t) = Basic shares(t) + treasury-stock options / warrants + if-converted shares`
- EPS:
  `EPS = Net income / diluted shares`

## Assumption Sources

- Price, market growth, market share, and segment growth are inferred from historical filing trends.
- Guidance uses the latest observable earnings-release midpoint at the selected `as_of`.
- DSO comes from `accounts_receivable / revenue * 365`.
- DIO and DPO come from `inventory / cost_of_revenue * 365` and `accounts_payable / cost_of_revenue * 365` when disclosure exists; cost of revenue is taken directly when filed and proxied conservatively when not.
- Deferred-revenue days and accrued-operating-liability days are built only when those balances are disclosed.
- Cash, marketable securities, short-term investments, short-term debt, current maturities, and other financing items are excluded from operating working capital.
- Sales-to-capital comes from `revenue / total assets` and is used only for positive-growth fixed-capital reinvestment, not for a second working-capital charge.
- Opening cash uses disclosed `cash_and_short_term_investments` or `cash_and_cash_equivalents` when available.
- Opening debt uses disclosed `total_debt`, or `current_debt + long_term_debt` as fallback.
- Debt cost uses historical `interest_expense / average debt` when disclosed.
- Cash yield uses historical `interest_income / average cash` when disclosed.
- Other income/expense uses direct disclosure first, then a residual bridge from pretax income if available.
- Book tax rate uses historical `income_tax_expense / pretax income` when disclosed, while cash tax rate uses direct cash taxes or current-tax disclosure when available and otherwise falls back to the modeled book rate.
- When tax disclosure is sufficient, the engine rolls opening NOL, current-period NOL creation, NOL usage, and ending NOL explicitly, with a simplified deferred-tax-asset bridge tied to the NOL balance.
- The diluted-share bridge starts from disclosed basic weighted-average shares when available, then layers on treasury-stock-method option and warrant dilution, disclosed RSU or stock-award issuance, explicit buyback retirement, acquisition share issuance, and if-converted shares for dilutive converts.
- If the filings do not disclose enough share-bridge components to support that build, the engine falls back to the older historical-share-drift proxy and labels that fallback explicitly in the assumptions card.
- Regulated-financial routing uses company classification from `regulated_financials.classify_regulated_entity(...)` first, then statement-level bank markers such as regulatory source ids, net interest income, deposits, and capital-ratio fields.
- Financial-sector-adjacent issuers without a confirmed bank classification are tagged `UNSURE_REQUIRE_CONSERVATIVE_FALLBACK` so the engine does not assert industrial IB-style working-capital and reinvestment schedules prematurely.

## Fallback Behavior

The driver engine still prefers explicit disclosure, but it uses conservative shortcuts when filings are incomplete:

- If cash balances are missing, opening cash falls back to a target cash ratio derived from historical cash-to-revenue, or a conservative default when no cash history exists.
- If debt balances are missing, opening debt starts at zero until forecast free cash flow would otherwise push cash below the target buffer, at which point the model draws debt.
- If receivables are missing, DSO falls back to a conservative default rather than using total current assets.
- If inventory is missing, the inventory schedule stays at zero unless filings disclose inventory explicitly.
- If payables are missing, DPO falls back to a conservative payable-days assumption rather than using total current liabilities.
- If deferred revenue or accrued operating liabilities are missing, those liability schedules default to zero instead of backfilling financing-heavy current-liability buckets.
- If historical debt cost is missing, new or existing debt accrues at a default debt rate rather than a company-specific disclosed rate.
- If historical cash yield is missing, surplus cash earns a default cash yield.
- If other income/expense is not directly disclosed, the engine back-solves it from the historical pretax bridge when possible; otherwise it assumes zero.
- If historical tax data is thin, taxes fall back to a clearly labeled simple effective-tax-rate method rather than an explicit NOL schedule.
- If explicit share-bridge disclosures are missing, diluted shares fall back to historical diluted-share drift with revenue-scaled SBC, buyback, acquisition, and convert proxies, and that fallback is called out directly in the assumptions output.
- If annual history is too thin to support explicit revenue, cost, reinvestment, and dilution schedules, the entire driver engine is bypassed and the older heuristic forecast remains the fallback.
- If the routing gate classifies the issuer as `REGULATED_FINANCIAL_SEPARATE`, the industrial driver engine is bypassed even when statement history is otherwise deep enough.

These shortcuts are intentionally narrow: they preserve a full EBIT -> EBT -> Net income -> OCF -> FCF bridge without reintroducing the old `net_income = EBIT * conversion` shortcut.
They also preserve working-capital release in declining revenue scenarios because the operating working-capital balances are explicitly re-scaled down with the lower revenue and cost base.

## No-Lookahead Rule

- Financial statements are filtered with the existing `as_of` behavior.
- Earnings-model diagnostics are filtered by row materialization time.
- Earnings-release guidance is filtered by filing acceptance time, then filing date, then reported period timing as fallback.
- Operating working-capital schedules are built only from statement balances observable at the selected `as_of`.
- Cash, debt, interest, other-income, and tax schedules are built only from statements observable at the selected `as_of`.
- Basic-share, option, warrant, RSU, repurchase, acquisition-share, and convertible inputs are built only from disclosures observable at the selected `as_of`.
- Historical charts snapshots must never use releases or derived model rows that were not observable at the requested `as_of`.

## Forecast Stability Notes

- The charts payload now labels the diagnostic as `Forecast Stability`, not `Forecast Reliability`.
- Stability is anchored to point-in-time walk-forward backtests for revenue, EBIT, EPS, and FCF across 1Y, 2Y, and 3Y horizons.
- Horizon errors are combined as a weighted APE:
  `Weighted error = 50% * 1Y + 30% * 2Y + 20% * 3Y`
- Metric errors are then combined into the empirical anchor with explicit weights:
  `Composite error = 50% * Revenue + 20% * EBIT + 15% * EPS + 15% * FCF`
- Sector templates do not replace company evidence; they only define conservative error buckets for labeling the realized backtest as `tight`, `moderate`, `wide`, or `very_wide`.
- The final score starts from the empirical error bucket, then subtracts explicit penalties for:
  - short history
  - cyclicality
  - structural breaks
  - major M&A
  - accounting restatements
  - unstable diluted share count
  - wide bull/base/bear scenario dispersion
- Missing metric backtests do not get silently zero-filled; the composite anchor reweights only across the metrics that have point-in-time realized samples at that horizon, and the metric-specific sample counts remain visible in diagnostics.
- Missing parser-confidence data is treated as a penalty, never as a boost.
