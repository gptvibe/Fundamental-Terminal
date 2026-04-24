// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChartShareActions } from "@/components/company/chart-share-actions";
import { createCompanyChartsShareSnapshot } from "@/lib/api";
import { captureElementViewportAsPngBlob } from "@/lib/export";
import type { CompanyChartsShareSnapshotPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  createCompanyChartsShareSnapshot: vi.fn(),
}));

vi.mock("@/lib/export", async () => {
  const actual = await vi.importActual<typeof import("@/lib/export")>("@/lib/export");
  return {
    ...actual,
    captureElementViewportAsPngBlob: vi.fn(),
  };
});

const snapshot: CompanyChartsShareSnapshotPayload = {
  schema_version: "company_chart_share_snapshot_v1",
  mode: "outlook",
  ticker: "ACME",
  company_name: "Acme Corp",
  title: "Growth Outlook",
  as_of: "2026-04-23",
  source_badge: "SEC Company Facts",
  provenance_badge: "SEC-derived",
  trust_label: "Forecast stability: Moderate stability",
  actual_label: "Reported",
  forecast_label: "Forecast",
  source_path: "/company/ACME/charts",
  chart_spec: {} as never,
  outlook: null,
  studio: null,
};

describe("ChartShareActions", () => {
  beforeEach(() => {
    vi.mocked(createCompanyChartsShareSnapshot).mockReset();
    vi.mocked(captureElementViewportAsPngBlob).mockReset();
    window.history.replaceState({}, "", "http://localhost:3000/company/ACME/charts");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { write: vi.fn().mockResolvedValue(undefined), writeText: vi.fn().mockResolvedValue(undefined) },
    });
    Object.defineProperty(window, "ClipboardItem", {
      configurable: true,
      value: class ClipboardItem {
        items: Record<string, Blob>;
        constructor(items: Record<string, Blob>) {
          this.items = items;
        }
      },
    });
  });

  it("creates a snapshot and copies the share link", async () => {
    vi.mocked(createCompanyChartsShareSnapshot).mockResolvedValue({
      id: "share-1",
      ticker: "ACME",
      mode: "outlook",
      schema_version: "company_chart_share_snapshot_v1",
      share_path: "/company/ACME/charts/share/share-1",
      image_path: "/company/ACME/charts/share/share-1/image",
      created_at: "2026-04-23T00:00:00Z",
      payload: snapshot,
    });

    render(<ChartShareActions ticker="ACME" snapshot={snapshot} fileStem="acme-growth-outlook" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy Link" }));

    await waitFor(() => expect(createCompanyChartsShareSnapshot).toHaveBeenCalledWith("ACME", snapshot));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("http://localhost:3000/company/ACME/charts/share/share-1"));
    expect(screen.getByText("Share link copied.")).toBeTruthy();
  });

  it("copies a live captured image when a capture target is provided", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    vi.mocked(captureElementViewportAsPngBlob).mockResolvedValue(blob);
    const captureTargetRef = { current: document.createElement("div") };

    render(<ChartShareActions ticker="ACME" snapshot={snapshot} fileStem="acme-growth-outlook" captureTargetRef={captureTargetRef} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy Image" }));

    await waitFor(() => expect(captureElementViewportAsPngBlob).toHaveBeenCalled());
    expect(createCompanyChartsShareSnapshot).not.toHaveBeenCalled();
    await waitFor(() => expect(navigator.clipboard.write).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Image copied.")).toBeTruthy();
  });
});
