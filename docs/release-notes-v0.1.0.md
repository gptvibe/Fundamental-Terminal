# Release Notes Draft - v0.1.0

Release date: 2026-05-06

## Summary

Fundamental Terminal v0.1.0 is the first public release of an official-source-first research workspace for U.S. public equities.

## Highlights

- Research launcher with ticker/company search and workspace entry points.
- Company overview workspace with filing-driven context and summary framing.
- Financial charts workspace for reported history and scenario views.
- Watchlist workspace for local triage and follow-up.
- Data Sources workspace for provenance, freshness, and source health visibility.
- Dockerized backend, worker, and frontend runtime for reproducible deployment.

## Reliability and Operations

- Cache-first request paths with background refresh orchestration.
- Health checks and deployment compatibility validation.
- Release smoke checks for key backend and frontend routes.

## Docker Quickstart Profiles

- Lite profile for lower-resource hosts.
- Normal profile for default deployments.
- Optional local source build profile using Docker Compose build override.

## Notes

- Not investment advice.
- Coverage is focused on U.S. public equities.
- Source freshness depends on upstream availability and refresh throughput.

## Verification Checklist (for publish)

- README updated for release clarity and quickstart.
- Public screenshots updated: home/search, company overview, financial charts, watchlist, data sources.
- Changelog entry present for v0.1.0.
- Docker normal and lite startup verified.
- CI checks pass.
