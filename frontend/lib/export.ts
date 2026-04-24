export type ExportCellValue = string | number | null | undefined;
export type ExportRow = Record<string, ExportCellValue>;

interface PngExportOptions {
  fileName: string;
  pixelRatio?: number;
  backgroundColor?: string;
}

interface ElementViewportPngOptions {
  outputWidth?: number;
  outputHeight?: number;
  pixelRatio?: number;
  backgroundColor?: string;
}

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
  downloadBlob(fileName, blob);
}

export function downloadJsonFile(fileName: string, payload: unknown) {
  const jsonPayload = JSON.stringify(payload, null, 2);
  if (jsonPayload === undefined) {
    return;
  }

  downloadTextFile(fileName, jsonPayload, "application/json;charset=utf-8");
}

export function downloadBlob(fileName: string, blob: Blob) {
  if (typeof document === "undefined") {
    return;
  }

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

export async function exportElementToPng(element: HTMLElement, { fileName, pixelRatio = 2, backgroundColor = "#111214" }: PngExportOptions) {
  const svg = element.querySelector("svg");
  if (!(svg instanceof SVGSVGElement)) {
    throw new Error("No SVG chart is available to export.");
  }

  const rect = svg.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width || Number(svg.getAttribute("width")) || element.clientWidth || 960));
  const height = Math.max(1, Math.round(rect.height || Number(svg.getAttribute("height")) || element.clientHeight || 540));
  const serializedSvg = serializeSvg(svg, width, height);
  const imageUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serializedSvg)}`;
  const image = await loadImage(imageUrl);
  const canvas = document.createElement("canvas");
  canvas.width = width * pixelRatio;
  canvas.height = height * pixelRatio;

  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("PNG export is unavailable in this browser.");
  }

  context.scale(pixelRatio, pixelRatio);
  context.fillStyle = backgroundColor;
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);

  const blob = await canvasToBlob(canvas);
  downloadBlob(fileName, blob);
}

export async function captureElementViewportAsPngBlob(
  element: HTMLElement,
  {
    outputWidth,
    outputHeight,
    pixelRatio = 2,
    backgroundColor,
  }: ElementViewportPngOptions = {}
): Promise<Blob> {
  if (typeof window === "undefined" || typeof document === "undefined") {
    throw new Error("PNG export is unavailable in this environment.");
  }

  const sourceRect = resolveElementCaptureRect(element);
  const targetWidth = Math.max(1, Math.round(outputWidth ?? sourceRect.width));
  const targetHeight = Math.max(1, Math.round(outputHeight ?? sourceRect.height));
  const resolvedBackground = backgroundColor ?? resolveElementBackgroundColor(element);
  const serializedSvg = buildElementViewportSvg(element, sourceRect);
  const image = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(serializedSvg)}`);
  const canvas = document.createElement("canvas");
  canvas.width = targetWidth * pixelRatio;
  canvas.height = targetHeight * pixelRatio;

  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("PNG export is unavailable in this browser.");
  }

  context.scale(pixelRatio, pixelRatio);
  context.fillStyle = resolvedBackground;
  context.fillRect(0, 0, targetWidth, targetHeight);

  const drawScale = Math.min(targetWidth / sourceRect.width, targetHeight / sourceRect.height);
  const drawWidth = sourceRect.width * drawScale;
  const drawHeight = sourceRect.height * drawScale;
  const drawX = (targetWidth - drawWidth) / 2;
  const drawY = (targetHeight - drawHeight) / 2;

  context.drawImage(image, drawX, drawY, drawWidth, drawHeight);
  return canvasToBlob(canvas);
}

function serializeSvg(svg: SVGSVGElement, width: number, height: number): string {
  const clone = svg.cloneNode(true);
  if (!(clone instanceof SVGSVGElement)) {
    throw new Error("Unable to prepare the chart for export.");
  }

  const rootVariables = readRootCssVariables();
  const existingStyle = clone.getAttribute("style") ?? "";

  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("viewBox", svg.getAttribute("viewBox") ?? `0 0 ${width} ${height}`);
  if (rootVariables) {
    clone.setAttribute("style", `${existingStyle}${existingStyle ? "; " : ""}${rootVariables}`);
  }

  return new XMLSerializer().serializeToString(clone);
}

function readRootCssVariables(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const computed = window.getComputedStyle(document.documentElement);
  const declarations: string[] = [];

  for (let index = 0; index < computed.length; index += 1) {
    const propertyName = computed.item(index);
    if (!propertyName.startsWith("--")) {
      continue;
    }

    const propertyValue = computed.getPropertyValue(propertyName).trim();
    if (!propertyValue) {
      continue;
    }
    declarations.push(`${propertyName}: ${propertyValue}`);
  }

  return declarations.join("; ");
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("The chart image could not be rendered for PNG export."));
    image.src = src;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }
      reject(new Error("The browser did not return a PNG export payload."));
    }, "image/png");
  });
}

function formatPlainTextCell(value: ExportCellValue): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value).replace(/\s*\n\s*/g, " ").trim() || "-";
}

function buildElementViewportSvg(
  element: HTMLElement,
  rect: { width: number; height: number; offsetLeft: number; offsetTop: number }
): string {
  const clonedRoot = cloneNodeWithStyles(element);

  if (!(clonedRoot instanceof HTMLElement || clonedRoot instanceof SVGElement)) {
    throw new Error("Unable to prepare the screen capture.");
  }

  if (clonedRoot instanceof HTMLElement) {
    clonedRoot.style.margin = "0";
    clonedRoot.style.transformOrigin = "top left";
    clonedRoot.style.transform = `translate(${-rect.offsetLeft}px, ${-rect.offsetTop}px)`;
  } else {
    const existingStyle = clonedRoot.getAttribute("style") ?? "";
    clonedRoot.setAttribute(
      "style",
      `${existingStyle}${existingStyle ? "; " : ""}transform-origin: top left; transform: translate(${-rect.offsetLeft}px, ${-rect.offsetTop}px);`
    );
  }

  const wrapper = document.createElement("div");
  wrapper.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
  wrapper.style.width = `${rect.width}px`;
  wrapper.style.height = `${rect.height}px`;
  wrapper.style.overflow = "hidden";
  wrapper.style.display = "block";
  wrapper.style.boxSizing = "border-box";
  wrapper.appendChild(clonedRoot);

  const serializedContent = new XMLSerializer().serializeToString(wrapper);
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${rect.width}" height="${rect.height}" viewBox="0 0 ${rect.width} ${rect.height}">`,
    `<foreignObject x="0" y="0" width="100%" height="100%">${serializedContent}</foreignObject>`,
    "</svg>",
  ].join("");
}

function cloneNodeWithStyles(node: Node): Node {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.cloneNode(true);
  }

  if (!(node instanceof Element)) {
    return node.cloneNode(true);
  }

  const clone = node.cloneNode(false);
  if (!(clone instanceof Element)) {
    return node.cloneNode(true);
  }

  if (clone instanceof HTMLElement && node instanceof HTMLElement) {
    copyComputedStyles(node, clone);
    clone.scrollTop = node.scrollTop;
    clone.scrollLeft = node.scrollLeft;

    if (node instanceof HTMLInputElement) {
      const inputClone = clone as HTMLInputElement;
      inputClone.value = node.value;
      inputClone.checked = node.checked;
    } else if (node instanceof HTMLTextAreaElement) {
      (clone as HTMLTextAreaElement).value = node.value;
    } else if (node instanceof HTMLSelectElement) {
      (clone as HTMLSelectElement).value = node.value;
    }
  } else if (clone instanceof SVGElement && node instanceof SVGElement) {
    copyComputedStyles(node, clone);
  }

  Array.from(node.childNodes).forEach((child) => {
    clone.appendChild(cloneNodeWithStyles(child));
  });

  return clone;
}

function copyComputedStyles(source: Element, target: Element): void {
  if (typeof window === "undefined") {
    return;
  }

  const computed = window.getComputedStyle(source);
  const targetStyle = target instanceof HTMLElement || target instanceof SVGElement ? target.style : null;
  if (!targetStyle) {
    return;
  }

  for (let index = 0; index < computed.length; index += 1) {
    const propertyName = computed.item(index);
    if (!propertyName) {
      continue;
    }
    targetStyle.setProperty(propertyName, computed.getPropertyValue(propertyName), computed.getPropertyPriority(propertyName));
  }
}

function resolveElementCaptureRect(element: HTMLElement): { width: number; height: number; offsetLeft: number; offsetTop: number } {
  const rect = element.getBoundingClientRect();
  const fullWidth = Math.max(1, Math.round(rect.width || element.clientWidth || element.scrollWidth || 1));
  const fullHeight = Math.max(1, Math.round(rect.height || element.clientHeight || element.scrollHeight || 1));

  const visibleLeft = rect.left < 0 ? Math.abs(rect.left) : 0;
  const visibleTop = rect.top < 0 ? Math.abs(rect.top) : 0;
  const visibleRight = Math.min(rect.right, window.innerWidth);
  const visibleBottom = Math.min(rect.bottom, window.innerHeight);
  const visibleWidth = Math.round(visibleRight - Math.max(rect.left, 0));
  const visibleHeight = Math.round(visibleBottom - Math.max(rect.top, 0));

  if (visibleWidth > 0 && visibleHeight > 0) {
    return {
      width: visibleWidth,
      height: visibleHeight,
      offsetLeft: Math.round(visibleLeft),
      offsetTop: Math.round(visibleTop),
    };
  }

  return {
    width: fullWidth,
    height: fullHeight,
    offsetLeft: 0,
    offsetTop: 0,
  };
}

function resolveElementBackgroundColor(element: HTMLElement): string {
  if (typeof window === "undefined") {
    return "#111214";
  }

  let current: HTMLElement | null = element;
  while (current) {
    const color = window.getComputedStyle(current).backgroundColor;
    if (color && color !== "transparent" && color !== "rgba(0, 0, 0, 0)") {
      return color;
    }
    current = current.parentElement;
  }

  return "#111214";
}
