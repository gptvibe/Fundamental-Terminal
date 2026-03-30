# Product North Star V3

## Positioning

Fundamental Terminal should be the best free, official-source-first U.S. equity research workstation.

That positioning has three concrete meanings:

- Best means the product should feel like one coherent research workflow, not a loose collection of capable pages.
- Free means serious bottoms-up equity research should be possible without paying for vendor terminals.
- Official-source-first means the trust model is visible in the product, not hidden in backend implementation details.

## Product Reset

The product already has strong SEC-first dataset coverage across financials, filings, earnings, ownership, governance, capital markets, and valuation. The reset is not about broadening scope. It is about reorganizing that coverage into one clear investor workflow.

The default company experience should stop behaving like an overview page and start behaving like a Research Brief.

Research Brief is the default reading surface for /company/[ticker]. It should answer, in order, the six questions an investor actually needs answered:

1. Understand business.
2. Detect what changed.
3. Assess business quality.
4. Assess capital, risk, dilution, and governance.
5. Compare and value.
6. Monitor.

Everything else in the company workspace should support one of those six jobs.

## Who The Product Is For

- Self-directed investors researching U.S. public equities.
- Small teams and independent analysts doing bottoms-up company work.
- Users who care about source provenance, filing evidence, and point-in-time trust.

## What The Product Is Not

- Not a generic market terminal.
- Not a real-time trading cockpit.
- Not a macro dashboard with a stock screener attached.
- Not a news firehose.
- Not a consumer finance app.

The product should go deeper on SEC-first equity research rather than wider across unrelated asset classes or high-frequency use cases.

## Product Principles

- Start from official public evidence for fundamentals, analytics, ownership, governance, and filing intelligence.
- Use Yahoo only as a clearly labeled fallback for price and market-profile context.
- Prefer persisted endpoints and cache-backed reads over request-path live fetches.
- Keep routers thin and keep ingestion, normalization, persistence, analytics, and refresh orchestration in services.
- Preserve app.main as the compatibility boundary for current public API contracts.
- Treat a dataset as unfinished until it ships as a full vertical slice: ingestion, normalization, persistence, API, frontend, refresh and cache wiring, tests, and docs.
- Keep route URLs stable unless there is an explicit redirect or alias decision.
- Favor coherence, hierarchy, and trust over page count.

## Primary Workflow

| Workflow step | Investor question | What the default Research Brief must answer | Main supporting routes |
| --- | --- | --- | --- |
| Understand business | What does this company do, how does it make money, and what are the important moving parts? | Business model, segment and geography mix, basic operating history, high-level context, source and freshness state | /company/[ticker]/financials, /company/[ticker]/filings |
| Detect what changed | What is new since the last filing, quarter, or review? | Latest filing deltas, earnings release changes, recent 8-Ks, new governance or ownership events, top alerts | /company/[ticker]/filings, /company/[ticker]/earnings, /company/[ticker]/events |
| Assess business quality | Is the business getting stronger, weaker, or just noisier? | Growth, margins, cash generation, balance-sheet quality, segment economics, accounting quality, restatement or reconciliation concerns | /company/[ticker]/financials, /company/[ticker]/earnings |
| Assess capital, risk, dilution, and governance | Can the equity claim be diluted, impaired, or misgoverned? | Debt burden, maturity and lease profile, dilution bridges, financing activity, proxy signals, insiders, major stake changes | /company/[ticker]/capital-markets, /company/[ticker]/governance, /company/[ticker]/ownership-changes, /company/[ticker]/insiders, /company/[ticker]/ownership |
| Compare and value | How does this company stack up and what is a reasonable valuation range? | Peer context, valuation summary, model confidence, downside/upside framing, key assumption risk | /company/[ticker]/peers, /company/[ticker]/models |
| Monitor | What should I keep watching after I leave this page? | Active alerts, recent SEC activity, refresh state, next review triggers, latest source dates | /company/[ticker]/sec-feed, /company/[ticker]/events, /watchlist |

## Research Brief Information Architecture

The new default /company/[ticker] should be a Research Brief with ordered sections that mirror the workflow above.

### 1. Snapshot

- Company identity, sector, CIK, freshness, and source ribbon.
- Short thesis-oriented summary strip: revenue, free cash flow, balance-sheet posture, and current alert count.
- Right rail actions stay utility-first: refresh, export, open models, save to watchlist.

### 2. Understand Business

- Plain-English business summary.
- Segment and geography mix.
- Core operating history and price-versus-fundamentals context, with fallback labeling if price context is from Yahoo.
- Direct links to the full Financials and Filings workspaces.

### 3. What Changed

- Changes since last filing card.
- Latest earnings release summary.
- Recent 8-K events and filing timeline highlights.
- Latest governance, ownership-change, and insider developments when present.

### 4. Business Quality

- Revenue, margin, free-cash-flow, and return-quality summary.
- Financial quality diagnostics and reconciliation status.
- Restatement, unusual disclosure, and segment-mix changes when relevant.
- Clear path into full statement tables and historical detail.

### 5. Capital, Risk, Dilution, And Governance

- Capital structure summary.
- Debt ladder, lease burden, payout mix, stock-based compensation, and dilution bridge summary.
- Financing events, proxy signals, insider activity, and 13D or 13G stake changes.
- This section should answer whether the equity claim is being protected or diluted.

### 6. Compare And Value

- Peer comparison snapshot.
- Valuation summary with model status, confidence, and main assumptions.
- Link-outs into full Models and Peers workspaces for underwriting detail.

### 7. Monitor

- Priority alerts.
- Chronological recent SEC activity.
- Refresh state and last checked timestamps.
- Short monitor checklist for what the user should revisit next.

## Navigation Policy

The company workspace should become more hierarchical.

- Research Brief is the default landing surface.
- Primary navigation should emphasize the smallest set of surfaces needed for daily research.
- Specialized datasets stay reachable, but they should stop competing equally for top-level attention.

Recommended primary company navigation:

- Brief
- Financials
- Models
- Peers

Recommended secondary research menu:

- Filings
- Earnings
- Events
- Capital Markets
- Governance
- Stake Changes

Recommended appendix access:

- Ownership
- Insiders

Merge candidates should remain live as routes, but no longer deserve first-class nav prominence once equivalent brief sections exist.

## Route And Data Implications

- Keep all existing company routes intact.
- Build Research Brief from existing persisted company endpoints wherever possible.
- If a new summary payload is required, add it in services and serialize it through app.main. Do not move orchestration into routers.
- Do not broaden source usage to support the new IA. The reset is about structure, not relaxing trust policy.
- Do not introduce new request-path live fetches for core brief sections.

## Migration Sequence

### Phase 1: Reframe The Product

- Update product copy from Overview to Research Brief.
- Update docs and UX language to describe the six-step investor workflow.
- Preserve all existing route paths and API contracts.

### Phase 2: Rebuild /company/[ticker] As Research Brief

- Keep the same route.
- Reorder the current overview content into the six workflow sections.
- Pull summary cards from existing persisted surfaces before inventing new data dependencies.

### Phase 3: Add Drill-Down Hand-Offs

- Every major Research Brief section should link to one or more full drill-down pages.
- Each drill-down page should make it obvious which Research Brief question it expands.

### Phase 4: Tighten Navigation Hierarchy

- Promote Brief, Financials, Models, and Peers as the core company nav.
- Move lower-frequency specialist routes into a More Research or appendix pattern.
- Demote merge candidates from primary navigation without deleting their routes.

### Phase 5: Close Data And Test Gaps

- Fill missing summary payloads only where the brief still feels thin.
- Keep new backend work inside services and persistence layers.
- Add deterministic tests for route stability, section presence, source labeling, and navigation hierarchy.

## Acceptance Criteria

- /company/[ticker] reads as a Research Brief rather than a generic overview page.
- The default company page covers all six workflow questions without requiring users to hunt across many tabs.
- Existing company routes remain intact, including the current legacy redirect behavior.
- Core brief sections are backed by persisted or cache-first data, not request-path live fetches.
- Fundamentals and analytics remain official-source-first, with Yahoo only as a clearly labeled fallback for price or market-profile context.
- Provenance, freshness, and confidence cues remain visible on the default company surface.
- Every specialist route has an explicit role: primary surface, drill-down, appendix, or merge candidate.
- Primary navigation becomes more focused, while drill-down routes remain directly reachable.
- Any implementation work needed for new brief summaries respects the documented architecture boundaries.
- Deterministic tests are in place for route stability and the new company information hierarchy.