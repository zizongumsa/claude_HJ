"""여러 종목 시세 수집과 매매법 적용(오늘의 추천)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from strategies import Panel, Strategy

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


@dataclass
class Selection:
    strategy: Strategy
    params: dict


def evaluate(P: Panel, sels: list[Selection]) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """매매법별 (signal, strength) 표."""
    out = {}
    for s in sels:
        r = s.strategy.compute(P, s.params)
        out[s.strategy.key] = (r.signal.astype(bool), r.strength.astype(float))
    return out


def active_mask(sig: pd.DataFrame, is_state: bool, recent: int) -> pd.DataFrame:
    """그 날짜 기준으로 '신호가 살아 있는지'. 상태형은 당일 조건, 이벤트형은 최근 N거래일 내 발생."""
    if is_state:
        return sig
    return sig.astype(float).rolling(recent, min_periods=1).max().astype(bool)


def recommend(P: Panel, sels: list[Selection], universe: pd.DataFrame, mode: str, recent: int,
              top_n: int, min_price: float = 5.0) -> pd.DataFrame:
    """가장 최근 거래일 기준 추천 목록. mode: 'and' | 'score'."""
    results = evaluate(P, sels)
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
