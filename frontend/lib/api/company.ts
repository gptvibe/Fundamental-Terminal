import type {
	CompanyActivityFeedResponse,
	CompanyActivityOverviewResponse,
	CompanyAlertsResponse,
	CompanyCapitalRaisesResponse,
	CompanyCapitalMarketsSummaryResponse,
	CompanyCommentLettersResponse,
	CompanyCompareResponse,
	CompanyEquityClaimRiskResponse,
	CompanyEventsResponse,
	CompanyMarketContextResponse,
	CompanyOverviewResponse,
	CompanyPeersResponse,
	CompanyResearchBriefResponse,
	CompanySectorContextResponse,
	CompanySearchResponse,
	CompanyWorkspaceBootstrapResponse,
	CompanyResolutionResponse,
	OfficialScreenerMetadataResponse,
	OfficialScreenerSearchRequest,
	OfficialScreenerSearchResponse,
	RefreshQueuedResponse,
	SecFramesScreenerResponse,
} from "@/lib/types";
import type { ReadCachePolicy } from "./types";
import { appendAsOf, fetchJson } from "./client";
import { invalidateApiReadCacheForTicker, shareReadCacheValue } from "./cacheStore";

export { invalidateApiReadCacheForTicker };

export function searchCompanies(
	query: string,
	options?: { refresh?: boolean; signal?: AbortSignal; cachePolicy?: ReadCachePolicy }
): Promise<CompanySearchResponse> {
	const params = new URLSearchParams({ query });
	params.set("refresh", String(options?.refresh ?? true));
	return fetchJson(`/companies/search?${params.toString()}`, { signal: options?.signal, cachePolicy: options?.cachePolicy });
}

export function resolveCompanyIdentifier(query: string): Promise<CompanyResolutionResponse> {
	return fetchJson(`/companies/resolve?query=${encodeURIComponent(query)}`);
}

export function getOfficialScreenerMetadata(): Promise<OfficialScreenerMetadataResponse> {
	return fetchJson("/screener/filters");
}

export function searchOfficialScreener(
	payload: OfficialScreenerSearchRequest
): Promise<OfficialScreenerSearchResponse> {
	return fetchJson("/screener/search", {
		method: "POST",
		body: JSON.stringify(payload),
	});
}

export function getSecFramesScreener(params?: {
	ciks?: string;
	fiscalYear?: number;
	fiscalQuarter?: number;
}): Promise<SecFramesScreenerResponse> {
	const query = new URLSearchParams();
	if (params?.ciks) query.set("ciks", params.ciks);
	if (params?.fiscalYear != null) query.set("fiscal_year", String(params.fiscalYear));
	if (params?.fiscalQuarter != null) query.set("fiscal_quarter", String(params.fiscalQuarter));
	const qs = query.toString();
	return fetchJson(`/screener/sec-frames${qs ? `?${qs}` : ""}`);
}

export function getCompanyOverview(
	ticker: string,
	options?: {
		asOf?: string | null;
		financialsView?: "full" | "core_segments" | "core";
		priceStartDate?: string | null;
		priceEndDate?: string | null;
		priceLatestN?: number;
		priceMaxPoints?: number;
		signal?: AbortSignal;
	}
): Promise<CompanyOverviewResponse> {
	const params = new URLSearchParams();
	if (options?.financialsView && options.financialsView !== "full") {
		params.set("financials_view", options.financialsView);
	}
	if (options?.priceStartDate) {
		params.set("price_start_date", options.priceStartDate);
	}
	if (options?.priceEndDate) {
		params.set("price_end_date", options.priceEndDate);
	}
	if (options?.priceLatestN != null) {
		params.set("price_latest_n", String(options.priceLatestN));
	}
	if (options?.priceMaxPoints != null) {
		params.set("price_max_points", String(options.priceMaxPoints));
	}
	appendAsOf(params, options?.asOf);
	const suffix = params.toString() ? `?${params.toString()}` : "";
	const financialsParams = new URLSearchParams();
	if (options?.financialsView && options.financialsView !== "full") {
		financialsParams.set("view", options.financialsView);
	}
	if (options?.priceStartDate) {
		financialsParams.set("price_start_date", options.priceStartDate);
	}
	if (options?.priceEndDate) {
		financialsParams.set("price_end_date", options.priceEndDate);
	}
	if (options?.priceLatestN != null) {
		financialsParams.set("price_latest_n", String(options.priceLatestN));
	}
	if (options?.priceMaxPoints != null) {
		financialsParams.set("price_max_points", String(options.priceMaxPoints));
	}
	appendAsOf(financialsParams, options?.asOf);
	const financialsSuffix = financialsParams.toString() ? `?${financialsParams.toString()}` : "";
	const normalizedTicker = encodeURIComponent(ticker);
	return fetchJson<CompanyOverviewResponse>(`/companies/${normalizedTicker}/overview${suffix}`, { signal: options?.signal }).then((payload) => {
		shareReadCacheValue(`/companies/${normalizedTicker}/financials${financialsSuffix}`, payload.financials);
		return payload;
	});
}

export function getCompanyWorkspaceBootstrap(
	ticker: string,
	options?: {
		asOf?: string | null;
		financialsView?: "full" | "core_segments" | "core";
		priceStartDate?: string | null;
		priceEndDate?: string | null;
		priceLatestN?: number;
		priceMaxPoints?: number;
		includeOverviewBrief?: boolean;
		includeInsiders?: boolean;
		includeInstitutional?: boolean;
		includeEarningsSummary?: boolean;
		signal?: AbortSignal;
	}
): Promise<CompanyWorkspaceBootstrapResponse> {
	const params = new URLSearchParams();
	if (options?.financialsView && options.financialsView !== "full") {
		params.set("financials_view", options.financialsView);
	}
	if (options?.priceStartDate) {
		params.set("price_start_date", options.priceStartDate);
	}
	if (options?.priceEndDate) {
		params.set("price_end_date", options.priceEndDate);
	}
	if (options?.priceLatestN != null) {
		params.set("price_latest_n", String(options.priceLatestN));
	}
	if (options?.priceMaxPoints != null) {
		params.set("price_max_points", String(options.priceMaxPoints));
	}
	if (options?.includeOverviewBrief) {
		params.set("include_overview_brief", "true");
	}
	if (options?.includeInsiders) {
		params.set("include_insiders", "true");
	}
	if (options?.includeInstitutional) {
		params.set("include_institutional", "true");
	}
	if (options?.includeEarningsSummary) {
		params.set("include_earnings_summary", "true");
	}
	appendAsOf(params, options?.asOf);
	const suffix = params.toString() ? `?${params.toString()}` : "";
	const normalizedTicker = encodeURIComponent(ticker);
	const financialsParams = new URLSearchParams();
	if (options?.financialsView && options.financialsView !== "full") {
		financialsParams.set("view", options.financialsView);
	}
	if (options?.priceStartDate) {
		financialsParams.set("price_start_date", options.priceStartDate);
	}
	if (options?.priceEndDate) {
		financialsParams.set("price_end_date", options.priceEndDate);
	}
	if (options?.priceLatestN != null) {
		financialsParams.set("price_latest_n", String(options.priceLatestN));
	}
	if (options?.priceMaxPoints != null) {
		financialsParams.set("price_max_points", String(options.priceMaxPoints));
	}
	appendAsOf(financialsParams, options?.asOf);
	const financialsSuffix = financialsParams.toString() ? `?${financialsParams.toString()}` : "";

	return fetchJson<CompanyWorkspaceBootstrapResponse>(`/companies/${normalizedTicker}/workspace-bootstrap${suffix}`, {
		signal: options?.signal,
	}).then((payload) => {
		shareReadCacheValue(`/companies/${normalizedTicker}/financials${financialsSuffix}`, payload.financials);
		if (payload.brief) {
			const overviewParams = new URLSearchParams();
			if (options?.financialsView && options.financialsView !== "full") {
				overviewParams.set("financials_view", options.financialsView);
			}
			appendAsOf(overviewParams, options?.asOf);
			const overviewSuffix = overviewParams.toString() ? `?${overviewParams.toString()}` : "";
			shareReadCacheValue(`/companies/${normalizedTicker}/overview${overviewSuffix}`, {
				company: payload.company,
				financials: payload.financials,
				brief: payload.brief,
			});
		}
		return payload;
	});
}

export function getCompaniesCompare(
	tickers: string[],
	options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyCompareResponse> {
	const normalized = tickers
		.map((ticker) => ticker.trim().toUpperCase())
		.filter(Boolean)
		.slice(0, 5);
	const params = new URLSearchParams({ tickers: normalized.join(",") });
	appendAsOf(params, options?.asOf);
	return fetchJson(`/companies/compare?${params.toString()}`, { signal: options?.signal });
}

export function getCompanyEquityClaimRisk(
	ticker: string,
	options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyEquityClaimRiskResponse> {
	const params = new URLSearchParams();
	appendAsOf(params, options?.asOf);
	const suffix = params.toString() ? `?${params.toString()}` : "";
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/equity-claim-risk${suffix}`, { signal: options?.signal });
}

export function getCompanyEvents(ticker: string): Promise<CompanyEventsResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/events`);
}

export function getCompanyCapitalRaises(ticker: string): Promise<CompanyCapitalRaisesResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-raises`);
}

export function getCompanyCapitalMarkets(ticker: string): Promise<CompanyCapitalRaisesResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-markets`);
}

export function getCompanyCapitalMarketsSummary(ticker: string): Promise<CompanyCapitalMarketsSummaryResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-markets/summary`);
}

export function getCompanyActivityFeed(ticker: string): Promise<CompanyActivityFeedResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/activity-feed`);
}

export function getCompanyAlerts(ticker: string): Promise<CompanyAlertsResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/alerts`);
}

export function getCompanyActivityOverview(ticker: string): Promise<CompanyActivityOverviewResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/activity-overview`);
}

export function getCompanyMarketContext(
	ticker: string,
	options?: { signal?: AbortSignal; cachePolicy?: ReadCachePolicy }
): Promise<CompanyMarketContextResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/market-context`, { signal: options?.signal, cachePolicy: options?.cachePolicy });
}

export function getCompanySectorContext(
	ticker: string,
	options?: { signal?: AbortSignal }
): Promise<CompanySectorContextResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/sector-context`, { signal: options?.signal });
}

export function getGlobalMarketContext(): Promise<CompanyMarketContextResponse> {
	return fetchJson("/market-context");
}

export function getCompanyResearchBrief(
	ticker: string,
	options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyResearchBriefResponse> {
	const params = new URLSearchParams();
	appendAsOf(params, options?.asOf);
	const suffix = params.toString() ? `?${params.toString()}` : "";
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/brief${suffix}`, { signal: options?.signal });
}

export function getCompanyPeers(
	ticker: string,
	peers?: string[],
	options?: { asOf?: string | null }
): Promise<CompanyPeersResponse> {
	const params = new URLSearchParams();
	if (peers?.length) {
		params.set("peers", peers.join(","));
	}
	appendAsOf(params, options?.asOf);
	const suffix = params.toString() ? `?${params.toString()}` : "";
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/peers${suffix}`);
}

export function getCompanyCommentLetters(ticker: string): Promise<CompanyCommentLettersResponse> {
	return fetchJson(`/companies/${encodeURIComponent(ticker)}/comment-letters`);
}

export function refreshCompany(ticker: string, force = false): Promise<RefreshQueuedResponse> {
	const suffix = force ? "?force=true" : "";
	return fetchJson<RefreshQueuedResponse>(`/companies/${encodeURIComponent(ticker)}/refresh${suffix}`, { method: "POST" }).then((response) => {
		invalidateApiReadCacheForTicker(ticker);
		void revalidateCompanyServerCacheTags(ticker);
		return response;
	});
}

async function revalidateCompanyServerCacheTags(ticker: string): Promise<void> {
	if (typeof window === "undefined") {
		return;
	}

	try {
		await fetch(`/api/cache/company/${encodeURIComponent(ticker)}`, {
			method: "POST",
			cache: "no-store",
		});
	} catch {
		// Refresh should still succeed even if frontend tag invalidation is temporarily unavailable.
	}
}