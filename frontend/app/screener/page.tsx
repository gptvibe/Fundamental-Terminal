"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MetricConfidenceBadge, type MetricConfidenceMetadata } from "@/components/ui/metric-confidence-badge";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useLocalScreener } from "@/hooks/use-local-screener";
import { showAppToast } from "@/lib/app-toast";
import { getOfficialScreenerMetadata, getSecFramesScreener, searchOfficialScreener } from "@/lib/api";
import { exportRowsToCsv } from "@/lib/export";
import {
  DEFAULT_LOCAL_SCREENER_DRAFT,
  areLocalScreenerDraftsEqual,
  buildOfficialScreenerSearchRequest,
  countActiveScreenerFilters,
  parseTickerUniverse,
  type LocalScreenerDraft,
} from "@/lib/local-screener";
import { formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  OfficialScreenerMetadataResponse,
  OfficialScreenerSearchResponse,
  SecFramesScreenerResponse,
  ScreenerFilterDefinitionPayload,
  ScreenerFilterInputPayload,
  ScreenerMatchFilterPayload,
  ScreenerRankingDefinitionPayload,
  ScreenerRankingScoreKey,
  ScreenerResultPayload,
  ScreenerSortField,
} from "@/lib/types";

type NumericFilterField =
  | "revenue_growth_min"
  | "operating_margin_min"
  | "fcf_margin_min"
  | "shareholder_yield_min"
  | "leverage_ratio_max"
  | "dilution_max"
  | "sbc_burden_max"
  | "max_filing_lag_days";

type RankingColumnConfig = {
  key: ScreenerRankingScoreKey;
  label: string;
  sortField: ScreenerSortField;
  tone: "positive" | "risk";
};

type MetricColumnConfig = {
  field: "revenue_growth" | "operating_margin" | "fcf_margin" | "leverage_ratio" | "dilution" | "sbc_burden" | "shareholder_yield" | "filing_lag_days";
  label: string;
  sortField: ScreenerSortField;
};

type SortOption = {
  field: ScreenerSortField;
  label: string;
  note: string;
};

const NUMERIC_FILTERS: NumericFilterField[] = [
  "revenue_growth_min",
  "operating_margin_min",
  "fcf_margin_min",
  "shareholder_yield_min",
  "leverage_ratio_max",
  "dilution_max",
  "sbc_burden_max",
  "max_filing_lag_days",
];

const RANKING_COLUMNS: RankingColumnConfig[] = [
  { key: "quality", label: "Quality (0–100)", sortField: "quality_score", tone: "positive" },
  { key: "value", label: "Value (0–100)", sortField: "value_score", tone: "positive" },
  { key: "capital_allocation", label: "Capital Alloc. (0–100)", sortField: "capital_allocation_score", tone: "positive" },
  { key: "dilution_risk", label: "Dilution Risk (0–100)", sortField: "dilution_risk_score", tone: "risk" },
  { key: "filing_risk", label: "Filing Risk (0–100)", sortField: "filing_risk_score", tone: "risk" },
];

const METRIC_COLUMNS: MetricColumnConfig[] = [
  { field: "revenue_growth", label: "Rev Growth (%)", sortField: "revenue_growth" },
  { field: "operating_margin", label: "Op Margin (%)", sortField: "operating_margin" },
  { field: "fcf_margin", label: "FCF Margin (%)", sortField: "fcf_margin" },
  { field: "leverage_ratio", label: "Leverage (×)", sortField: "leverage_ratio" },
  { field: "dilution", label: "Dilution (%)", sortField: "dilution" },
  { field: "sbc_burden", label: "SBC Burden (%)", sortField: "sbc_burden" },
  { field: "shareholder_yield", label: "Sh. Yield (%)", sortField: "shareholder_yield" },
  { field: "filing_lag_days", label: "Filing Lag (days)", sortField: "filing_lag_days" },
];

const SORT_FIELD_LABELS: Record<ScreenerSortField, string> = {
  ticker: "Ticker",
  period_end: "Period end",
  revenue_growth: "Revenue growth",
  operating_margin: "Operating margin",
  fcf_margin: "FCF margin",
  leverage_ratio: "Leverage",
  dilution: "Dilution",
  sbc_burden: "SBC burden",
  shareholder_yield: "Shareholder yield",
  filing_lag_days: "Filing lag",
  restatement_count: "Restatement count",
  quality_score: "Quality score",
  value_score: "Value score",
  capital_allocation_score: "Capital allocation score",
  dilution_risk_score: "Dilution risk score",
  filing_risk_score: "Filing risk score",
};

const LIMIT_OPTIONS = [25, 50, 100, 200];

export default function OfficialScreenerPage() {
  const { hydrated, draft, presets, presetCount, updateDraft, resetDraft, savePreset, deletePreset, applyPreset } = useLocalScreener();
  const [metadata, setMetadata] = useState<OfficialScreenerMetadataResponse | null>(null);
  const [metadataLoading, setMetadataLoading] = useState(true);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [results, setResults] = useState<OfficialScreenerSearchResponse | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [presetName, setPresetName] = useState("");
  const [initialSearchStarted, setInitialSearchStarted] = useState(false);
  const [lastExecutedDraft, setLastExecutedDraft] = useState<LocalScreenerDraft | null>(null);
  const requestIdRef = useRef(0);
    const [useOfficialOnly, setUseOfficialOnly] = useState(false);
    const [secFramesData, setSecFramesData] = useState<SecFramesScreenerResponse | null>(null);
    const [secFramesLoading, setSecFramesLoading] = useState(false);
    const [secFramesError, setSecFramesError] = useState<string | null>(null);

  const filterMap = useMemo(
    () => new Map((metadata?.filters ?? []).map((definition) => [definition.field, definition])),
    [metadata?.filters]
  );
  const rankingMap = useMemo(
    () => new Map((metadata?.rankings ?? []).map((definition) => [definition.score_key, definition])),
    [metadata?.rankings]
  );
  const sortOptions = useMemo(() => buildSortOptions(metadata), [metadata]);
  const selectedSortOption = useMemo(
    () => sortOptions.find((option) => option.field === draft.sortField) ?? null,
    [draft.sortField, sortOptions]
  );
  const activeFilterCount = useMemo(() => countActiveScreenerFilters(draft), [draft]);
  const customUniverse = useMemo(() => parseTickerUniverse(draft.tickerUniverseText), [draft.tickerUniverseText]);
  const activePresetId = useMemo(() => {
    const comparableDraft = { ...draft, offset: 0 };
    return presets.find((preset) => areLocalScreenerDraftsEqual(preset.draft, comparableDraft))?.id ?? null;
  }, [draft, presets]);
  const draftDirty = useMemo(() => {
    if (!lastExecutedDraft) {
      return false;
    }
    return !areLocalScreenerDraftsEqual(lastExecutedDraft, draft);
  }, [draft, lastExecutedDraft]);
  const rangeStart = results ? Math.min(results.coverage.matched_count, results.query.offset + 1) : 0;
  const rangeEnd = results ? Math.min(results.coverage.matched_count, results.query.offset + results.query.limit) : 0;
  const canPageBackward = Boolean(results && results.query.offset > 0);
  const canPageForward = Boolean(results && results.query.offset + results.query.limit < results.coverage.matched_count);
  const provenancePayload = results ?? metadata;
  const visibleResultRows = useMemo(() => buildScreenerExportRows(results?.results ?? []), [results?.results]);
  const tableColumnCount = 3 + RANKING_COLUMNS.length + METRIC_COLUMNS.length;

  const loadMetadata = useCallback(async () => {
    try {
      setMetadataLoading(true);
      setMetadataError(null);
      const payload = await getOfficialScreenerMetadata();
      setMetadata(payload);
    } catch (error) {
      setMetadataError(error instanceof Error ? error.message : "Unable to load screener metadata.");
    } finally {
      setMetadataLoading(false);
    }
  }, []);

  const runScreen = useCallback(
    async (nextDraft: LocalScreenerDraft = draft) => {
      const nextRequestId = ++requestIdRef.current;
      try {
        setResultsLoading(true);
        setResultsError(null);
        const payload = await searchOfficialScreener(buildOfficialScreenerSearchRequest(nextDraft));
        if (requestIdRef.current !== nextRequestId) {
          return;
        }

        setResults(payload);
        setLastExecutedDraft(nextDraft);
      } catch (error) {
        if (requestIdRef.current !== nextRequestId) {
          return;
        }
        setResultsError(error instanceof Error ? error.message : "Unable to run screener search.");
      } finally {
        if (requestIdRef.current === nextRequestId) {
          setResultsLoading(false);
        }
      }
    },
    [draft]
  );

  useEffect(() => {
    void loadMetadata();
  }, [loadMetadata]);

    const loadSecFrames = useCallback(async () => {
      try {
        setSecFramesLoading(true);
        setSecFramesError(null);
        const payload = await getSecFramesScreener();
        setSecFramesData(payload);
      } catch (error) {
        setSecFramesError(error instanceof Error ? error.message : "Unable to load SEC frames data.");
      } finally {
        setSecFramesLoading(false);
      }
    }, []);

    useEffect(() => {
      if (useOfficialOnly) {
        void loadSecFrames();
      }
    }, [useOfficialOnly, loadSecFrames]);

  useEffect(() => {
    if (!hydrated || !metadata || initialSearchStarted) {
      return;
    }

    setInitialSearchStarted(true);
    void runScreen(draft);
  }, [draft, hydrated, initialSearchStarted, metadata, runScreen]);

  const setNumericFilter = useCallback(
    (field: NumericFilterField, value: string) => {
      updateDraft((current) => ({
        ...current,
        offset: 0,
        filters: {
          ...current.filters,
          [field]: value,
        },
      }));
    },
    [updateDraft]
  );

  const toggleBooleanFilter = useCallback(
    (field: "exclude_restatements" | "exclude_stale_periods") => {
      updateDraft((current) => ({
        ...current,
        offset: 0,
        filters: {
          ...current.filters,
          [field]: !current.filters[field],
        },
      }));
    },
    [updateDraft]
  );

  const toggleQualityFlag = useCallback(
    (flag: string) => {
      updateDraft((current) => {
        const nextFlags = current.filters.excluded_quality_flags.includes(flag)
          ? current.filters.excluded_quality_flags.filter((value) => value !== flag)
          : [...current.filters.excluded_quality_flags, flag];

        return {
          ...current,
          offset: 0,
          filters: {
            ...current.filters,
            excluded_quality_flags: nextFlags,
          },
        };
      });
    },
    [updateDraft]
  );

  const handleSubmit = useCallback(
    async (event?: React.FormEvent<HTMLFormElement>) => {
      event?.preventDefault();
      await runScreen({
        ...draft,
        offset: 0,
      });
    },
    [draft, runScreen]
  );

  const handleSavePreset = useCallback(() => {
    try {
      savePreset(presetName);
      setPresetName("");
      showAppToast({ message: `Saved screener preset: ${presetName.trim()}`, tone: "info" });
    } catch (error) {
      showAppToast({
        message: error instanceof Error ? error.message : "Unable to save screener preset.",
        tone: "danger",
      });
    }
  }, [presetName, savePreset]);

  const handleApplyPreset = useCallback(
    async (presetId: string) => {
      const preset = presets.find((item) => item.id === presetId) ?? null;
      const nextDraft = applyPreset(presetId);
      if (!nextDraft) {
        return;
      }

      if (preset) {
        setPresetName(preset.name);
      }
      await runScreen(nextDraft);
    },
    [applyPreset, presets, runScreen]
  );

  const handleReset = useCallback(async () => {
    resetDraft();
    setPresetName("");
    await runScreen(DEFAULT_LOCAL_SCREENER_DRAFT);
  }, [resetDraft, runScreen]);

  const handlePageChange = useCallback(
    async (direction: "previous" | "next") => {
      if (!results) {
        return;
      }

      const nextOffset = direction === "previous"
        ? Math.max(0, results.query.offset - results.query.limit)
        : results.query.offset + results.query.limit;

      const nextDraft = {
        ...draft,
        offset: nextOffset,
      };
      updateDraft(nextDraft);
      await runScreen(nextDraft);
    },
    [draft, results, runScreen, updateDraft]
  );

  const handleTableSort = useCallback(
    async (field: ScreenerSortField) => {
      const nextDirection: LocalScreenerDraft["sortDirection"] =
        draft.sortField === field && draft.sortDirection === "desc" ? "asc" : "desc";
      const nextDraft = {
        ...draft,
        sortField: field,
        sortDirection: nextDirection,
        offset: 0,
      };

      updateDraft(nextDraft);
      await runScreen(nextDraft);
    },
    [draft, runScreen, updateDraft]
  );

  const toggleRowExpanded = useCallback((rowKey: string) => {
    setExpandedRows((current) => ({
      ...current,
      [rowKey]: !current[rowKey],
    }));
  }, []);

  const qualityFlagOptions = filterMap.get("excluded_quality_flags")?.suggested_values ?? [];

  return (
    <div className="screener-page-grid">
      <Panel
        title="Official Screener"
        subtitle="Dense official-source-only discovery surface. Filters, ranking sort, current draft, and saved presets stay in this browser first."
        variant="subtle"
      >
        <div className="screener-intro">
          <div className="screener-summary-strip">
            <div className="screener-summary-item">
              <span className="screener-summary-label">Surface</span>
              <span className="screener-summary-value">Official/public only</span>
              <span className="screener-summary-detail">No Yahoo-backed price dependency.</span>
            </div>
            <div className="screener-summary-item">
              <span className="screener-summary-label">Active filters</span>
              <span className="screener-summary-value">{activeFilterCount}</span>
              <span className="screener-summary-detail">{customUniverse.length ? `${customUniverse.length} tickers in custom universe.` : "Full cached candidate universe."}</span>
            </div>
            <div className="screener-summary-item">
              <span className="screener-summary-label">Sort focus</span>
              <span className="screener-summary-value">{selectedSortOption?.label ?? SORT_FIELD_LABELS[draft.sortField]}</span>
              <span className="screener-summary-detail">{selectedSortOption?.note ?? "Ranking and metric sorts rerun against the backend response order."}</span>
            </div>
            <div className="screener-summary-item">
              <span className="screener-summary-label">Saved presets</span>
              <span className="screener-summary-value">{presetCount}</span>
              <span className="screener-summary-detail">Current draft auto-saves in browser-local storage.</span>
            </div>
          </div>

          <form className="screener-controls" onSubmit={handleSubmit}>
            <div className="screener-control-row">
              <label className="screener-field">
                <span className="screener-field-label">Period</span>
                <select
                  className="screener-field-select"
                  value={draft.periodType}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      periodType: event.target.value as LocalScreenerDraft["periodType"],
                      offset: 0,
                    }))
                  }
                >
                  {(metadata?.period_types ?? ["quarterly", "annual", "ttm"]).map((periodType) => (
                    <option key={periodType} value={periodType}>
                      {titleCase(periodType)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="screener-field screener-field-wide">
                <span className="screener-field-label">Ticker universe</span>
                <input
                  className="screener-field-input"
                  value={draft.tickerUniverseText}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      tickerUniverseText: event.target.value.toUpperCase(),
                      offset: 0,
                    }))
                  }
                  placeholder="AAPL, MSFT, NVDA"
                />
                <span className="screener-field-help">Leave blank for the full cached universe. Separate tickers with commas or spaces.</span>
              </label>

              <label className="screener-field">
                <span className="screener-field-label">Sort</span>
                <select
                  className="screener-field-select"
                  value={draft.sortField}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      sortField: event.target.value as ScreenerSortField,
                      offset: 0,
                    }))
                  }
                >
                  {sortOptions.map((option) => (
                    <option key={option.field} value={option.field}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="screener-field">
                <span className="screener-field-label">Direction</span>
                <select
                  className="screener-field-select"
                  value={draft.sortDirection}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      sortDirection: event.target.value as LocalScreenerDraft["sortDirection"],
                      offset: 0,
                    }))
                  }
                >
                  <option value="desc">Descending</option>
                  <option value="asc">Ascending</option>
                </select>
              </label>

              <label className="screener-field">
                <span className="screener-field-label">Rows</span>
                <select
                  className="screener-field-select"
                  value={draft.limit}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      limit: Number.parseInt(event.target.value, 10),
                      offset: 0,
                    }))
                  }
                >
                  {LIMIT_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="screener-filter-grid">
              {NUMERIC_FILTERS.map((field) => (
                <NumericFilterInput
                  key={field}
                  definition={filterMap.get(field) ?? null}
                  value={draft.filters[field]}
                  onChange={(value) => setNumericFilter(field, value)}
                />
              ))}
            </div>

            <div className="screener-toggle-section">
              <div className="screener-toggle-block">
                <div className="screener-toggle-title">Quality gates</div>
                <div className="screener-toggle-row">
                  <button
                    type="button"
                    className={`ticker-button screener-toggle-pill${draft.filters.exclude_restatements ? " is-active" : ""}`}
                    onClick={() => toggleBooleanFilter("exclude_restatements")}
                    aria-pressed={draft.filters.exclude_restatements}
                  >
                    Exclude restatements
                  </button>
                  <button
                    type="button"
                    className={`ticker-button screener-toggle-pill${draft.filters.exclude_stale_periods ? " is-active" : ""}`}
                    onClick={() => toggleBooleanFilter("exclude_stale_periods")}
                    aria-pressed={draft.filters.exclude_stale_periods}
                  >
                    Exclude stale periods
                  </button>
                </div>
              </div>

              <div className="screener-toggle-block">
                <div className="screener-toggle-title">Data source</div>
                <div className="screener-toggle-row">
                  <button
                    type="button"
                    className={`ticker-button screener-toggle-pill${useOfficialOnly ? " is-active" : ""}`}
                    onClick={() => setUseOfficialOnly((prev) => !prev)}
                    aria-pressed={useOfficialOnly}
                  >
                    Official SEC metrics only
                  </button>
                </div>
              </div>

              <div className="screener-toggle-block">
                <div className="screener-toggle-title">Exclude quality flags</div>
                <div className="screener-toggle-row">
                  {qualityFlagOptions.length ? (
                    qualityFlagOptions.map((flag) => (
                      <button
                        key={flag}
                        type="button"
                        className={`ticker-button screener-toggle-pill${draft.filters.excluded_quality_flags.includes(flag) ? " is-active" : ""}`}
                        onClick={() => toggleQualityFlag(flag)}
                        aria-pressed={draft.filters.excluded_quality_flags.includes(flag)}
                      >
                        {titleCase(flag)}
                      </button>
                    ))
                  ) : (
                    <div className="screener-muted">Metadata is still loading quality-flag options.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="screener-control-actions">
              <button type="submit" className="ticker-button screener-run-button" disabled={!hydrated || metadataLoading || resultsLoading}>
                {resultsLoading ? "Running..." : "Run Screen"}
              </button>
              <button type="button" className="ticker-button" onClick={() => void handleReset()} disabled={resultsLoading}>
                Reset Draft
              </button>
              {draftDirty ? <span className="pill">Draft changed since last run</span> : null}
              {metadataError ? <span className="pill">Metadata issue</span> : null}
            </div>
          </form>

          <div className="screener-preset-section">
            <div className="screener-preset-header">
              <div>
                <div className="screener-toggle-title">Saved presets</div>
                <div className="screener-muted">Presets keep filters, sort, period, and ticker universe in local browser storage.</div>
              </div>
              <div className="screener-preset-form">
                <input
                  className="screener-field-input screener-preset-input"
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                  placeholder="Large-cap compounders"
                />
                <button type="button" className="ticker-button" onClick={handleSavePreset} disabled={!presetName.trim()}>
                  Save Preset
                </button>
              </div>
            </div>

            {presets.length ? (
              <div className="screener-preset-list">
                {presets.map((preset) => (
                  <div key={preset.id} className={`screener-preset-card${activePresetId === preset.id ? " is-active" : ""}`}>
                    <div className="screener-preset-name">{preset.name}</div>
                    <div className="screener-cell-note">Updated {formatDate(preset.updatedAt)}</div>
                    <div className="screener-preset-actions">
                      <button type="button" className="ticker-button" onClick={() => void handleApplyPreset(preset.id)}>
                        Apply
                      </button>
                      <button type="button" className="ticker-button" onClick={() => deletePreset(preset.id)}>
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="screener-muted">No presets saved yet. Save a filter stack once it matches your research workflow.</div>
            )}
          </div>

          {metadataLoading ? <div className="screener-muted">Loading screener metadata...</div> : null}
          {metadataError ? (
            <div className="screener-empty-state">
              <div className="screener-kicker">Metadata</div>
              <div className="screener-empty-title">Screener configuration is unavailable</div>
              <div className="screener-muted">{metadataError}</div>
              <div>
                <button type="button" className="ticker-button" onClick={() => void loadMetadata()}>
                  Retry Metadata
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel
        title="Results"
        subtitle="Ranking-aware table ordered by the current backend query. Click key headers to rerun the sort from the server response order."
      >
        <div className="screener-results-toolbar">
          <div className="screener-results-meta">
            {results ? (
              <>
                <span className="pill">Matched {results.coverage.matched_count}</span>
                <span className="pill">Returned {results.coverage.returned_count}</span>
                <span className="pill">Fresh {results.coverage.fresh_count}</span>
                <span className="pill">Stale {results.coverage.stale_count}</span>
                <span className="pill">Yield gaps {results.coverage.missing_shareholder_yield_count}</span>
              </>
            ) : (
              <span className="pill">Awaiting first run</span>
            )}
          </div>
          <div className="screener-results-hint">{selectedSortOption?.note ?? "Use ranking scores for fast cross-sectional discovery, then jump directly into the Research Brief for a company-level read."}</div>
          {results?.results.length ? (
            <button
              type="button"
              className="ticker-button financial-export-button"
              onClick={() => exportRowsToCsv(`official-screener-results-${draft.periodType}.csv`, visibleResultRows)}
            >
              Download CSV
            </button>
          ) : null}
        </div>

        {results?.results.length ? (
          <>
            <div className="screener-table-shell">
              <table className="screener-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <SortHeader
                        label="Company"
                        field="ticker"
                        activeField={draft.sortField}
                        activeDirection={draft.sortDirection}
                        onClick={handleTableSort}
                      />
                    </th>
                    {RANKING_COLUMNS.map((column) => (
                      <th key={column.key} scope="col">
                        <SortHeader
                          label={column.label}
                          field={column.sortField}
                          activeField={draft.sortField}
                          activeDirection={draft.sortDirection}
                          onClick={handleTableSort}
                          title={rankingMap.get(column.key)?.description ?? undefined}
                        />
                      </th>
                    ))}
                    {METRIC_COLUMNS.map((column) => (
                      <th key={column.field} scope="col">
                        <SortHeader
                          label={column.label}
                          field={column.sortField}
                          activeField={draft.sortField}
                          activeDirection={draft.sortDirection}
                          onClick={handleTableSort}
                          title={filterMap.get(getFilterFieldForMetric(column.field))?.description ?? undefined}
                        />
                      </th>
                    ))}
                    <th scope="col">Flags</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {results.results.map((result) => {
                    const rowKey = `${result.company.ticker}:${result.period_end ?? "na"}`;
                    const expanded = expandedRows[rowKey] === true;
                    return [
                      <tr key={rowKey} className={result.company.cache_state === "stale" ? "is-stale" : undefined}>
                          <td data-label="Company">
                            <div className="screener-company-cell">
                              <Link href={`/company/${encodeURIComponent(result.company.ticker)}`} className="screener-company-link">
                                <span className="screener-company-ticker">{result.company.ticker}</span>
                                <span className="screener-company-name">{result.company.name}</span>
                              </Link>
                              <div className="screener-company-meta">
                                {result.company.sector ? <span className="pill">{result.company.sector}</span> : null}
                                <span className="pill">{titleCase(result.company.cache_state)}</span>
                                <span className="pill">{result.filing_type ?? result.period_type.toUpperCase()}</span>
                              </div>
                              <div className="screener-company-period">Period end {formatDate(result.period_end)}</div>
                            </div>
                          </td>

                          {RANKING_COLUMNS.map((column) => {
                            const ranking = result.rankings[column.key];
                            return (
                              <td key={column.key} data-label={column.label}>
                                <div className="screener-score-cell">
                                  <div className={`screener-score-value${column.tone === "risk" ? " is-risk" : " is-positive"}`}>
                                    {formatScore(ranking.score)}
                                  </div>
                                  <div className="screener-cell-note">
                                    {ranking.rank ? `#${ranking.rank}` : "Unranked"}
                                    {ranking.percentile !== null ? ` · ${ranking.percentile.toFixed(0)} pct` : ""}
                                  </div>
                                </div>
                              </td>
                            );
                          })}

                          {METRIC_COLUMNS.map((column) => (
                            <td key={column.field} data-label={column.label}>
                              <div className="screener-metric-cell">
                                <div className="screener-score-value">{formatMetricField(column.field, result)}</div>
                                <div className="screener-cell-note">{metricCellNote(column.field, result)}</div>
                                <MetricConfidenceBadge metadata={buildScreenerMetricConfidence(column.field, result)} />
                              </div>
                            </td>
                          ))}

                          <td data-label="Flags" className="screener-flag-cell">
                            <div className="screener-flag-stack">
                              {buildVisibleFlags(result).map((flag) => (
                                <span key={flag} className="pill screener-flag-pill">{flag}</span>
                              ))}
                            </div>
                          </td>

                          <td data-label="Actions">
                            <div className="screener-row-actions">
                              <button
                                type="button"
                                className="ticker-button"
                                aria-expanded={expanded}
                                onClick={() => toggleRowExpanded(rowKey)}
                              >
                                {expanded ? "Hide Why Matched" : "Why Matched"}
                              </button>
                              <Link href={`/company/${encodeURIComponent(result.company.ticker)}`} className="ticker-button screener-action-link">
                                Research Brief
                              </Link>
                            </div>
                          </td>
                        </tr>,
                      expanded ? (
                        <tr className="screener-row-detail" key={`${rowKey}:detail`}>
                          <td colSpan={tableColumnCount}>
                            <ScreenerMatchDetail result={result} queryFilters={results.query.filters} provenance={results.provenance} />
                          </td>
                        </tr>
                      ) : null,
                    ];
                  })}
                </tbody>
              </table>
            </div>

            <div className="screener-pagination">
              <div className="screener-cell-note">
                Showing {rangeStart ? `${rangeStart}-${rangeEnd}` : 0} of {results.coverage.matched_count} matched companies.
              </div>
              <div className="screener-row-actions">
                <button type="button" className="ticker-button" onClick={() => void handlePageChange("previous")} disabled={!canPageBackward || resultsLoading}>
                  Previous
                </button>
                <button type="button" className="ticker-button" onClick={() => void handlePageChange("next")} disabled={!canPageForward || resultsLoading}>
                  Next
                </button>
              </div>
            </div>
          </>
        ) : resultsLoading ? (
          <div className="screener-empty-state" data-testid="results-loading-state" role="status" aria-live="polite">
            <div className="screener-kicker">Results</div>
            <div className="screener-empty-title">Loading screener results</div>
            <div className="screener-muted">Running screener query against persisted official-source datasets.</div>
          </div>
        ) : resultsError ? (
          <div className="screener-empty-state" data-testid="results-error-state" role="alert">
            <div className="screener-kicker">Results</div>
            <div className="screener-empty-title">Screener query failed</div>
            <div className="screener-muted">{resultsError}</div>
            <div>
              <button type="button" className="ticker-button" onClick={() => void runScreen(draft)}>
                Retry Query
              </button>
            </div>
          </div>
        ) : results ? (
          <div className="screener-empty-state" data-testid="results-empty-state">
            <div className="screener-kicker">Results</div>
            <div className="screener-empty-title">No companies matched the current filter stack</div>
            <div className="screener-muted">Loosen one or two thresholds, remove a quality exclusion, or broaden the custom ticker universe.</div>
            <div>
              <button type="button" className="ticker-button" onClick={() => void handleReset()}>
                Reset Draft
              </button>
            </div>
          </div>
        ) : (
          <div className="screener-empty-state" data-testid="results-idle-state">
            <div className="screener-kicker">Results</div>
            <div className="screener-empty-title">Run the screener to load ranked candidates</div>
            <div className="screener-muted">The current draft is already persisted in your browser, so you can leave and come back without losing the filter stack.</div>
          </div>
        )}
      </Panel>

      {provenancePayload ? (
        <Panel title="Source Freshness" subtitle="Persisted-source contract and freshness detail for the current screener surface." className="screener-provenance-panel" variant="subtle">
          <SourceFreshnessSummary
            provenance={provenancePayload.provenance}
            asOf={provenancePayload.as_of}
            lastRefreshedAt={provenancePayload.last_refreshed_at}
            sourceMix={provenancePayload.source_mix}
            confidenceFlags={provenancePayload.confidence_flags}
          />
        </Panel>
      ) : null}

      {useOfficialOnly ? (
        <Panel title="Official SEC Metrics" subtitle="Cross-company XBRL frames from SEC EDGAR. Values are official filings only; missing means no XBRL frame was found for that concept." className="screener-provenance-panel" variant="subtle">
          {secFramesLoading ? (
            <div className="screener-muted">Loading official SEC metrics...</div>
          ) : secFramesError ? (
            <div className="screener-muted">{secFramesError}</div>
          ) : secFramesData ? (
            <SecFramesTable data={secFramesData} />
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}

function NumericFilterInput({
  definition,
  value,
  onChange,
}: {
  definition: ScreenerFilterDefinitionPayload | null;
  value: string;
  onChange: (value: string) => void;
}) {
  const label = definition?.label ?? "Filter";
  const description = definition?.description ?? "";
  const unit = definition?.unit === "ratio" ? "Percent or ratio" : definition?.unit === "days" ? "Days" : null;

  return (
    <label className="screener-field">
      <span className="screener-field-label">{label}</span>
      <input
        className="screener-field-input"
        type="number"
        inputMode="decimal"
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={unit ?? "Value"}
        title={description}
      />
      <span className="screener-field-help">{description}</span>
    </label>
  );
}

function SortHeader({
  label,
  field,
  activeField,
  activeDirection,
  onClick,
  title,
}: {
  label: string;
  field: ScreenerSortField;
  activeField: ScreenerSortField;
  activeDirection: "asc" | "desc";
  onClick: (field: ScreenerSortField) => void;
  title?: string;
}) {
  const active = activeField === field;

  return (
    <button
      type="button"
      className={`screener-sort-header${active ? " is-active" : ""}`}
      onClick={() => void onClick(field)}
      title={title}
    >
      <span>{label}</span>
      <span>{active ? (activeDirection === "desc" ? "v" : "^") : "-"}</span>
    </button>
  );
}

function buildSortOptions(metadata: OfficialScreenerMetadataResponse | null): SortOption[] {
  const rankingOptions = (metadata?.rankings ?? []).map((definition) => ({
    field: toSortField(definition.score_key),
    label: `${definition.label} score`,
    note:
      definition.score_directionality === "higher_is_worse"
        ? `${definition.label} sorts high-to-low as higher risk first.`
        : `${definition.label} sorts high-to-low as stronger cross-sectional rank first.`,
  }));

  const fixedOptions: SortOption[] = [
    { field: "revenue_growth", label: "Revenue growth", note: "Sort by latest persisted revenue growth." },
    { field: "operating_margin", label: "Operating margin", note: "Sort by latest operating margin." },
    { field: "fcf_margin", label: "FCF margin", note: "Sort by latest free-cash-flow margin." },
    { field: "shareholder_yield", label: "Shareholder yield", note: "Sort by the official-only shareholder-yield proxy." },
    { field: "leverage_ratio", label: "Leverage", note: "Sort by debt-to-equity leverage ratio." },
    { field: "filing_lag_days", label: "Filing lag", note: "Sort by filing lag days." },
    { field: "restatement_count", label: "Restatement count", note: "Sort by persisted restatement history count." },
    { field: "ticker", label: "Ticker", note: "Sort alphabetically by ticker." },
    { field: "period_end", label: "Period end", note: "Sort by the latest persisted screened period." },
  ];

  return [...rankingOptions, ...fixedOptions];
}

function toSortField(scoreKey: ScreenerRankingScoreKey): ScreenerSortField {
  return `${scoreKey}_score` as ScreenerSortField;
}

function getFilterFieldForMetric(field: MetricColumnConfig["field"]): string {
  switch (field) {
    case "revenue_growth":
      return "revenue_growth";
    case "operating_margin":
      return "operating_margin";
    case "fcf_margin":
      return "fcf_margin";
    case "leverage_ratio":
      return "leverage_ratio";
    case "dilution":
      return "dilution";
    case "sbc_burden":
      return "sbc_burden";
    case "shareholder_yield":
      return "shareholder_yield";
    case "filing_lag_days":
      return "filing_lag_days";
  }
}

function formatMetricField(field: MetricColumnConfig["field"], result: ScreenerResultPayload): string {
  switch (field) {
    case "revenue_growth":
      return formatPercent(result.metrics.revenue_growth.value);
    case "operating_margin":
      return formatPercent(result.metrics.operating_margin.value);
    case "fcf_margin":
      return formatPercent(result.metrics.fcf_margin.value);
    case "leverage_ratio":
      return formatMultiple(result.metrics.leverage_ratio.value);
    case "dilution":
      return formatPercent(result.metrics.dilution.value);
    case "sbc_burden":
      return formatPercent(result.metrics.sbc_burden.value);
    case "shareholder_yield":
      return formatPercent(result.metrics.shareholder_yield.value);
    case "filing_lag_days":
      return formatDays(result.filing_quality.filing_lag_days.value);
  }
}

function metricCellNote(field: MetricColumnConfig["field"], result: ScreenerResultPayload): string {
  switch (field) {
    case "filing_lag_days":
      return result.filing_quality.restatement_count
        ? `${result.filing_quality.restatement_count} restatements on record`
        : "No persisted restatements";
    case "shareholder_yield":
      return result.metrics.shareholder_yield.is_proxy ? "Official proxy" : "Direct";
    case "leverage_ratio":
      return result.metrics.leverage_ratio.source_key;
    default:
      return result.metrics[field].source_key;
  }
}

function formatScore(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(1);
}

function formatMultiple(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(2)}x`;
}

function formatDays(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(0)}d`;
}

function buildVisibleFlags(result: ScreenerResultPayload): string[] {
  const flags = result.filing_quality.aggregated_quality_flags.map((flag) => titleCase(flag.replaceAll("_", " ")));
  if (!flags.length) {
    return ["Clean latest row"];
  }

  if (flags.length <= 3) {
    return flags;
  }

  return [...flags.slice(0, 2), `+${flags.length - 2} more`];
}

function buildScreenerExportRows(results: ScreenerResultPayload[]) {
  return results.map((result) => ({
    ticker: result.company.ticker,
    company_name: result.company.name,
    sector: result.company.sector ?? "--",
    cache_state: titleCase(result.company.cache_state),
    period_type: result.period_type.toUpperCase(),
    filing_type: result.filing_type ?? result.period_type.toUpperCase(),
    period_end: formatDate(result.period_end),
    quality_score: formatScore(result.rankings.quality.score),
    quality_rank: result.rankings.quality.rank ?? "Unranked",
    value_score: formatScore(result.rankings.value.score),
    value_rank: result.rankings.value.rank ?? "Unranked",
    capital_allocation_score: formatScore(result.rankings.capital_allocation.score),
    capital_allocation_rank: result.rankings.capital_allocation.rank ?? "Unranked",
    dilution_risk_score: formatScore(result.rankings.dilution_risk.score),
    dilution_risk_rank: result.rankings.dilution_risk.rank ?? "Unranked",
    filing_risk_score: formatScore(result.rankings.filing_risk.score),
    filing_risk_rank: result.rankings.filing_risk.rank ?? "Unranked",
    revenue_growth: formatMetricField("revenue_growth", result),
    operating_margin: formatMetricField("operating_margin", result),
    fcf_margin: formatMetricField("fcf_margin", result),
    leverage_ratio: formatMetricField("leverage_ratio", result),
    dilution: formatMetricField("dilution", result),
    sbc_burden: formatMetricField("sbc_burden", result),
    shareholder_yield: formatMetricField("shareholder_yield", result),
    filing_lag_days: formatMetricField("filing_lag_days", result),
    flags: buildVisibleFlags(result).join(" | "),
    research_brief_url: `/company/${encodeURIComponent(result.company.ticker)}`,
  }));
}

function buildScreenerMetricConfidence(field: MetricColumnConfig["field"], result: ScreenerResultPayload): MetricConfidenceMetadata {
  const metric = getScreenerMetricSnapshot(field, result);
  const qualityFlags = metric.quality_flags ?? [];
  const missingInputsCount = qualityFlags.filter((flag) => flag.includes("missing")).length;

  return {
    freshness: result.company.cache_state === "stale" ? "stale" : "fresh",
    source: metric.source_key,
    formulaVersion: null,
    missingInputsCount,
    proxyUsed: metric.is_proxy,
    fallbackUsed: metric.source_key.includes("fallback") || qualityFlags.some((flag) => flag.includes("fallback")),
    qualityFlags,
    lastRefreshedAt: result.last_metrics_check,
  };
}

function getScreenerMetricSnapshot(
  field: MetricColumnConfig["field"],
  result: ScreenerResultPayload
) {
  if (field === "filing_lag_days") {
    return result.filing_quality.filing_lag_days;
  }
  return result.metrics[field];
}

function SecFramesTable({ data }: { data: SecFramesScreenerResponse }) {
  const concepts = data.snapshots.map((s) => s.concept_key);
  if (!data.companies.length) {
    return (
      <div className="screener-muted">
        No company data found. Run an ingest job to populate SEC XBRL frame snapshots.
      </div>
    );
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--color-border, #ddd)" }}>Company</th>
            {data.snapshots.map((s) => (
              <th key={s.concept_key} style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--color-border, #ddd)" }}>
                {s.label}
                <div style={{ fontWeight: "normal", fontSize: "0.75em", opacity: 0.7 }}>{s.period_label}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.companies.map((company) => (
            <tr key={company.cik}>
              <td style={{ padding: "4px 8px", borderBottom: "1px solid var(--color-border, #ddd)" }}>
                {company.entity_name || company.cik}
              </td>
              {concepts.map((concept) => {
                const fact = company.facts[concept];
                return (
                  <td key={concept} style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--color-border, #ddd)", opacity: fact?.missing ? 0.4 : 1 }}>
                    {fact?.missing ? "—" : fact?.value != null ? fact.value.toLocaleString() : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function buildMatchedFiltersForDisplay(
  result: ScreenerResultPayload,
  queryFilters: ScreenerFilterInputPayload
): ScreenerMatchFilterPayload[] {
  if (result.match_explanation?.matched_filters?.length) {
    return result.match_explanation.matched_filters;
  }

  const matches: ScreenerMatchFilterPayload[] = [];
  const pushThreshold = (
    field: string,
    label: string,
    comparator: "min" | "max",
    thresholdValue: number | null,
    metricValue: number | null,
    sourceKey: string,
    unit: string | null,
    isProxy: boolean,
    qualityFlags: string[]
  ) => {
    if (thresholdValue === null) {
      return;
    }
    matches.push({
      field,
      label,
      comparator,
      source_key: sourceKey,
      unit,
      threshold_value: thresholdValue,
      metric_value: metricValue,
      passed: comparator === "max" ? metricValue !== null && metricValue <= thresholdValue : metricValue !== null && metricValue >= thresholdValue,
      is_proxy: isProxy,
      quality_flags: qualityFlags,
    });
  };

  pushThreshold(
    "revenue_growth_min",
    "Revenue growth",
    "min",
    queryFilters.revenue_growth_min,
    result.metrics.revenue_growth.value,
    result.metrics.revenue_growth.source_key,
    result.metrics.revenue_growth.unit,
    result.metrics.revenue_growth.is_proxy,
    result.metrics.revenue_growth.quality_flags
  );
  pushThreshold(
    "operating_margin_min",
    "Operating margin",
    "min",
    queryFilters.operating_margin_min,
    result.metrics.operating_margin.value,
    result.metrics.operating_margin.source_key,
    result.metrics.operating_margin.unit,
    result.metrics.operating_margin.is_proxy,
    result.metrics.operating_margin.quality_flags
  );
  pushThreshold(
    "fcf_margin_min",
    "FCF margin",
    "min",
    queryFilters.fcf_margin_min,
    result.metrics.fcf_margin.value,
    result.metrics.fcf_margin.source_key,
    result.metrics.fcf_margin.unit,
    result.metrics.fcf_margin.is_proxy,
    result.metrics.fcf_margin.quality_flags
  );
  pushThreshold(
    "leverage_ratio_max",
    "Leverage",
    "max",
    queryFilters.leverage_ratio_max,
    result.metrics.leverage_ratio.value,
    result.metrics.leverage_ratio.source_key,
    result.metrics.leverage_ratio.unit,
    result.metrics.leverage_ratio.is_proxy,
    result.metrics.leverage_ratio.quality_flags
  );
  pushThreshold(
    "dilution_max",
    "Dilution",
    "max",
    queryFilters.dilution_max,
    result.metrics.dilution.value,
    result.metrics.dilution.source_key,
    result.metrics.dilution.unit,
    result.metrics.dilution.is_proxy,
    result.metrics.dilution.quality_flags
  );
  pushThreshold(
    "sbc_burden_max",
    "SBC burden",
    "max",
    queryFilters.sbc_burden_max,
    result.metrics.sbc_burden.value,
    result.metrics.sbc_burden.source_key,
    result.metrics.sbc_burden.unit,
    result.metrics.sbc_burden.is_proxy,
    result.metrics.sbc_burden.quality_flags
  );
  pushThreshold(
    "shareholder_yield_min",
    "Shareholder yield",
    "min",
    queryFilters.shareholder_yield_min,
    result.metrics.shareholder_yield.value,
    result.metrics.shareholder_yield.source_key,
    result.metrics.shareholder_yield.unit,
    result.metrics.shareholder_yield.is_proxy,
    result.metrics.shareholder_yield.quality_flags
  );
  pushThreshold(
    "max_filing_lag_days",
    "Filing lag",
    "max",
    queryFilters.max_filing_lag_days,
    result.filing_quality.filing_lag_days.value,
    result.filing_quality.filing_lag_days.source_key,
    result.filing_quality.filing_lag_days.unit,
    result.filing_quality.filing_lag_days.is_proxy,
    result.filing_quality.filing_lag_days.quality_flags
  );

  return matches;
}

function formatMatchValue(value: number | string | string[] | null, unit: string | null): string {
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "None";
  }
  if (typeof value === "number") {
    if (unit === "ratio") {
      return formatPercent(value);
    }
    if (unit === "days") {
      return formatDays(value);
    }
    if (unit === "flag") {
      return value > 0 ? "Yes" : "No";
    }
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  return "-";
}

function ScreenerMatchDetail({
  result,
  queryFilters,
  provenance,
}: {
  result: ScreenerResultPayload;
  queryFilters: ScreenerFilterInputPayload;
  provenance: OfficialScreenerSearchResponse["provenance"];
}) {
  const matchedFilters = buildMatchedFiltersForDisplay(result, queryFilters);
  const rowProvenanceKeys = result.match_explanation?.provenance_source_keys ?? [];
  const matchingProvenanceEntries = provenance.filter((entry) => rowProvenanceKeys.includes(entry.source_id));

  return (
    <div className="screener-match-detail" data-testid={`why-matched-${result.company.ticker}`}>
      <div className="screener-match-section">
        <h4 className="screener-match-title">Matched filters</h4>
        {matchedFilters.length ? (
          <ul className="screener-match-list">
            {matchedFilters.map((filter) => (
              <li key={`${result.company.ticker}:${filter.field}`}>
                <strong>{filter.label}:</strong> {formatMatchValue(filter.metric_value, filter.unit)}
                <span className="screener-cell-note">
                  {` ${filter.comparator === "max" ? "<=" : filter.comparator === "min" ? ">=" : "matches"} ${formatMatchValue(filter.threshold_value, filter.unit)} · ${filter.source_key}`}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="screener-muted">No explicit thresholds were active for this run.</div>
        )}
      </div>

      <div className="screener-match-section">
        <h4 className="screener-match-title">Freshness</h4>
        <div className="screener-cell-note">
          Cache state: {titleCase(result.match_explanation?.freshness.cache_state ?? result.company.cache_state)} · Last metrics check {formatDate(result.match_explanation?.freshness.last_metrics_check ?? result.last_metrics_check)}
          {result.match_explanation?.freshness.last_model_check || result.last_model_check
            ? ` · Last model check ${formatDate(result.match_explanation?.freshness.last_model_check ?? result.last_model_check)}`
            : ""}
        </div>
      </div>

      <div className="screener-match-section">
        <h4 className="screener-match-title">Source and provenance</h4>
        {matchingProvenanceEntries.length ? (
          <ul className="screener-match-list">
            {matchingProvenanceEntries.map((entry) => (
              <li key={`${result.company.ticker}:${entry.source_id}`}>
                <strong>{entry.display_label}</strong>
                <span className="screener-cell-note"> {`(${entry.source_id} · ${titleCase(entry.role)})`}</span>
              </li>
            ))}
          </ul>
        ) : rowProvenanceKeys.length ? (
          <div className="screener-muted">Row-level provenance keys: {rowProvenanceKeys.join(", ")}.</div>
        ) : (
          <div className="screener-muted">Provenance details unavailable for this row.</div>
        )}
      </div>

      <div className="screener-row-actions">
        <Link href={`/company/${encodeURIComponent(result.company.ticker)}`} className="ticker-button screener-action-link">
          Open Research Brief
        </Link>
      </div>
    </div>
  );
}