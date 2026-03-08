from __future__ import annotations

from pathlib import Path


DEFAULT_SP500_TICKERS_PATH = Path(__file__).resolve().parents[1] / "data" / "sp500_tickers.txt"


def normalize_index_ticker(value: str) -> str:
    return value.strip().upper().replace(".", "-").replace("/", "-")


def load_sp500_tickers(path: str | Path | None = None) -> list[str]:
    file_path = Path(path) if path is not None else DEFAULT_SP500_TICKERS_PATH
    if not file_path.exists():
        raise FileNotFoundError(f"S&P 500 constituents file not found: {file_path}")

    tickers: list[str] = []
    seen: set[str] = set()
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        ticker = normalize_index_ticker(line)
        if not ticker or ticker in seen:
            continue

        seen.add(ticker)
        tickers.append(ticker)

    if not tickers:
        raise ValueError(f"S&P 500 constituents file is empty: {file_path}")

    return tickers
