import { describe, expect, it } from "vitest";

import { buildCompanyChartsShareMetadata } from "@/lib/chart-share-server";
import type { CompanyChartsShareSnapshotRecordPayload } from "@/lib/types";

describe("chart share metadata", () => {
  it("builds OG metadata that points at the server image route", () => {
    const record: CompanyChartsShareSnapshotRecordPayload = {
      id: "share-1",
      ticker: "ACME",
      mode: "outlook",
      schema_version: "company_chart_share_snapshot_v1",
      share_path: "/company/ACME/charts/share/share-1",
      image_path: "/company/ACME/charts/share/share-1/image",
      created_at: "2026-04-23T00:00:00Z",
      payload: {
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
      },
    };

    const metadata = buildCompanyChartsShareMetadata(record, "https://fundamental-terminal.test");

    expect(metadata.alternates?.canonical).toBe("https://fundamental-terminal.test/company/ACME/charts/share/share-1");
    expect(metadata.openGraph?.images?.[0]).toBe("https://fundamental-terminal.test/company/ACME/charts/share/share-1/image?layout=landscape");
    expect(metadata.twitter?.images?.[0]).toBe("https://fundamental-terminal.test/company/ACME/charts/share/share-1/image?layout=landscape");
  });
});
