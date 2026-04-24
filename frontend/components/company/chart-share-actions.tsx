"use client";

import type { RefObject } from "react";
import { useMemo, useRef, useState } from "react";

import { buildCompanyChartsShareImagePath, CHART_SHARE_LAYOUTS, type ChartShareLayout } from "@/lib/chart-share";
import { createCompanyChartsShareSnapshot } from "@/lib/api";
import { captureElementViewportAsPngBlob, copyTextToClipboard, downloadBlob } from "@/lib/export";
import type { CompanyChartsShareSnapshotPayload, CompanyChartsShareSnapshotRecordPayload } from "@/lib/types";

type ChartShareActionsProps = {
  ticker: string;
  snapshot: CompanyChartsShareSnapshotPayload;
  fileStem: string;
  className?: string;
  captureTargetRef?: RefObject<HTMLElement | null>;
};

export function ChartShareActions({ ticker, snapshot, fileStem, className, captureTargetRef }: ChartShareActionsProps) {
  const [layout, setLayout] = useState<ChartShareLayout>("landscape");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const cachedSnapshotRef = useRef<{ key: string; record: CompanyChartsShareSnapshotRecordPayload } | null>(null);
  const snapshotKey = useMemo(() => JSON.stringify(snapshot), [snapshot]);

  async function ensureSnapshotRecord(): Promise<CompanyChartsShareSnapshotRecordPayload> {
    if (cachedSnapshotRef.current?.key === snapshotKey) {
      return cachedSnapshotRef.current.record;
    }

    const record = await createCompanyChartsShareSnapshot(ticker, snapshot);
    cachedSnapshotRef.current = { key: snapshotKey, record };
    return record;
  }

  async function handleCopyLink() {
    await runShareAction("copy-link", async () => {
      const record = await ensureSnapshotRecord();
      const url = new URL(record.share_path, window.location.origin).toString();
      await copyTextToClipboard(url);
      setStatusMessage("Share link copied.");
    });
  }

  async function handleDownloadPng() {
    await runShareAction("download-png", async () => {
      const blob = await buildExportImageBlob(layout);
      downloadBlob(`${fileStem}-${layout}.png`, blob);
      setStatusMessage("PNG downloaded.");
    });
  }

  async function handleCopyImage() {
    await runShareAction("copy-image", async () => {
      const blob = await buildExportImageBlob(layout);

      if (typeof navigator !== "undefined" && navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setStatusMessage("Image copied.");
        return;
      }

      const record = await ensureSnapshotRecord();
      const fallbackUrl = new URL(record.share_path, window.location.origin).toString();
      await copyTextToClipboard(fallbackUrl);
      setStatusMessage("Image clipboard is unavailable here, so the share link was copied instead.");
    });
  }

  async function runShareAction(action: string, callback: () => Promise<void>) {
    setBusyAction(action);
    setStatusMessage(null);
    try {
      await callback();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Share action failed.");
    } finally {
      setBusyAction(null);
    }
  }

  async function buildExportImageBlob(selectedLayout: ChartShareLayout): Promise<Blob> {
    const captureTarget = captureTargetRef?.current;
    if (captureTarget) {
      const frame = CHART_SHARE_LAYOUTS[selectedLayout];
      return captureElementViewportAsPngBlob(captureTarget, {
        outputWidth: frame.width,
        outputHeight: frame.height,
      });
    }

    const record = await ensureSnapshotRecord();
    return fetchShareImageBlob(record, selectedLayout);
  }

  return (
    <div className={`chart-share-action-bar ${className ?? ""}`.trim()}>
      <label className="chart-share-layout-picker">
        <span>Layout</span>
        <select value={layout} onChange={(event) => setLayout(event.target.value as ChartShareLayout)} aria-label="Share image layout">
          {Object.entries(CHART_SHARE_LAYOUTS).map(([value, config]) => (
            <option key={value} value={value}>
              {config.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="chart-share-button" onClick={() => void handleCopyImage()} disabled={busyAction !== null}>
        Copy Image
      </button>
      <button type="button" className="chart-share-button" onClick={() => void handleDownloadPng()} disabled={busyAction !== null}>
        Download PNG
      </button>
      <button type="button" className="chart-share-button" onClick={() => void handleCopyLink()} disabled={busyAction !== null}>
        Copy Link
      </button>
      {statusMessage ? <div className="chart-share-status" role="status">{statusMessage}</div> : null}
    </div>
  );
}

async function fetchShareImageBlob(record: CompanyChartsShareSnapshotRecordPayload, layout: ChartShareLayout): Promise<Blob> {
  const imageUrl = new URL(buildCompanyChartsShareImagePath(record.share_path, layout), window.location.origin).toString();
  const response = await fetch(imageUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to render the share image right now.");
  }
  return response.blob();
}
