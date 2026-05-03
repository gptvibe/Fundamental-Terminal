# SEC Comment-Letter Document Enrichment MVP

Status: Discovery only. Do not treat this dataset as newly shipped from this document alone.

## Goal

Investigate the next step for SEC issuer correspondence coverage without creating a half-built pipeline. The codebase already ships a cache-first metadata slice for `CORRESP` filings. The open question is whether to extend that slice into document-level issuer correspondence research.

## Current State

### What already exists

- `app/services/sec_edgar.py` already reads SEC submissions JSON, builds a filing index, filters `CORRESP` filings, and normalizes them into `NormalizedCommentLetter` rows.
- The current normalized payload is intentionally thin: `accession_number`, `filing_date`, `description`, and `sec_url`.
- `refresh_comment_letters` persists those rows into the `comment_letters` table and updates dataset freshness through the existing SEC refresh orchestration.
- `GET /api/companies/{ticker}/comment-letters` is already a cache-first endpoint. It reads persisted rows and only triggers background refresh when the cache is missing or stale.
- Comment-letter metadata is already surfaced in the frontend and derived company-research views:
  - `/company/[ticker]/sec-feed`
  - activity feed entries and alerts
  - filing change summaries / research brief counts
- There is existing migration and test coverage for the metadata slice.

### What is not represented today

- No document body or cleaned text is persisted.
- No separation of SEC staff letters vs issuer response letters.
- No thread-level grouping across a correspondence exchange.
- No extracted topics, staff comments, response dates, or notable disclosure areas.
- No document-format handling beyond archive URLs; PDF or exhibit-heavy correspondence is not normalized.
- No dedicated UI for reading or comparing correspondence content.

## Assessment

Issuer correspondence is currently collected and shipped as metadata-only `CORRESP` coverage. It is not ignored, and it is not an unfinished greenfield dataset. The missing work is a second-stage vertical slice for document enrichment and research UX.

That means the implementation should extend the existing `comment_letters` dataset rather than introduce a second overlapping dataset with separate refresh semantics.

## Best Source Path

### Recommended acquisition path

1. Use the existing submissions feed (`data.sec.gov/submissions/CIK{cik}.json` plus the additional `filings.files` JSON pages) as the authoritative index of candidate `CORRESP` accessions.
2. Continue using the existing filing index fields for cheap metadata discovery:
   - `form`
   - `filingDate`
   - `acceptanceDateTime`
   - `primaryDocument`
   - `primaryDocDescription`
3. For each candidate accession selected for enrichment, fetch the filing directory manifest from the archive `index.json` path.
4. Resolve the primary correspondence document from that manifest and fetch the document from the archive URL.

### Why this is the best path

- It matches the current ingestion architecture instead of creating a special-purpose crawler.
- It preserves the existing cache-first request-path contract.
- It gives both stable metadata discovery and deterministic archive URLs for persisted documents.
- It avoids using SEC search pages or ad hoc request-time scraping.

### Non-goals for the MVP

- No live SEC fetches from request handlers.
- No OCR pipeline for scanned PDFs.
- No attempt to backfill every exhibit in a correspondence folder.
- No speculative LLM summarization in the ingestion path.

## Proposed MVP Vertical Slice

This MVP should be framed as comment-letter document enrichment, not as initial comment-letter ingestion.

### Ingestion scope

- Start from already indexed `CORRESP` accessions.
- For each accession, attempt to fetch one primary correspondence document when the archive contains a text-like file (`.htm`, `.html`, `.txt`).
- Record document format and archive URL even when the document cannot be text-parsed.
- Extract a plain-text body for HTML/TXT documents only.
- Add lightweight heuristics for:
  - `correspondent_role`: `sec_staff | issuer | unknown`
  - `document_kind`: `comment_letter | response_letter | transmittal | other`
- Preserve existing metadata rows even when document enrichment fails.

### Normalized schema

Recommended model shape:

- Keep `comment_letters` as the accession-level parent row.
- Extend it with enrichment fields needed for the document slice:
  - `acceptance_datetime`
  - `primary_document`
  - `document_url`
  - `document_format`
  - `correspondent_role`
  - `document_kind`
  - `thread_key`
  - `document_text`
  - `document_text_sha256`
  - `text_extracted_at`
  - `parser_version`

If row size or future exhibit handling becomes a concern, split `document_text` into a child table later. For the MVP, a single accession-level row keeps the migration and cache query surface smaller.

### Database table / migration

Preferred migration strategy:

- Alter the existing `comment_letters` table instead of creating a new sibling dataset.
- Add nullable enrichment columns first.
- Backfill opportunistically through the normal refresh job rather than a blocking one-time migration job.

Rationale:

- The current table already defines the accession-level identity.
- Reusing the table avoids duplicate freshness state and duplicate provenance wiring.
- Existing APIs and research surfaces already depend on this dataset name.

### API endpoint

Reuse the existing list route and add one detail route.

- Keep `GET /api/companies/{ticker}/comment-letters` as the cache-first summary list.
- Expand list items with enrichment metadata that is cheap to render:
  - `acceptance_datetime`
  - `correspondent_role`
  - `document_kind`
  - `has_document_text`
  - `document_format`
- Add `GET /api/companies/{ticker}/comment-letters/{accession}` for cached detail payload:
  - accession metadata
  - archive/document URLs
  - extracted text or extracted excerpt blocks
  - parser version and confidence flags
  - refresh metadata / provenance

This keeps the existing surface stable while adding a clear place for document content.

### Frontend surface

MVP recommendation:

- Keep the current comment-letter list on `/company/[ticker]/sec-feed`.
- Add a cached detail panel or drawer opened from each list item.
- Surface three research signals in the list and detail views:
  - whether the row is likely SEC staff or issuer-authored
  - whether document text is available
  - any extracted disclosure topics / flags

Optional follow-on surface after MVP:

- Add a dedicated correspondence page if the dataset proves dense enough to justify filtering, threading, and topic pivots.

### Cache / refresh behavior

- Continue to treat company research endpoints as cache-first.
- Do not fetch correspondence documents inside request handlers.
- Extend the existing `refresh_comment_letters` dataset job so one run can:
  - discover new `CORRESP` accessions from submissions
  - enrich missing document fields for existing rows
  - update dataset freshness only after persistence succeeds
- Keep route behavior consistent with the current pattern:
  - return persisted rows immediately
  - trigger background refresh on `missing` or `stale`
  - never block the request on SEC archive fetches

### Tests and fixtures

Required coverage for the MVP slice:

- `sec_edgar` unit tests for:
  - selecting `CORRESP` candidates from submissions
  - choosing the archive primary document
  - extracting text from representative HTML and TXT correspondence
  - handling PDF-only or unsupported documents without breaking metadata persistence
- persistence tests for the altered `comment_letters` schema
- route tests for:
  - enriched list payload
  - detail payload
  - cache-first behavior when enrichment is stale or missing
- frontend tests for:
  - sec-feed list rendering with enrichment badges
  - detail drawer / panel states
  - empty and unsupported-document states
- fixtures:
  - one SEC staff comment letter HTML sample
  - one issuer response HTML sample
  - one unsupported/PDF-only archive manifest sample

## Recommended Definition Of Done

Do not mark this work shipped until all of the following are true:

- `CORRESP` document enrichment persists in PostgreSQL.
- The list and detail APIs are cache-first and provenance-complete.
- The frontend can inspect cached correspondence content without live SEC fetches.
- Refresh orchestration and stale-cache behavior are tested.
- Parser, persistence, API, and UI fixtures cover the supported document formats.

## Risks

### Document-format variability

Some correspondence filings will be HTML/TXT, while others may rely on PDF attachments or sparse transmittal documents. The MVP should explicitly treat PDF-only correspondence as unsupported-but-tracked rather than pretending the content was parsed.

### Thread reconstruction

The SEC archive does not guarantee a clean thread identifier. Matching staff letters to issuer responses may require heuristics on accession timing, descriptions, and filenames. Threading should remain best-effort in MVP.

### Storage footprint

Persisting full cleaned text increases row size and hot-query cost. If query latency or table bloat becomes noticeable, move text into a child table or separate blob store in a follow-up.

### Historical completeness

The existing submissions walker already traverses extra filing pages, but correspondence history may still be uneven for older issuers. The rollout should tolerate partial backfills.

### Noise and relevance

Not every `CORRESP` item is equally useful to end users. Some will be transmittal or procedural. Topic extraction and UI ranking should assume mixed signal quality.

## Estimated PR Breakdown

1. Backend enrichment plumbing
   - Extend `comment_letters` schema and refresh job.
   - Add archive-document selection and text extraction for HTML/TXT.
   - Add parser and persistence tests.

2. API contract expansion
   - Extend list payload.
   - Add comment-letter detail endpoint.
   - Add provenance and cache-state route tests.

3. Frontend sec-feed enrichment
   - Add badges and detail panel.
   - Add frontend types and render tests.

4. Research-surface follow-through
   - Add any topic/count rollups to activity overview or filing-change summaries only after the detail slice is stable.
   - Keep this PR separate if signal design is still moving.

## Recommendation

Do not open an implementation PR that only fetches archive documents or only adds a table. The next implementation should be a full document-enrichment vertical slice on top of the already shipped metadata dataset.