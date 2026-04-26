export const COMMAND_PALETTE_REFRESH_EVENT = "ft:command-palette:refresh-company";
export const COMMAND_PALETTE_EXPORT_MEMO_EVENT = "ft:command-palette:export-memo";

export interface CommandPaletteTickerDetail {
  ticker: string;
}

export function emitRefreshCurrentCompany(ticker: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(
    new CustomEvent<CommandPaletteTickerDetail>(COMMAND_PALETTE_REFRESH_EVENT, {
      detail: { ticker: ticker.trim().toUpperCase() },
    })
  );
}

export function emitExportMemo(ticker: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(
    new CustomEvent<CommandPaletteTickerDetail>(COMMAND_PALETTE_EXPORT_MEMO_EVENT, {
      detail: { ticker: ticker.trim().toUpperCase() },
    })
  );
}
