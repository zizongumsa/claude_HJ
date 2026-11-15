"""여러 종목 시세 수집과 매매법 적용(오늘의 추천)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from strategies import FundamentalStrategy, Panel, Strategy

UNIVERSE_DIR = Path(__file__).resolve().parent / "universes"
UNIVERSES = {
    "S&P 500": "sp500.csv",
    "나스닥 100": "nasdaq100.csv",
}
BENCHMARK = "SPY"


def load_universe(name: str) -> pd.DataFrame:
    """종목 목록(ticker, name, sector). '둘 다'는 중복을 제거해 합친다."""
    if name == "S&P 500 + 나스닥 100":
        df = pd.concat([load_universe("S&P 500"), load_universe("나스닥 100")])
        return df.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    return pd.read_csv(UNIVERSE_DIR / UNIVERSES[name])


def parse_watchlist(text: str) -> pd.DataFrame:
    tickers = []
    for tok in text.replace("\n", ",").replace(" ", ",").split(","):
        t = tok.strip().upper().replace(".", "-")
        if t and t not in tickers:
            tickers.append(t)
    return pd.DataFrame({"ticker": tickers, "name": tickers, "sector": ""})


def download_panel(tickers: list[str], period: str = "3y") -> Panel:
    """yfinance로 일괄 다운로드. 수정주가(분할·배당 반영) 기준."""
    import yfinance as yf

    raw = yf.download(sorted(set(tickers)), period=period, interval="1d", auto_adjust=True,
                      progress=False, threads=True, group_by="column")
    if raw is None or raw.empty:
        raise RuntimeError("시세를 받지 못했습니다. 잠시 후 다시 시도하세요.")
    if not isinstance(raw.columns, pd.MultiIndex):  # 종목이 1개일 때
        raw.columns = pd.MultiIndex.from_product([raw.columns, [tickers[0]]])
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    close = raw["Close"].dropna(axis=1, how="all")
    keep = close.columns
    get = lambda f: raw[f][keep].astype(float)  # noqa: E731
    return Panel(get("Open"), get("High"), get("Low"), close.astype(float), get("Volume"))


FUND_FIELDS = [
    "trailingPE", "priceToBook", "debtToEquity", "returnOnEquity", "operatingMargins", "totalRevenue",
    "enterpriseValue", "bookValue", "sharesOutstanding", "totalDebt", "totalCash", "dividendYield",
    "payoutRatio", "fiveYearAvgDividendYield", "trailingPegRatio", "earningsGrowth", "sector", "marketCap",
]


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    return {"ticker": ticker, **{k: info.get(k) for k in FUND_FIELDS}}


def download_fundamentals(tickers: list[str], workers: int = 16) -> pd.DataFrame:
    """종목별 현재 재무 지표 (Yahoo Finance). 100종목에 수 초, 500종목에 30초 안팎."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(_fetch_info, tickers))
    return pd.DataFrame(rows).set_index("ticker")


@dataclass
class Selection:
    strategy: Strategy
    params: dict


def evaluate(P: Panel, sels: list[Selection]) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """매매법별 (signal, strength) 표."""
    out = {}
    for s in sels:
        if s.strategy.kind != "price":
            continue
        r = s.strategy.compute(P, s.params)
        out[s.strategy.key] = (r.signal.astype(bool), r.strength.astype(float))
    return out


def active_mask(sig: pd.DataFrame, is_state: bool, recent: int) -> pd.DataFrame:
    """그 날짜 기준으로 '신호가 살아 있는지'. 상태형은 당일 조건, 이벤트형은 최근 N거래일 내 발생."""
    if is_state:
        return sig
    return sig.astype(float).rolling(recent, min_periods=1).max().astype(bool)


def recommend(P: Panel, sels: list[Selection], universe: pd.DataFrame, mode: str, recent: int,
              top_n: int, min_price: float = 5.0, F: pd.DataFrame | None = None) -> pd.DataFrame:
    """가장 최근 거래일 기준 추천 목록. mode: 'and' | 'score'. F: 재무 표(재무 매매법을 고른 경우)."""
    results = evaluate(P, sels)
    for s in sels:
        if isinstance(s.strategy, FundamentalStrategy):
            if F is None:
                raise ValueError("재무 매매법에는 재무 데이터가 필요합니다.")
            ok, strength = s.strategy.screen(F, s.params)
            results[s.strategy.key] = (ok.reindex(P.tickers, fill_value=False).astype(bool),
                                       strength.reindex(P.tickers, fill_value=0.0).astype(float))
    last = P.close.index[-1]
    tail = P.close.index[-recent:]
    rows = []
    info = universe.set_index("ticker")
    for t in P.tickers:
        price = P.close[t].iloc[-1]
        if not np.isfinite(price) or price < min_price or P.close[t].iloc[-recent:].isna().any():
            continue  # 저가주·거래정지·최근 데이터 누락 제외
        hits, scores = [], []
        for s in sels:
            sig, strength = results[s.strategy.key]
            if s.strategy.kind == "fundamental":
                if sig[t]:
                    hits.append((s, last))
                    scores.append(float(strength[t]))
                else:
                    scores.append(0.0)
                continue
            col = sig[t]
            if s.strategy.is_state:
                fired = [last] if col.iloc[-1] else []
            else:
                fired = list(col.loc[tail][col.loc[tail]].index)
            if fired:
                d = fired[-1]
                hits.append((s, d))
                scores.append(float(strength.at[d, t]))
            else:
                scores.append(0.0)
        if not hits or (mode == "and" and len(hits) < len(sels)):
            continue
        score = sum(scores) / len(sels)
        prev = P.close[t].iloc[-2] if len(P.close) > 1 else price
        rows.append({
            "ticker": t,
            "name": info["name"].get(t, t) if t in info.index else t,
            "sector": info["sector"].get(t, "") if t in info.index else "",
            "price": price,
            "chg_1d": (price / prev - 1) * 100,
            "score": score,
            "n_hits": len(hits),
            "hits": hits,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["n_hits", "score"] if mode == "score" else ["score"], ascending=False)
    return df.head(top_n).reset_index(drop=True)
