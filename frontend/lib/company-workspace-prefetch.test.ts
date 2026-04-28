// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import { prefetchCompanyWorkspaceTabs } from "@/lib/company-workspace-prefetch";

const getApiReadCacheState = vi.fn();
const getCompanyFinancials = vi.fn();
const getCompanyCharts = vi.fn();
const getCompanyModels = vi.fn();
const getCompanyPeers = vi.fn();
const readStoredActiveJob = vi.fn();
const withPerformanceAuditSource = vi.fn();

vi.mock("@/lib/api", () => ({
  getApiReadCacheState: (...args: unknown[]) => getApiReadCacheState(...args),
  getCompanyFinancials: (...args: unknown[]) => getCompanyFinancials(...args),
  getCompanyCharts: (...args: unknown[]) => getCompanyCharts(...args),
  getCompanyModels: (...args: unknown[]) => getCompanyModels(...args),
  getCompanyPeers: (...args: unknown[]) => getCompanyPeers(...args),
}));

vi.mock("@/lib/active-job", () => ({
  readStoredActiveJob: (...args: unknown[]) => readStoredActiveJob(...args),
}));

vi.mock("@/lib/performance-audit", () => ({
  withPerformanceAuditSource: (...args: unknown[]) => withPerformanceAuditSource(...args),
}));

describe("prefetchCompanyWorkspaceTabs", () => {
  beforeEach(() => {
    getApiReadCacheState.mockReset();
    getCompanyFinancials.mockReset();
    getCompanyCharts.mockReset();
    getCompanyModels.mockReset();
    getCompanyPeers.mockReset();
    readStoredActiveJob.mockReset();
    withPerformanceAuditSource.mockReset();

    readStoredActiveJob.mockReturnValue(null);
    getApiReadCacheState.mockResolvedValue("fresh");
    getCompanyFinancials.mockResolvedValue({});
    getCompanyCharts.mockResolvedValue({});
    getCompanyModels.mockResolvedValue({});
    getCompanyPeers.mockResolvedValue({});
    withPerformanceAuditSource.mockImplementation(async (_context: unknown, work: () => Promise<unknown>) => work());

    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: true,
    });
  });

  it("skips requests when all tab caches are fresh", async () => {
    await prefetchCompanyWorkspaceTabs("AAPL", { trigger: "idle" });

    expect(getApiReadCacheState).toHaveBeenCalledTimes(4);
    expect(getCompanyFinancials).not.toHaveBeenCalled();
    expect(getCompanyCharts).not.toHaveBeenCalled();
    expect(getCompanyModels).not.toHaveBeenCalled();
    expect(getCompanyPeers).not.toHaveBeenCalled();
  });

  it("prefetches only stale or missing tab payloads", async () => {
    getApiReadCacheState
      .mockResolvedValueOnce("stale")
      .mockResolvedValueOnce("fresh")
      .mockResolvedValueOnce("missing")
      .mockResolvedValueOnce("fresh");

    await prefetchCompanyWorkspaceTabs("AAPL", {
      trigger: "hover",
      pageRoute: "/company/[ticker]",
      scenario: "company_workspace_nav_prefetch",
    });

    expect(getCompanyFinancials).toHaveBeenCalledTimes(1);
    expect(getCompanyCharts).not.toHaveBeenCalled();
    expect(getCompanyModels).toHaveBeenCalledTimes(1);
    expect(getCompanyPeers).not.toHaveBeenCalled();

    expect(withPerformanceAuditSource).toHaveBeenCalledWith(
      expect.objectContaining({ source: "prefetch:hover:financials" }),
      expect.any(Function)
    );
    expect(withPerformanceAuditSource).toHaveBeenCalledWith(
      expect.objectContaining({ source: "prefetch:hover:models" }),
      expect.any(Function)
    );
  });

  it("skips prefetch while offline", async () => {
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: false,
    });

    await prefetchCompanyWorkspaceTabs("AAPL", { trigger: "focus" });

    expect(getApiReadCacheState).not.toHaveBeenCalled();
    expect(getCompanyFinancials).not.toHaveBeenCalled();
    expect(getCompanyCharts).not.toHaveBeenCalled();
    expect(getCompanyModels).not.toHaveBeenCalled();
    expect(getCompanyPeers).not.toHaveBeenCalled();
  });
});
