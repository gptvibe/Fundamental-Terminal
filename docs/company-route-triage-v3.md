# Company Route Triage V3

## Scope

This document inventories the current frontend company routes under frontend/app/company/[ticker] and classifies each route for the product reset described in docs/product-north-star-v3.md.

This is a navigation and information-architecture triage, not a route-deletion plan. Existing paths stay intact.

## Triage Labels

- Primary workflow surface: A route that deserves first-class visibility in the main company navigation because it maps directly to a core research job.
- Drill-down: A route that expands a Research Brief section with deeper evidence, tables, timelines, or workflow-specific analysis.
- Appendix: A specialist route that is still useful, but is not required in the first-pass research read for most companies.
- Merge candidate: A route whose concept should be absorbed into Research Brief or another surface for navigation purposes, while the URL itself remains live for deep links, direct entry, and compatibility.

## Current Route Inventory

| Route | Current role | Primary workflow step | Triage | Proposed handling |
| --- | --- | --- | --- | --- |
| /company/[ticker] | Mixed overview with price, segments, changes, metrics, peer module, and research pulse | All steps | Primary workflow surface | Recast as Research Brief and make it the clear default landing surface |
| /company/[ticker]/financials | Full statement history, quality diagnostics, segment analysis, capital structure, and detailed charts | Understand business; assess business quality | Primary workflow surface | Keep as the main deep financial evidence page |
| /company/[ticker]/models | Valuation workbench, model diagnostics, market context, sector context, and evaluation summary | Compare and value | Primary workflow surface | Keep as the main underwriting and valuation page |
| /company/[ticker]/peers | Peer comparison dashboard for valuation, quality, and growth context | Compare and value | Primary workflow surface | Keep as the main comparative analysis page |
| /company/[ticker]/earnings | Release-level earnings analysis, guidance, trend context, and earnings-specific backtests | Detect what changed | Drill-down | Keep as a release-specific drill-down linked from the What Changed section |
| /company/[ticker]/filings | SEC filing timeline, parser snapshot, filing events, and document viewer | Detect what changed | Drill-down | Keep as the core filing-evidence drill-down |
| /company/[ticker]/events | 8-K event classification and current-report timeline | Detect what changed; monitor | Drill-down | Keep as a focused current-report intelligence page |
| /company/[ticker]/capital-markets | Financing signals, dilution context, registration filings, and financing-related current reports | Assess capital, risk, and dilution | Drill-down | Keep as the financing and capital-raising deep dive |
| /company/[ticker]/governance | Proxy filings, meeting history, vote outcomes, and executive compensation | Assess governance and risk | Drill-down | Keep as the proxy and governance deep dive |
| /company/[ticker]/ownership-changes | 13D and 13G stake changes, amendment chains, and activist signals | Assess governance and risk | Drill-down | Keep as the major-holder change drill-down |
| /company/[ticker]/ownership | 13F institutional holdings, manager activity, and smart-money trend context | Monitor; supporting context | Appendix | Keep reachable from Brief and specialist menus, but not primary nav |
| /company/[ticker]/insiders | Form 4 and Form 144 insider activity | Monitor; supporting risk context | Appendix | Keep reachable from Brief and specialist menus, but not primary nav |
| /company/[ticker]/sec-feed | Unified SEC activity stream across filings, events, governance, ownership, insiders, and Form 144 | Monitor | Merge candidate | Absorb key alert and timeline value into the Research Brief Monitor section; keep route live for full chronological review |
| /company/[ticker]/stakes | Legacy redirect to ownership-changes | Legacy compatibility | Merge candidate | Keep redirect only; do not expose in navigation |

## Recommended Navigation End State

### Primary company navigation

- Brief
- Financials
- Models
- Peers

### Secondary research menu

- Filings
- Earnings
- Events
- Capital Markets
- Governance
- Stake Changes

### Appendix access

- Ownership
- Insiders

### Hidden but preserved

- SEC Feed
- Stakes redirect

## Why This Triage Improves The Product

- It reduces the number of top-level decisions the user must make before getting oriented.
- It aligns navigation with investor jobs rather than dataset names.
- It keeps specialist evidence available without letting every page compete equally for attention.
- It preserves current route stability and deep-link compatibility.
- It makes the default company page strong enough to earn the phrase research workstation.

## Research Brief Mapping

| Research Brief section | Supporting current routes |
| --- | --- |
| Understand business | /company/[ticker]/financials, /company/[ticker]/filings |
| Detect what changed | /company/[ticker]/filings, /company/[ticker]/earnings, /company/[ticker]/events |
| Assess business quality | /company/[ticker]/financials, /company/[ticker]/earnings |
| Assess capital, risk, dilution, and governance | /company/[ticker]/capital-markets, /company/[ticker]/governance, /company/[ticker]/ownership-changes, /company/[ticker]/ownership, /company/[ticker]/insiders |
| Compare and value | /company/[ticker]/peers, /company/[ticker]/models |
| Monitor | /company/[ticker]/sec-feed, /company/[ticker]/events, /company/[ticker]/ownership, /company/[ticker]/insiders |

## Route-Specific Notes

### /company/[ticker]

- Rename the product concept from Overview to Research Brief.
- Keep the route path unchanged.
- Replace mixed-module ordering with the six-step research sequence.

### /company/[ticker]/financials

- This should remain the most detailed accounting and statement-quality surface.
- Do not overload the default brief with full-table behavior that belongs here.

### /company/[ticker]/models and /company/[ticker]/peers

- These remain primary because valuation and comparison are core investor jobs.
- Research Brief should summarize them, not replace them.

### /company/[ticker]/filings, /earnings, and /events

- These are best understood as expansions of the Detect what changed workflow step.
- The brief should surface the answer quickly, then hand off to these routes for evidence.

### /company/[ticker]/capital-markets, /governance, and /ownership-changes

- These are not noise pages. They are high-value risk and capital-allocation drill-downs.
- They should stay visible in a More Research pattern because they often change the thesis.

### /company/[ticker]/ownership and /insiders

- These are useful supporting signals, but they are usually not the first page an investor needs to open.
- They fit better as appendix routes linked from Monitor and Capital/Risk sections.

### /company/[ticker]/sec-feed

- The unified feed is valuable, but much of its user value overlaps with the current Research Pulse concept and the new Monitor section.
- Make the Monitor section good enough that SEC Feed becomes optional rather than required.

### /company/[ticker]/stakes

- Keep it as a compatibility alias only.
- Do not spend product complexity on a second name for the same concept.

## Implementation Constraints

- Keep all existing routes intact.
- Do not move orchestration into routers.
- If the brief needs new summary data, add service-backed persisted summaries and serialize them through app.main.
- Prefer composing the brief from existing persisted endpoints before introducing new ones.
- Keep Yahoo use limited to clearly labeled price and market-profile context.

## Acceptance Criteria For Triage

- Every current company route has one explicit triage label.
- The default company route is positioned as Research Brief.
- The primary company nav is reduced to the smallest coherent set of daily-use surfaces.
- Drill-down and appendix routes remain reachable without changing URLs.
- Merge candidates stay live but lose unnecessary nav prominence.
- The route plan reinforces a single SEC-first investor workflow instead of a page catalog.