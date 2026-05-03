import type { AsyncState, MonitorChecklistItem, ResearchBriefCue, SectionLink } from "@/components/company/brief-primitives";
import type {
  CompanyActivityOverviewResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsSummaryResponse,
  CompanyGovernanceSummaryResponse,
  CompanyModelsResponse,
  CompanyPeersResponse,
  CompanyResearchBriefResponse,
  FilingTimelineItemPayload,
  RefreshState,
  ResearchBriefBuildState,
  ResearchBriefSectionStatusPayload,
  ResearchBriefSummaryCardPayload,
} from "@/lib/types";

export type { AsyncState, MonitorChecklistItem, ResearchBriefCue, SectionLink };

export type ResearchBriefAsyncState = {
  activityOverview: AsyncState<CompanyActivityOverviewResponse>;
  changes: AsyncState<CompanyChangesSinceLastFilingResponse>;
  earningsSummary: AsyncState<CompanyEarningsSummaryResponse>;
  capitalStructure: AsyncState<CompanyCapitalStructureResponse>;
  capitalMarketsSummary: AsyncState<CompanyCapitalMarketsSummaryResponse>;
  governanceSummary: AsyncState<CompanyGovernanceSummaryResponse>;
  ownershipSummary: AsyncState<CompanyBeneficialOwnershipSummaryResponse>;
  models: AsyncState<CompanyModelsResponse>;
  peers: AsyncState<CompanyPeersResponse>;
};

export type ResearchBriefDataState = ResearchBriefAsyncState & {
  brief: CompanyResearchBriefResponse | null;
  error: string | null;
  loading: boolean;
  buildState: ResearchBriefBuildState;
  buildStatus: string | null;
  availableSections: string[];
  sectionStatuses: ResearchBriefSectionStatusPayload[];
  filingTimeline: FilingTimelineItemPayload[];
  summaryCards: ResearchBriefSummaryCardPayload[];
};

export type BriefCompany = {
  ticker?: string | null;
  name?: string | null;
  last_checked?: string | null;
};

export const BRIEF_SECTIONS = [
  {
    id: "snapshot",
    title: "Snapshot",
    question: "What matters before I read further?",
  },
  {
    id: "what-changed",
    title: "What changed",
    question: "What is new since the last filing or review?",
  },
  {
    id: "business-quality",
    title: "Business quality",
    question: "Is the business getting stronger, weaker, or just noisier?",
  },
  {
    id: "capital-risk",
    title: "Capital & risk",
    question: "Is the equity claim being protected, diluted, or put at risk?",
  },
  {
    id: "valuation",
    title: "Valuation",
    question: "How does the current price compare with peers and cached model ranges?",
  },
  {
    id: "monitor",
    title: "Monitor",
    question: "What should I keep watching after I leave this page?",
  },
] as const;

export const BRIEF_SECTION_IDS = BRIEF_SECTIONS.map((section) => section.id);
export const RESEARCH_BRIEF_SECTION_STORAGE_PREFIX = "fundamental-terminal:research-brief:sections";

export const INITIAL_ASYNC_STATE: ResearchBriefAsyncState = {
  activityOverview: { data: null, error: null, loading: true },
  changes: { data: null, error: null, loading: true },
  earningsSummary: { data: null, error: null, loading: true },
  capitalStructure: { data: null, error: null, loading: true },
  capitalMarketsSummary: { data: null, error: null, loading: true },
  governanceSummary: { data: null, error: null, loading: true },
  ownershipSummary: { data: null, error: null, loading: true },
  models: { data: null, error: null, loading: true },
  peers: { data: null, error: null, loading: true },
};

export const INITIAL_RESEARCH_BRIEF_DATA_STATE: ResearchBriefDataState = {
  ...INITIAL_ASYNC_STATE,
  brief: null,
  error: null,
  loading: true,
  buildState: "building",
  buildStatus: null,
  availableSections: [],
  sectionStatuses: [],
  filingTimeline: [],
  summaryCards: [],
};
