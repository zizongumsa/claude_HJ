"""수익 계산과 추세 분석."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ───────────────────────── 수익 계산 ─────────────────────────
@dataclass
class FeeConfig:
    buy_commission: float   # 매수 수수료율 (예: 0.00015 = 0.015%)
    sell_commission: float  # 매도 수수료율
    sell_tax: float         # 매도 시 거래세율


@dataclass
class TradeResult:
    buy_date: pd.Timestamp
    sell_date: pd.Timestamp
    buy_price: float
    sell_price: float
    quantity: float
    buy_amount: float      # 매수 금액 (수수료 제외)
    sell_amount: float     # 매도 금액 (수수료·세금 제외)
    buy_fee: float
    sell_fee: float
    sell_tax: float
    gross_profit: float    # 비용 차감 전 손익
    net_profit: float      # 비용 차감 후 손익
    return_pct: float      # 순수익률 (총 투입금 대비, %)
    holding_days: int      # 달력 기준 보유일
    annualized_pct: float | None
    notes: list[str] = field(default_factory=list)


def _pick_buy_day(df: pd.DataFrame, date) -> pd.Timestamp:
    later = df.index[df.index >= pd.Timestamp(date)]
    if later.empty:
        raise ValueError("매수일 이후 거래일 데이터가 없습니다.")
    return later[0]


def _pick_sell_day(df: pd.DataFrame, date) -> pd.Timestamp:
    earlier = df.index[df.index <= pd.Timestamp(date)]
    if earlier.empty:
        raise ValueError("매도일 이전 거래일 데이터가 없습니다.")
    return earlier[-1]


def calc_trade(df: pd.DataFrame, buy_date, sell_date, buy_field: str, sell_field: str,
               fees: FeeConfig, quantity: float | None = None, amount: float | None = None,
               fractional: bool = False) -> TradeResult:
    """buy_date에 사서 sell_date에 팔았을 때의 손익.

    휴장일을 고르면 매수는 다음 거래일, 매도는 직전 거래일로 조정한다.
    quantity 또는 amount(투자금) 중 하나를 지정한다.
    """
    notes: list[str] = []
    bd, sd = _pick_buy_day(df, buy_date), _pick_sell_day(df, sell_date)
    if bd.date() != pd.Timestamp(buy_date).date():
        notes.append(f"매수일이 거래일이 아니어서 다음 거래일({bd:%Y-%m-%d})로 조정했습니다.")
    if sd.date() != pd.Timestamp(sell_date).date():
        notes.append(f"매도일이 거래일이 아니어서 직전 거래일({sd:%Y-%m-%d})로 조정했습니다.")
    if sd < bd or (sd == bd and not (buy_field == "Open" and sell_field == "Close")):
        raise ValueError("매도 시점이 매수 시점보다 뒤여야 합니다. (같은 날이면 시가 매수 → 종가 매도만 가능)")

    bp, sp = float(df.at[bd, buy_field]), float(df.at[sd, sell_field])

    if quantity is None:
        if not amount or amount <= 0:
            raise ValueError("수량 또는 투자금을 입력하세요.")
        # 수수료까지 포함해 투자금 안에서 살 수 있는 수량
        raw = amount / (bp * (1 + fees.buy_commission))
        quantity = raw if fractional else float(np.floor(raw))
        if quantity <= 0:
            raise ValueError(f"투자금이 1주 가격({bp:,.2f})보다 적습니다.")
    if quantity <= 0:
        raise ValueError("수량은 0보다 커야 합니다.")

    buy_amount, sell_amount = bp * quantity, sp * quantity
    buy_fee = buy_amount * fees.buy_commission
    sell_fee = sell_amount * fees.sell_commission
    tax = sell_amount * fees.sell_tax
    net = sell_amount - sell_fee - tax - (buy_amount + buy_fee)
    invested = buy_amount + buy_fee
    ret = net / invested * 100
    days = (sd - bd).days
    ann = None
    if days >= 30:
        ann = ((1 + ret / 100) ** (365 / days) - 1) * 100

    return TradeResult(bd, sd, bp, sp, quantity, buy_amount, sell_amount, buy_fee, sell_fee, tax,
                       sell_amount - buy_amount, net, ret, days, ann, notes)


def best_trade(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp, float] | None:
    """기간 내 종가 기준으로 가장 수익이 컸을 매수·매도일 (사후적 최적, 참고용)."""
    close = df["Close"]
    if len(close) < 2:
        return None
    best, lo_i, buy_i, sell_i = -np.inf, 0, 0, 0
    vals = close.to_numpy()
    for i in range(1, len(vals)):
        if vals[i - 1] < vals[lo_i]:
            lo_i = i - 1
        r = vals[i] / vals[lo_i] - 1
        if r > best:
            best, buy_i, sell_i = r, lo_i, i
    return close.index[buy_i], close.index[sell_i], best * 100


# ───────────────────────── 기술 지표 ─────────────────────────
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["Close"]
    for n in (5, 20, 60, 120):
        out[f"MA{n}"] = c.rolling(n).mean()

    # RSI(14) — Wilder 평활
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["RSI"] = (100 - 100 / (1 + rs)).where(loss != 0, 100.0)
    out.loc[gain.isna(), "RSI"] = np.nan

    # MACD(12, 26, 9)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_hist"] = out["MACD"] - out["MACD_signal"]

    # 볼린저 밴드(20, 2σ)
    std = c.rolling(20).std()
    out["BB_upper"], out["BB_lower"] = out["MA20"] + 2 * std, out["MA20"] - 2 * std
    return out


# ───────────────────────── 추세 요약 ─────────────────────────
@dataclass
class TrendSummary:
    label: str             # 강한 상승 / 상승 / 횡보 / 하락 / 강한 하락
    score: int             # -100 ~ 100
    slope_pct_per_day: float
    slope_annual_pct: float
    r2: float
    period_return_pct: float
    volatility_pct: float  # 연환산 변동성
    max_drawdown_pct: float
    rsi: float | None
    signals: list[tuple[str, str]]  # (신호 종류: "up"|"down"|"neutral", 설명)


def regression_trend(close: pd.Series) -> tuple[float, float]:
    """로그 종가의 선형회귀 → (일평균 기울기 %, R²)."""
    y = np.log(close.to_numpy(dtype=float))
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res, ss_tot = ((y - pred) ** 2).sum(), ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return (np.exp(slope) - 1) * 100, r2


def summarize_trend(ind: pd.DataFrame, period: pd.DataFrame, window: int = 20) -> TrendSummary:
    """ind: 지표가 붙은 전체 데이터, period: 사용자가 고른 분석 기간."""
    close = period["Close"]
    if len(close) < 5:
        raise ValueError("추세 분석에는 최소 5거래일 이상의 데이터가 필요합니다.")

    recent = close.iloc[-min(window, len(close)):]
    slope, r2 = regression_trend(recent)
    last = ind.loc[:close.index[-1]].iloc[-1]
    signals: list[tuple[str, str]] = []
    score = 0.0

    # 1) 회귀 기울기: 설명력(R²)으로 가중
    w = min(abs(slope) / 0.3, 1.0) * r2  # 일 0.3%면 최대
    score += 35 * w * np.sign(slope)
    direction = "up" if slope > 0 else "down"
    signals.append((direction if r2 >= 0.3 else "neutral",
                    f"최근 {len(recent)}거래일 회귀 기울기 {slope:+.2f}%/일 (R² {r2:.2f}"
                    + (", 추세 뚜렷함)" if r2 >= 0.6 else ", 추세 약함)" if r2 < 0.3 else ")")))

    # 2) 이동평균 배열
    price = last["Close"]
    mas = {n: last.get(f"MA{n}") for n in (5, 20, 60)}
    if all(pd.notna(v) for v in mas.values()):
        if price > mas[5] > mas[20] > mas[60]:
            score += 25; signals.append(("up", "정배열: 주가 > MA5 > MA20 > MA60"))
        elif price < mas[5] < mas[20] < mas[60]:
            score -= 25; signals.append(("down", "역배열: 주가 < MA5 < MA20 < MA60"))
        else:
            signals.append(("neutral", "이동평균선이 뒤섞여 있음 (방향성 혼조)"))
    if pd.notna(mas[20]):
        if price > mas[20]:
            score += 10; signals.append(("up", f"주가가 20일선 위 ({(price / mas[20] - 1) * 100:+.1f}%)"))
        else:
            score -= 10; signals.append(("down", f"주가가 20일선 아래 ({(price / mas[20] - 1) * 100:+.1f}%)"))

    # 3) 최근 골든/데드 크로스 (MA5 vs MA20, 최근 10거래일)
    seg = ind.loc[:close.index[-1]].tail(11)
    diff = (seg["MA5"] - seg["MA20"]).dropna()
    if len(diff) >= 2:
        sign = np.sign(diff)
        flips = sign[sign != sign.shift()].iloc[1:]
        if not flips.empty:
            d, s = flips.index[-1], flips.iloc[-1]
            if s > 0:
                score += 10; signals.append(("up", f"골든크로스 발생 ({d:%Y-%m-%d}, MA5↑MA20)"))
            else:
                score -= 10; signals.append(("down", f"데드크로스 발생 ({d:%Y-%m-%d}, MA5↓MA20)"))

    # 4) MACD
    if pd.notna(last.get("MACD_hist")):
        if last["MACD"] > last["MACD_signal"]:
            score += 10; signals.append(("up", "MACD가 시그널선 위 (상승 모멘텀)"))
        else:
            score -= 10; signals.append(("down", "MACD가 시그널선 아래 (하락 모멘텀)"))

    # 5) RSI — 추세 방향이 아니라 과열/침체 경고
    rsi = float(last["RSI"]) if pd.notna(last.get("RSI")) else None
    if rsi is not None:
        if rsi >= 70:
            signals.append(("down", f"RSI {rsi:.0f}: 과매수 구간 (단기 조정 가능성)"))
        elif rsi <= 30:
            signals.append(("up", f"RSI {rsi:.0f}: 과매도 구간 (기술적 반등 가능성)"))
        else:
            signals.append(("neutral", f"RSI {rsi:.0f}: 중립"))

    score = int(np.clip(round(score), -100, 100))
    label = ("강한 상승" if score >= 50 else "상승" if score >= 20 else
             "강한 하락" if score <= -50 else "하락" if score <= -20 else "횡보")

    rets = close.pct_change().dropna()
    vol = float(rets.std() * np.sqrt(TRADING_DAYS) * 100) if len(rets) > 1 else 0.0
    mdd = float((close / close.cummax() - 1).min() * 100)
    period_ret = float((close.iloc[-1] / close.iloc[0] - 1) * 100)
    annual = ((1 + slope / 100) ** TRADING_DAYS - 1) * 100

    return TrendSummary(label, score, slope, annual, r2, period_ret, vol, mdd, rsi, signals)
