export type ExportCellValue = string | number | null | undefined;
export type ExportRow = Record<string, ExportCellValue>;

export function normalizeExportFileStem(value: string | null | undefined, fallback = "company"): string {
  const sanitized = (value ?? "")
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return sanitized || fallback;
}

export function csvCell(value: ExportCellValue): string {
  if (value === null || value === undefined) {
    return "";
  }

  const text = String(value);
  if (!/[",\n]/.test(text)) {
    return text;
  }

  return `"${text.replaceAll('"', '""')}"`;
}

export function buildCsv(rows: ExportRow[]): string {
  if (!rows.length) {
    return "";
  }

  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const lines = [
    keys.join(","),
    ...rows.map((row) => keys.map((key) => csvCell(row[key])).join(",")),
  ];

  return lines.join("\n");
}

export function downloadTextFile(fileName: string, payload: string, mimeType: string) {
  if (!payload || typeof document === "undefined") {
    return;
  }

  const blob = new Blob([payload], { type: mimeType });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function exportRowsToCsv(fileName: string, rows: ExportRow[]) {
  const payload = buildCsv(rows);
  if (!payload) {
    return;
  }

  downloadTextFile(fileName, payload, "text/csv;charset=utf-8");
}

export function buildPlainTextTable(headers: string[], rows: ExportCellValue[][]): string {
  const normalizedRows = rows.map((row) => headers.map((_, index) => formatPlainTextCell(row[index])));
  const widths = headers.map((header, index) => {
    const rowWidths = normalizedRows.map((row) => row[index]?.length ?? 0);
    return Math.max(header.length, ...rowWidths);
  });

  const formatRow = (cells: string[]) => cells.map((cell, index) => cell.padEnd(widths[index], " ")).join(" | ");
  const separator = widths.map((width) => "-".repeat(width)).join("-+-");

  return [
    formatRow(headers),
    separator,
    ...normalizedRows.map((row) => formatRow(row)),
  ].join("\n");
}

export async function copyTextToClipboard(text: string) {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  if (typeof document === "undefined") {
    throw new Error("Clipboard access is unavailable in this environment.");
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "true");
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  textArea.style.pointerEvents = "none";

  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();

  const copied = document.execCommand("copy");

  textArea.remove();

  if (!copied) {
    throw new Error("Unable to copy the table to the clipboard.");
  }
}

function formatPlainTextCell(value: ExportCellValue): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value).replace(/\s*\n\s*/g, " ").trim() || "-";
}