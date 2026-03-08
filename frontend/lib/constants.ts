export const TRENDING_TICKERS = [
  { ticker: "AAPL", name: "Apple" },
  { ticker: "MSFT", name: "Microsoft" },
  { ticker: "NVDA", name: "NVIDIA" },
  { ticker: "AMZN", name: "Amazon" },
  { ticker: "GOOGL", name: "Alphabet" },
  { ticker: "META", name: "Meta" },
  { ticker: "TSLA", name: "Tesla" },
  { ticker: "BRK.B", name: "Berkshire" }
];

export interface ModelGuideEntry {
  key: string;
  label: string;
  locationSummary: string;
}

export const MODEL_GUIDE: ModelGuideEntry[] = [
  {
    key: "dcf",
    label: "DCF",
    locationSummary: "Investment Summary, DCF Scenario Analysis, and Model Analytics"
  },
  {
    key: "dupont",
    label: "DuPont",
    locationSummary: "the summary cards at the top and Model Analytics"
  },
  {
    key: "piotroski",
    label: "Piotroski",
    locationSummary: "the summary cards, Financial Health Score, and Model Analytics"
  },
  {
    key: "altman_z",
    label: "Altman Z",
    locationSummary: "the summary cards, Financial Health Score, and Model Analytics"
  },
  {
    key: "ratios",
    label: "Ratios",
    locationSummary: "Model Analytics"
  }
];

export const MODEL_NAMES = MODEL_GUIDE.map((model) => model.key);
