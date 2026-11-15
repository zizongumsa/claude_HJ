"""간이 백테스트: 과거에 같은 신호가 났을 때 N거래일 뒤 수익률을 집계한다."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scanner import Selection, active_mask, evaluate
from strategies import Panel


@dataclass
class BacktestResult:
    trades: pd.DataFrame       # ticker, entry_date, exit_date, ret(비용 차감 %)
    baseline_mean: float       # 아무 종목·아무 날 샀을 때 평균 (%)
    benchmark_mean: float | None  # SPY를 같은 날 샀을 때 평균 (%)
    hold: int
    cost_pct: float
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def n(self) -> int:
        return len(self.trades)

    def stats(self) -> dict:
        r = self.trades["ret"]
        if r.empty:
            return {}
        return {
            "거래 수": len(r),
            "승률": (r > 0).mean() * 100,
            "평균": r.mean(),
            "중간값": r.median(),
            "하위 10%": r.quantile(0.10),
            "상위 10%": r.quantile(0.90),
            "최악": r.min(),
            "최고": r.max(),
        }


def combined_signal(P: Panel, sels: list[Selection], mode: str, recent: int) -> pd.DataFrame:
    """추천 화면과 같은 규칙으로 '추천 조건이 새로 충족된 날'(진입일)을 만든다."""
    res = evaluate(P, sels)
    masks = [active_mask(res[s.strategy.key][0], s.strategy.is_state, recent) for s in sels]
    cond = masks[0].copy()
    for m in masks[1:]:
        cond = (cond & m) if mode == "and" else (cond | m)
    return cond & ~cond.shift(1, fill_value=False)


def run_backtest(P: Panel, sels: list[Selection], mode: str, recent: int, hold: int,
                 cost_pct: float, benchmark: pd.DataFrame | None = None, min_price: float = 5.0,
                 warmup: int = 252) -> BacktestResult:
    """신호 다음 날 시가에 사서 hold 거래일 뒤 종가에 판다. 같은 종목 보유 중 신호는 무시."""
    entries = combined_signal(P, sels, mode, recent)
    idx = P.close.index
    start_i = min(warmup, len(idx) - hold - 2)  # 지표 준비 기간 이후부터 집계
    o, c = P.open.to_numpy(), P.close.to_numpy()
    e = entries.to_numpy()
    rows = []
    cost = cost_pct / 100
    for j, t in enumerate(P.tickers):
        i = start_i
        last_entry = len(idx) - hold - 1
        while i < last_entry:
            if e[i, j]:
                buy, sell = o[i + 1, j], c[i + hold, j]
                if np.isfinite(buy) and np.isfinite(sell) and buy >= min_price:
                    ret = (sell * (1 - cost)) / (buy * (1 + cost)) - 1
                    rows.append((t, idx[i], idx[i + hold], ret * 100))
                    i += hold  # 보유 중 재진입 금지
                    continue
            i += 1
    trades = pd.DataFrame(rows, columns=["ticker", "signal_date", "exit_date", "ret"])

    # 기준선: 같은 기간 아무 날에 아무 종목을 샀을 때의 평균 (같은 비용 반영)
    fwd = (P.close.shift(-hold) * (1 - cost)) / (P.open.shift(-1) * (1 + cost)) - 1
    base = fwd.iloc[start_i:len(idx) - hold - 1]
    base = base.where(P.open.shift(-1).iloc[start_i:len(idx) - hold - 1] >= min_price)
    baseline = float(np.nanmean(base.to_numpy()) * 100)

    bench = None
    if benchmark is not None and not trades.empty:
        bo, bc = benchmark["Open"], benchmark["Close"]
        bfwd = ((bc.shift(-hold) * (1 - cost)) / (bo.shift(-1) * (1 + cost)) - 1) * 100
        vals = bfwd.reindex(trades["signal_date"]).dropna()
        bench = float(vals.mean()) if not vals.empty else None

    return BacktestResult(trades, baseline, bench, hold, cost_pct, idx[start_i], idx[len(idx) - 1])
