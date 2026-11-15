"""추세추종 매매법: 골든크로스, 모멘텀, 터틀 돌파, 52주 신고가."""
from __future__ import annotations

import pandas as pd

from .base import Panel, Param, Result, Strategy, clip01, cross_up, sma


class GoldenCross(Strategy):
    def __init__(self):
        super().__init__(
            key="golden_cross", name="이동평균 골든크로스", category="추세추종",
            summary="단기 이동평균선이 장기 이동평균선을 아래에서 위로 돌파",
            description=("가장 널리 쓰이는 추세 전환 신호입니다. 단기 평균 가격이 장기 평균보다 높아지면 "
                         "상승 추세가 시작된 것으로 봅니다. 횡보장에서는 신호가 자주 나왔다 사라지는(속임수) "
                         "약점이 있어, 장기선도 함께 오르고 있을 때 점수를 더 줍니다."),
            params=[
                Param("fast", "단기 이동평균 (일)", {"단기": 5, "스윙": 20, "중장기": 50}, 2, 100, 1),
                Param("slow", "장기 이동평균 (일)", {"단기": 20, "스윙": 60, "중장기": 200}, 5, 300, 1),
            ])

    def compute(self, P: Panel, p: dict) -> Result:
        f, s = sma(P.close, int(p["fast"])), sma(P.close, int(p["slow"]))
        sig = cross_up(f, s)
        rising = (s > s.shift(5)).astype(float)
        above = (P.close > f).astype(float)
        return Result(sig, 50 + 30 * rising + 20 * above)

    def reason(self, P, t, p, date):
        s = sma(P.close[[t]], int(p["slow"]))[t]
        trend = "장기선도 상승 중" if s.loc[date] > s.shift(5).loc[date] else "장기선은 아직 하락·횡보"
        return f"{p['fast']}일선이 {p['slow']}일선을 상향 돌파 ({date:%m/%d}), {trend}"


class Momentum(Strategy):
    def __init__(self):
        super().__init__(
            key="momentum", name="모멘텀 (상대강도)", category="추세추종", is_state=True,
            summary="같은 시장 안에서 최근 수익률이 가장 높은 종목들",
            description=("'오른 종목이 계속 오른다'는 현상을 이용합니다. 학술적으로 가장 많이 검증된 전략 중 "
                         "하나로, 중장기는 최근 12개월 수익률에서 직전 1개월을 뺀 값(12-1 모멘텀)을 씁니다. "
                         "종목들을 서로 비교해 순위를 매기므로 비교 대상 종목이 많을수록 의미가 있습니다. "
                         "급락장 직후 반등장에서 크게 손실을 보는 경우가 있습니다."),
            params=[
                Param("lookback", "수익률 측정 기간 (거래일)", {"단기": 21, "스윙": 63, "중장기": 252}, 5, 252, 1),
                Param("skip", "최근 제외 기간 (거래일)", {"단기": 0, "스윙": 5, "중장기": 21}, 0, 63, 1,
                      "최근 며칠의 급등락은 되돌려지는 경향이 있어 계산에서 뺍니다."),
                Param("top_pct", "상위 몇 % 추천", {"단기": 10, "스윙": 15, "중장기": 20}, 1, 50, 1),
            ])

    def _metric(self, P, p):
        lb, sk = int(p["lookback"]), int(p["skip"])
        return P.close.shift(sk) / P.close.shift(lb) - 1

    def compute(self, P: Panel, p: dict) -> Result:
        m = self._metric(P, p)
        rank = m.rank(axis=1, pct=True)
        sig = (rank >= 1 - p["top_pct"] / 100) & (m > 0)
        return Result(sig.fillna(False), (rank * 100).fillna(0))

    def reason(self, P, t, p, date):
        m = self._metric(P, p)
        rank = m.rank(axis=1, pct=True)
        n = m.loc[date].notna().sum()
        pos = int(round((1 - rank.loc[date, t]) * n)) + 1
        return (f"최근 {p['lookback']}거래일 수익률 {m.loc[date, t] * 100:+.1f}% "
                f"(비교 종목 {n}개 중 {pos}위)")


class TurtleBreakout(Strategy):
    def __init__(self):
        super().__init__(
            key="breakout", name="터틀 트레이딩 (가격 돌파)", category="추세추종",
            summary="최근 N일 최고가를 종가로 돌파",
            description=("1980년대 '터틀' 트레이더들이 쓴 돈치안 채널 돌파 전략입니다. 일정 기간의 최고가를 "
                         "넘어서면 새로운 추세가 시작된 것으로 보고 따라갑니다. 돌파한 날 거래량이 많을수록 "
                         "신뢰도가 높다고 보고 점수를 더 줍니다. 돌파 실패(다시 밀림)가 잦아 손절 원칙이 중요합니다."),
            params=[
                Param("n", "돌파 기준 기간 (거래일)", {"단기": 20, "스윙": 55, "중장기": 120}, 5, 252, 1),
            ])

    def compute(self, P: Panel, p: dict) -> Result:
        n = int(p["n"])
        hh = P.high.rolling(n, min_periods=n).max().shift(1)
        sig = (P.close > hh) & (P.close.shift(1) <= hh.shift(1))
        vr = P.volume / P.volume.rolling(20, min_periods=20).mean().shift(1)
        return Result(sig.fillna(False), 50 + 50 * clip01((vr - 1) / 2))

    def reason(self, P, t, p, date):
        n = int(p["n"])
        hh = P.high[t].rolling(n).max().shift(1).loc[date]
        vr = P.volume[t].loc[date] / P.volume[t].rolling(20).mean().shift(1).loc[date]
        return f"{n}일 최고가 {hh:,.2f} 돌파 ({date:%m/%d}), 거래량 평소의 {vr:.1f}배"


class High52(Strategy):
    def __init__(self):
        super().__init__(
            key="high52", name="52주 신고가 근접", category="추세추종", is_state=True,
            summary="52주(1년) 최고가 근처에서 거래량이 늘고 있는 종목",
            description=("윌리엄 오닐(CAN SLIM) 등이 강조한 방식으로, 신고가 근처 종목은 위에 팔려는 물량(매물대)이 "
                         "적어 추가 상승 여력이 있다고 봅니다. 최근 거래량이 평소보다 많으면 매수세가 붙은 것으로 "
                         "봅니다. 최고가에 가까울수록 점수가 높습니다."),
            params=[
                Param("within", "최고가 대비 몇 % 이내", {"단기": 3, "스윙": 5, "중장기": 8}, 1, 20, 1),
                Param("vol_ratio", "최근 거래량 / 평소 거래량 최소 배수", {"단기": 1.2, "스윙": 1.1, "중장기": 1.0},
                      0.5, 3.0, 0.1, "최근 10일 평균 거래량 ÷ 최근 60일 평균 거래량"),
            ])

    def _parts(self, P):
        hi = P.high.rolling(252, min_periods=200).max()
        dist = 1 - P.close / hi
        vr = P.volume.rolling(10).mean() / P.volume.rolling(60, min_periods=60).mean()
        return dist, vr

    def compute(self, P: Panel, p: dict) -> Result:
        dist, vr = self._parts(P)
        w = p["within"] / 100
        sig = (dist <= w) & (vr >= p["vol_ratio"])
        return Result(sig.fillna(False), 50 + 50 * clip01(1 - dist / w).fillna(0))

    def reason(self, P, t, p, date):
        dist, vr = self._parts(P.subset([t]))
        return f"52주 최고가 대비 -{dist.loc[date, t] * 100:.1f}%, 최근 거래량 평소의 {vr.loc[date, t]:.2f}배"
