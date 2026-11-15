"""S&P 500 / Nasdaq-100 구성 종목 목록을 위키백과에서 받아 universes/*.csv로 저장한다.

지수 구성 종목은 분기마다 조금씩 바뀌므로 가끔 실행해 갱신한다:
    python tools/update_universes.py
"""
import io
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent.parent / "universes"
HEADERS = {"User-Agent": "Mozilla/5.0 (stock-screener universe updater)"}


def _tables(url: str) -> list[pd.DataFrame]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def _clean(tickers: pd.Series) -> pd.Series:
    return tickers.astype(str).str.strip().str.replace(".", "-", regex=False)  # BRK.B → BRK-B (yfinance 형식)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sp = _tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    sp = pd.DataFrame({"ticker": _clean(sp["Symbol"]), "name": sp["Security"], "sector": sp["GICS Sector"]})
    sp.sort_values("ticker").to_csv(OUT / "sp500.csv", index=False)

    nd = next(t for t in _tables("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies")
              if "Ticker" in t.columns and len(t) > 90)
    sector = next((c for c in nd.columns if "Industry" in str(c) or "Sector" in str(c)), None)
    nd = pd.DataFrame({"ticker": _clean(nd["Ticker"]), "name": nd["Company"],
                       "sector": nd[sector] if sector else ""})
    nd.sort_values("ticker").to_csv(OUT / "nasdaq100.csv", index=False)
    print(f"S&P 500: {len(sp)}종목, Nasdaq-100: {len(nd)}종목 저장 완료")


if __name__ == "__main__":
    main()
