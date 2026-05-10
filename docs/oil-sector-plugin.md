# Oil Sector Plugin

The oil sector plugin adds an optional workbench for U.S. oil-company equities. It layers
official EIA benchmark curves, SEC-disclosed oil-price sensitivities, and fair-value scenario
math on top of the core research brief. It is **disabled by default** so the general U.S.
equities experience is unaffected.

## What the plugin provides

| Surface | Path / endpoint |
|---|---|
| Oil workspace page | `/company/[ticker]/oil` |
| Oil scenario overlay API | `GET /api/companies/{ticker}/oil-scenario-overlay` |
| Oil scenario (computed) API | `GET /api/companies/{ticker}/oil-scenario` |
| Oil tab in company subnav | Shown only for oil-exposed companies when plugin is enabled |

### Covered exposure types

| Type | Support status |
|---|---|
| Upstream E&P | `supported` |
| Integrated | `supported` |
| Refiner | `partial` |
| Midstream / pipeline | `unsupported` (v1) |
| Oilfield services | `unsupported` (v1) |

### Data provenance (official sources only)

- **EIA Petroleum Spot Prices** (`eia_petroleum_spot_prices`) — WTI / Brent daily spot history
- **EIA Short-Term Energy Outlook** (`eia_steo`) — official near-term price baseline
- **SEC EDGAR** (`sec_edgar`) — issuer-disclosed $/barrel sensitivity and realized price tables
- **Fundamental Terminal Oil Scenario Overlay** (`ft_oil_scenario_overlay`) — persisted overlay payload derived from the above

## Enabling the plugin

### Backend

Set the environment variable before starting the API server:

```bash
export ENABLE_OIL_SCENARIOS=true
```

Or add it to your `.env` / Docker Compose environment block:

```yaml
environment:
  ENABLE_OIL_SCENARIOS: "true"
```

When the variable is absent or `false`, the two oil API routes return HTTP 404 with a clear
message and no oil-related data is fetched or served.

### Frontend

Set the corresponding Next.js public environment variable:

```bash
export NEXT_PUBLIC_ENABLE_OIL_SCENARIOS=true
```

When this variable is absent or not `"true"`:
- The Oil tab is hidden in the company subnav for all companies.
- Navigating directly to `/company/[ticker]/oil` shows a "plugin not enabled" notice.

### Local development example

```bash
# Backend
ENABLE_OIL_SCENARIOS=true uvicorn app.main:app --reload

# Frontend
NEXT_PUBLIC_ENABLE_OIL_SCENARIOS=true npm --prefix frontend run dev
```

## Architecture

The oil plugin code lives in two main areas:

```
app/services/
  oil_scenario.py                 # Public payload builder (orchestrator)
  oil_scenario_overlay.py         # Persistence helpers (read/write overlay cache)
  oil_scenario_overlay_persistence.py
  oil_overlay_engine.py           # Fair-value overlay math
  oil_exposure.py                 # SIC/sector classification
  oil_company_evidence.py         # SEC filing parser (sensitivity, realized prices)
  official_oil_inputs.py          # EIA data fetcher (spot prices + STEO)
  sector_plugins/oil/
    __init__.py                   # Plugin namespace re-exporting all public APIs

app/api/
  handlers/models.py              # company_oil_scenario + company_oil_scenario_overlay
  routers/models.py               # Route registration (always registered; handlers gate by flag)
  schemas/oil_scenario.py         # Pydantic response models

frontend/
  app/company/[ticker]/oil/page.tsx             # Oil workspace page
  components/models/oil-scenario-overlay-panel.tsx  # Workbench UI
  lib/oil-overlay.ts              # Client-side overlay engine
  lib/oil-workspace.ts            # Utilities including isOilScenariosEnabled()
```

### Handler gate

`_is_oil_scenarios_enabled()` in `app/api/handlers/_shared.py` returns `False` by default.
Both oil handlers call it at the top and raise `HTTP 404` when it returns `False`. The function
is a wrapper (not a module constant) so it can be monkey-patched in tests independently.

### Sector plugins namespace

`app/services/sector_plugins/oil/__init__.py` re-exports all public oil service APIs, giving
the plugin its own discoverable namespace alongside the other sector data providers
(`bts_airlines`, `eia_power`, `fhfa_housing`, etc.).

## Tests

Oil-specific tests that require the plugin to be active patch the handler flag:

```python
_patch_handler_namespaces(monkeypatch, "_is_oil_scenarios_enabled", lambda: True)
```

All other tests run with the default (disabled) and are unaffected by the oil plugin.

## EIA API key

The EIA data fetcher uses `settings.eia_api_key` (env var `EIA_API_KEY`). Without a key the
EIA endpoints still work at a lower rate limit. Set the key for production use:

```bash
export EIA_API_KEY=your_key_here
```
