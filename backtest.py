"""간이 백테스트: 과거에 같은 신호가 났을 때 N거래일 뒤 수익률을 집계한다."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scanner import Selection, active_mask, evaluate
from strategies import Panel
from strategies.base import atr


@dataclass
class BacktestResult:
    trades: pd.DataFrame       # ticker, signal_date, exit_date, ret(비용 차감 %), i/j(내부 위치)
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
    sels = [s for s in sels if s.strategy.kind == "price"]
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
                    rows.append((t, idx[i], idx[i + hold], ret * 100, i, j))
                    i += hold  # 보유 중 재진입 금지
                    continue
            i += 1
    trades = pd.DataFrame(rows, columns=["ticker", "signal_date", "exit_date", "ret", "i", "j"])

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


# ───────────────────────── 매도 규칙(목표가·손절가) 검증 ─────────────────────────
TP_GRID = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, np.inf]  # 목표: 매수가 + k × ATR
SL_GRID = [1.0, 1.5, 2.0, 3.0, 4.0, np.inf]                     # 손절: 매수가 − m × ATR
DEFAULT_RULE = (3.0, 2.0)  # 검증할 거래가 부족할 때 쓰는 일반 기준 (손익비 1.5)
MIN_TRADES = 30


@dataclass
class ExitRule:
    tp: float          # ATR 배수 (inf = 목표가 없음)
    sl: float          # ATR 배수 (inf = 손절 없음)
    source: str        # "검증" | "일반 기준"
    mean: float | None = None      # 이 규칙의 과거 평균 수익률 (%)
    win: float | None = None       # 승률 (%)
    tp_rate: float | None = None   # 목표가 도달 비율 (%)
    sl_rate: float | None = None   # 손절 비율 (%)
    hold_mean: float | None = None  # 같은 거래를 기간 끝까지 보유했을 때 평균 (%)


@dataclass
class ExitStudy:
    grid: pd.DataFrame   # index=목표 배수, columns=손절 배수, 값=평균 수익률(%)
    best: ExitRule       # 추천 매도 계획: 목표가·손절가가 모두 있는 규칙 중 최선
    default: ExitRule    # 일반 기준 (목표 3 ATR, 손절 2 ATR)
    hold_only: ExitRule  # 목표·손절 없이 기간 끝까지 보유
    n: int


def _simulate(paths: dict, tp: float, sl: float, cost: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """거래별 수익률(비용 차감, 소수)과 목표·손절 도달 여부. 같은 날 둘 다 닿으면 손절로 가정(보수적)."""
    entry, a = paths["entry"], paths["atr"]
    O, H, L, C_end = paths["O"], paths["H"], paths["L"], paths["C_end"]
    n, hold = O.shape
    tgt = entry + tp * a
    stp = entry - sl * a
    hit_tp = H >= tgt[:, None]
    hit_sl = L <= stp[:, None]
    big = hold + 1
    first_tp = np.where(hit_tp.any(1), hit_tp.argmax(1), big)
    first_sl = np.where(hit_sl.any(1), hit_sl.argmax(1), big)
    exit_px = C_end.copy()
    rows = np.arange(n)
    is_sl = (first_sl <= first_tp) & (first_sl < big)
    is_tp = (first_tp < first_sl) & (first_tp < big)
    d_sl, d_tp = first_sl[is_sl], first_tp[is_tp]
    exit_px[is_sl] = np.minimum(O[rows[is_sl], d_sl], stp[is_sl])   # 갭 하락이면 시가에 체결
    exit_px[is_tp] = np.maximum(O[rows[is_tp], d_tp], tgt[is_tp])   # 갭 상승이면 시가에 체결
    ret = exit_px * (1 - cost) / (entry * (1 + cost)) - 1
    return ret, is_tp, is_sl


def study_exits(P: Panel, bt: BacktestResult) -> ExitStudy:
    """과거 신호 거래들에 목표가·손절가 조합을 적용해 평균 수익률이 가장 좋은 규칙을 찾는다."""
    hold, cost = bt.hold, bt.cost_pct / 100
    tr = bt.trades
    default = ExitRule(*DEFAULT_RULE, source="일반 기준")
    hold_rule = ExitRule(np.inf, np.inf, source="보유만")
    if len(tr) < MIN_TRADES:
        return ExitStudy(pd.DataFrame(), default, default, hold_rule, len(tr))

    A = atr(P).to_numpy()
    O, H, L, C = (getattr(P, f).to_numpy() for f in ("open", "high", "low", "close"))
    i, j = tr["i"].to_numpy(), tr["j"].to_numpy()
    days = i[:, None] + 1 + np.arange(hold)[None, :]          # 매수일(i+1)부터 hold거래일
    jj = np.broadcast_to(j[:, None], days.shape)
    paths = {"entry": O[i + 1, j], "atr": A[i, j], "O": O[days, jj], "H": H[days, jj], "L": L[days, jj],
             "C_end": C[i + hold, j]}
    ok = np.isfinite(paths["atr"]) & (paths["atr"] > 0) & np.isfinite(paths["H"]).all(1) & \
        np.isfinite(paths["L"]).all(1) & np.isfinite(paths["O"]).all(1)
    paths = {k: v[ok] for k, v in paths.items()}
    if ok.sum() < MIN_TRADES:
        return ExitStudy(pd.DataFrame(), default, default, hold_rule, int(ok.sum()))

    def rule(tp, sl, source):
        r, t_hit, s_hit = _simulate(paths, tp, sl, cost)
        return ExitRule(tp, sl, source, r.mean() * 100, (r > 0).mean() * 100, t_hit.mean() * 100,
                        s_hit.mean() * 100, hold_mean)

    hold_mean = _simulate(paths, np.inf, np.inf, cost)[0].mean() * 100
    grid = pd.DataFrame(index=TP_GRID, columns=SL_GRID, dtype=float)
    for tp in TP_GRID:
        for sl in SL_GRID:
            grid.loc[tp, sl] = _simulate(paths, tp, sl, cost)[0].mean() * 100
    # 우연히 튄 한 칸을 고르지 않도록 이웃 칸과 평균낸 값으로 고른다
    smooth = grid.copy()
    g = grid.to_numpy()
    for a in range(g.shape[0]):
        for b in range(g.shape[1]):
            smooth.iat[a, b] = np.nanmean(g[max(a - 1, 0):a + 2, max(b - 1, 0):b + 2])
    finite = smooth.loc[[x for x in TP_GRID if np.isfinite(x)], [x for x in SL_GRID if np.isfinite(x)]]
    tp_best, sl_best = finite.stack().idxmax()
    return ExitStudy(grid, rule(tp_best, sl_best, "검증"), rule(*DEFAULT_RULE, "일반 기준"),
                     rule(np.inf, np.inf, "보유만"), int(ok.sum()))


def exit_prices(P: Panel, t: str, rule: ExitRule) -> dict:
    """오늘 종가에 산다고 가정했을 때의 목표가·손절가와 참고 가격."""
    price = float(P.close[t].iloc[-1])
    a = float(atr(P.subset([t]))[t].iloc[-1])
    hi52 = float(P.high[t].iloc[-252:].max())
    c20 = P.close[t].iloc[-20:]
    bb_up = float(c20.mean() + 2 * c20.std())
    tgt = price + rule.tp * a if np.isfinite(rule.tp) else None
    stp = price - rule.sl * a if np.isfinite(rule.sl) else None
    return {"price": price, "atr": a, "target": tgt, "stop": stp, "hi52": hi52, "bb_up": bb_up,
            "rr": (rule.tp / rule.sl) if np.isfinite(rule.tp) and np.isfinite(rule.sl) else None}
