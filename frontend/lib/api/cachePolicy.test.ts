import { describe, expect, it } from "vitest";

import {
  DEFAULT_READ_POLICY,
  STABLE_SEC_POLICY,
  resolveReadPolicy,
  isReadRequest,
  shouldBypassReadCache,
} from "@/lib/api/cachePolicy";

describe("resolveReadPolicy", () => {
  it("returns STABLE_SEC_POLICY for financials", () => {
    expect(resolveReadPolicy("/companies/AAPL/financials")).toEqual(STABLE_SEC_POLICY);
    expect(resolveReadPolicy("/companies/AAPL/financials?view=core")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for overview", () => {
    expect(resolveReadPolicy("/companies/MSFT/overview")).toEqual(STABLE_SEC_POLICY);
    expect(resolveReadPolicy("/companies/MSFT/overview?as_of=2025-01-01")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for workspace-bootstrap", () => {
    expect(resolveReadPolicy("/companies/NVDA/workspace-bootstrap")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for brief", () => {
    expect(resolveReadPolicy("/companies/AAPL/brief")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for models", () => {
    expect(resolveReadPolicy("/companies/AAPL/models")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for peers", () => {
    expect(resolveReadPolicy("/companies/AAPL/peers")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns STABLE_SEC_POLICY for governance", () => {
    expect(resolveReadPolicy("/companies/AAPL/governance")).toEqual(STABLE_SEC_POLICY);
  });

  it("returns short TTL for market-context", () => {
    const policy = resolveReadPolicy("/companies/AAPL/market-context");
    expect(policy.ttlMs).toBe(20_000);
    expect(policy.staleMs).toBe(90_000);
  });

  it("returns short TTL for global market-context", () => {
    const policy = resolveReadPolicy("/market-context");
    expect(policy.ttlMs).toBe(20_000);
    expect(policy.staleMs).toBe(90_000);
  });

  it("returns 30s TTL for earnings summary", () => {
    const policy = resolveReadPolicy("/companies/AAPL/earnings/summary");
    expect(policy.ttlMs).toBe(30_000);
    expect(policy.staleMs).toBe(120_000);
  });

  it("returns long TTL for screener filters", () => {
    const policy = resolveReadPolicy("/screener/filters");
    expect(policy.ttlMs).toBe(300_000);
    expect(policy.staleMs).toBe(900_000);
  });

  it("returns long TTL for source-registry", () => {
    const policy = resolveReadPolicy("/source-registry");
    expect(policy.ttlMs).toBe(300_000);
    expect(policy.staleMs).toBe(900_000);
  });

  it("returns short TTL for jobs status", () => {
    const policy = resolveReadPolicy("/jobs/job-123/status");
    expect(policy.ttlMs).toBe(5_000);
    expect(policy.staleMs).toBe(20_000);
  });

  it("returns DEFAULT_READ_POLICY for unknown paths", () => {
    expect(resolveReadPolicy("/companies/AAPL/unknown-endpoint")).toEqual(DEFAULT_READ_POLICY);
    expect(resolveReadPolicy("/some-other-path")).toEqual(DEFAULT_READ_POLICY);
  });

  it("does not match partial path segments", () => {
    // /companies/AAPL/financials-extra should NOT match the financials policy
    const policy = resolveReadPolicy("/companies/AAPL/financials-extra");
    expect(policy).toEqual(DEFAULT_READ_POLICY);
  });
});

describe("isReadRequest", () => {
  it("returns true for undefined init", () => {
    expect(isReadRequest(undefined)).toBe(true);
  });

  it("returns true when method is absent", () => {
    expect(isReadRequest({})).toBe(true);
  });

  it("returns true for GET", () => {
    expect(isReadRequest({ method: "GET" })).toBe(true);
    expect(isReadRequest({ method: "get" })).toBe(true);
  });

  it("returns false for POST", () => {
    expect(isReadRequest({ method: "POST" })).toBe(false);
  });

  it("returns false for DELETE", () => {
    expect(isReadRequest({ method: "DELETE" })).toBe(false);
  });

  it("returns false for PATCH", () => {
    expect(isReadRequest({ method: "PATCH" })).toBe(false);
  });
});

describe("shouldBypassReadCache", () => {
  it("returns false for normal paths", () => {
    expect(shouldBypassReadCache("/companies/AAPL/financials")).toBe(false);
  });

  it("returns true for paths containing /refresh", () => {
    expect(shouldBypassReadCache("/companies/AAPL/refresh")).toBe(true);
  });

  it("returns true when refresh=true query param is present", () => {
    expect(shouldBypassReadCache("/companies/search?query=AAPL&refresh=true")).toBe(true);
  });

  it("returns false when refresh=false query param", () => {
    expect(shouldBypassReadCache("/companies/search?query=AAPL&refresh=false")).toBe(false);
  });

  it("returns false for paths with query params but no refresh=true", () => {
    expect(shouldBypassReadCache("/companies/AAPL/financials?view=core")).toBe(false);
  });

  it("returns false for refresh=true value that is not a query param value", () => {
    // The string "refresh" appears in path but it's not /refresh sub-path nor ?refresh=true
    expect(shouldBypassReadCache("/companies/AAPL/overview?q=refresh")).toBe(false);
  });
});
