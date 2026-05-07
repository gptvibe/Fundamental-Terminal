# Research Brief Implementation Audit

Date: 2026-05-06
Scope audited: default /company/[ticker] brief flow, brief contracts, frontend composition, endpoint composition, and related tests.

## Executive Summary

- The current default page is a solid six-section Research Brief implementation (Snapshot, What Changed, Business Quality, Capital & Risk, Valuation, Monitor) with persisted bootstrap and explicit provenance/freshness UI.
- The requested seven-section target is not fully met: Understand Business is not a first-class section in contract, nav, or page composition.
- The biggest architecture risk on the current page is not the brief endpoint itself (snapshot-backed), but idle prefetch and side-panel requests that can trigger request-path compute on models/peers/equity-risk surfaces.
- Test coverage is strong for page orchestration and bootstrap behavior, but thin for route-level loading skeletons and explicit 7-section/contract parity.

## Section Audit Table

| section | current status | files involved | existing data sources | missing UI/data | provenance/freshness behavior | test coverage | risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Snapshot | Existing | frontend/app/company/[ticker]/page.tsx; frontend/app/company/[ticker]/_sections/snapshot-section.tsx; app/api/schemas/company_overview.py; app/services/company_research_brief.py | /api/companies/{ticker}/workspace-bootstrap (financials + brief), /api/companies/{ticker}/brief, cached financials + price history + segment analysis | No dedicated plain-English business model narrative in this section; no explicit SIC/business model card | Uses top-level source_mix/provenance badges and section cues; backend snapshot provenance includes sec_companyfacts primary and yahoo_finance fallback when price history is present | frontend/app/company/[ticker]/page.activity-feed.test.ts covers render/order/fallback labels; no dedicated snapshot-section unit test | Medium: section is stable, but business-context content is lighter than north-star expectations |
| Understand Business | Missing (first-class), Partial (distributed) | frontend/app/company/[ticker]/page.tsx (plain-English panel + snapshot metrics); frontend/components/company/research-brief-plain-english-panel.tsx; frontend/app/company/[ticker]/_lib/research-brief-types.ts; app/api/handlers/_shared.py (RESEARCH_BRIEF_SECTION_ORDER) | Uses existing brief models/financials and company identity data already loaded | No dedicated section id, nav entry, contract field, or section-level drill-down handoff for this question | Inherits top-level provenance/diagnostics but not represented as an explicit section provenance envelope | No explicit test asserting presence/behavior of an Understand Business section | High: direct mismatch with requested 7-section target and product-north-star structure |
| What Changed | Existing | frontend/app/company/[ticker]/_sections/what-changed-section.tsx; frontend/components/company/changes-since-last-filing-card.tsx; app/api/handlers/_shared.py (company_changes_since_last_filing, activity overview); app/services/company_research_brief.py | /api/companies/{ticker}/brief.what_changed embeds activity_overview + changes + earnings_summary; fallback endpoint /api/companies/{ticker}/changes-since-last-filing | Mostly complete; minor overlap with Monitor (same activity feed reused in two sections) | Section cues surface provenance/source mix/confidence flags for filing comparison and activity overview | frontend/app/company/[ticker]/page.activity-feed.test.ts; frontend/app/company/[ticker]/_lib/what-changed-summary.test.ts; frontend/components/company/changes-since-last-filing-card.test.ts | Medium: content is present, but overlap can cause repetition and UX duplication |
| Business Quality | Partial | frontend/components/company/brief-business-quality-section.tsx; frontend/app/company/[ticker]/page.tsx; app/services/company_research_brief.py (business_quality summary) | /api/companies/{ticker}/workspace-bootstrap financials plus /api/companies/{ticker}/brief.business_quality summary | Missing explicit restatement/reconciliation/unusual-disclosure card in this section itself; these are mostly indirect via diagnostics and other routes | Uses section cue with as_of/last_refreshed_at/provenance/source_mix/confidence flags from financials envelope | frontend/app/company/[ticker]/page.activity-feed.test.ts validates section render and empty states; component-level tests exist for underlying financial-quality widgets | Medium: section exists, but deeper quality/risk evidence is still scattered |
| Capital & Risk | Existing | frontend/app/company/[ticker]/_sections/capital-risk-section.tsx; frontend/components/company/capital-structure-intelligence-panel.tsx; app/services/company_research_brief.py; app/api/handlers/financials.py; app/api/handlers/governance.py; app/api/handlers/ownership.py | /api/companies/{ticker}/brief.capital_and_risk embeds capital_structure, capital_markets_summary, governance_summary, ownership_summary, equity_claim_risk_summary | Strong section coverage; some evidence remains drill-down only (full equity risk pack details) | Section cues include capital structure and equity claim risk provenance/source mix/confidence; governance summary can be snapshot-backed from brief when available | frontend/app/company/[ticker]/page.activity-feed.test.ts; frontend/components/company/capital-structure-intelligence-panel.test.ts | Medium: good coverage, but request-path compute risk exists for related drill-down endpoints |
| Compare & Value | Partial (implemented as Valuation) | frontend/components/company/brief-valuation-section.tsx; frontend/app/company/[ticker]/page.tsx; app/api/handlers/models.py; app/api/handlers/company_overview.py (peers route); app/services/company_research_brief.py | /api/companies/{ticker}/brief.valuation embeds models + peers; idle prefetch also calls /api/companies/{ticker}/models and /api/companies/{ticker}/peers | Label/IA differs from target wording (Compare & Value vs Valuation); no explicit compare framing card beyond peer table | Section cues include models/peers provenance and freshness; strict official mode is passed to UI | frontend/app/company/[ticker]/page.activity-feed.test.ts; frontend/lib/api.routes.test.ts route wiring | Medium-High: idle prefetch can trigger request-path model/peer compute |
| Monitor | Existing | frontend/components/company/brief-monitor-section.tsx; frontend/app/company/[ticker]/page.tsx; app/api/handlers/_shared.py (_build_company_activity_overview_response); app/services/company_research_brief.py | /api/companies/{ticker}/brief.monitor.activity_overview (same activity-overview object as What Changed), refresh state from workspace | Functionally present; duplicates content with What Changed activity panels | Strong cues for monitoring feed provenance/source mix/confidence and last_checked | frontend/app/company/[ticker]/page.activity-feed.test.ts covers monitor content and checklist behavior | Low-Medium: mostly UX duplication risk, not data availability risk |

## Endpoint/Component Mapping Notes

- Default page composition is centered on:
  - useCompanyWorkspace(... includeOverviewBrief: true) for bootstrap financials and optional brief payload.
  - useResearchBriefData() for /api/companies/{ticker}/brief fallback load if bootstrap brief is absent/incomplete.
- Brief contract currently contains six named sections plus monitor payload, but no Understand Business section object.
- Frontend nav is six items from BRIEF_SECTIONS in frontend/app/company/[ticker]/_lib/research-brief-types.ts.

## Duplicate Client Request Findings

1. Models and peers are prefetched even when brief valuation data already contains models/peers.
   - Trigger path: page.tsx idle prefetch -> frontend/lib/company-workspace-prefetch.ts -> getCompanyModels/getCompanyPeers.
   - Impact: duplicate network work; can trigger compute on request-path model/peer endpoints.

2. Filing risk signals are fetched separately from the brief contract.
   - Trigger path: page.tsx useEffect -> getCompanyFilingRiskSignals(ticker).
   - Impact: additional request on first load; useful content, but outside brief endpoint composition.

3. What Changed and Monitor intentionally reuse the same activity_overview data.
   - Current behavior is data reuse (not duplicate fetch) when brief payload is present.
   - Risk is mainly repetitive UI, not redundant API calls.

## Request-Path Live Fetch Risks

1. /api/companies/{ticker}/models can compute missing model runs on read.
   - In app/api/handlers/models.py, company_models may call ModelEngine.compute_models during request handling.
   - Exposure increases due to idle prefetch calling models route.

2. /api/companies/{ticker}/peers builds comparison on read.
   - In app/api/handlers/company_overview.py, company_peers calls build_peer_comparison.
   - Also targeted by idle prefetch.

3. /api/companies/{ticker}/equity-claim-risk builds derived payload on read.
   - In app/api/handlers/_shared.py, company_equity_claim_risk calls build_company_equity_claim_risk_response.
   - Not called by default brief render path, but used in exports/drill-down and can be expensive.

4. /api/companies/{ticker}/brief itself is snapshot-backed and not the main live-fetch risk.
   - It loads persisted CompanyResearchBriefSnapshot and returns bootstrap payload when missing.
   - No dedicated hot cache layer for /brief, but persistence path is already cache-first.

## Test Coverage: Current vs Needed

### Current relevant coverage

- Backend:
  - tests/test_company_research_brief.py (bootstrap/ready/stale/shared-snapshot behavior)
  - tests/test_api_route_inventory.py (route existence)
  - tests/test_handler_refactor_guards.py (handler registration)
  - tests/test_conditional_get_routes.py and tests/test_sec_expansion_routes.py include workspace-bootstrap/brief route behaviors.

- Frontend:
  - frontend/app/company/[ticker]/page.activity-feed.test.ts (section render/order, fallback disclosure, bootstrap behavior, no redundant brief fetch when bootstrap includes brief).
  - frontend/app/company/[ticker]/error.test.tsx (route error fallback).
  - frontend/app/company/[ticker]/_lib/what-changed-summary.test.ts.
  - frontend/lib/api.routes.test.ts (route-building for brief/bootstrap/section endpoints).

### Gaps to add/update

1. Add explicit contract parity test for seven-section target (currently impossible without Understand Business section implementation).
2. Add frontend test for loading skeleton nav chip count and labels (currently no loading.tsx test).
3. Add frontend test proving idle prefetch does not duplicate models/peers requests when brief valuation data is already present (or document why it intentionally still prefetches).
4. Add backend test ensuring RESEARCH_BRIEF_SECTION_ORDER aligns with documented IA contract.
5. Add backend test asserting /brief provenance/source_mix/confidence flags exist for every exposed section, including monitor.
6. Add integration test that /brief remains snapshot-backed under stale/missing scenarios and does not trigger request-path recomputation.

## Recommended Sequence of Small PRs

1. PR 1: Align contract and docs on section taxonomy.
   - Decide whether target is six sections + monitor or full seven including Understand Business.
   - Update docs and section-order constants together to remove ambiguity.

2. PR 2: Add first-class Understand Business section shell using existing persisted inputs.
   - Reuse existing company identity, segment/geography, and plain-English signals before introducing new backend dependencies.

3. PR 3: Wire nav/loading/state models to include Understand Business.
   - Update BRIEF_SECTIONS, loading skeleton chips, section status labels, and section order tests.

4. PR 4: Reduce duplicate/extra client requests.
   - Gate idle prefetch of models/peers when brief valuation data is already present and fresh.
   - Keep filing-risk-signals as optional deferred panel fetch.

5. PR 5: Keep brief path persisted-first and document compute-heavy drill-down routes.
   - Explicitly classify models/peers/equity-risk routes as drill-down compute surfaces in docs.

6. PR 6: Add loading/error and section-contract parity tests.
   - Add loading.tsx test and contract parity backend tests.

7. PR 7: Add provenance/freshness completeness tests for all brief sections.
   - Ensure each section exposes provenance/source_mix/as_of/last_refreshed_at/confidence flags as expected.

8. PR 8: Optional polish pass for Monitor vs What Changed de-duplication in UI.
   - Keep shared data object but reduce repeated cards/text for clearer narrative flow.

## Implementation Checklist

- [ ] Resolve six-vs-seven section contract mismatch in docs + constants.
- [ ] Introduce Understand Business as first-class section (if seven-section target is confirmed).
- [ ] Update frontend section nav and loading skeleton to match final section set.
- [ ] Audit and trim idle prefetch duplicates for models/peers when brief already has data.
- [ ] Keep /brief snapshot-backed behavior as default path; avoid adding request-path recompute.
- [ ] Add missing tests for loading skeleton, section parity, and provenance completeness.
- [ ] Re-run existing brief page tests and API route tests after section-contract changes.
