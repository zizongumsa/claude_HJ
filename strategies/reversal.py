"""역추세·전환 매매법: RSI 과매도 반등, 볼린저밴드 반등, MACD 크로스."""
from __future__ import annotations

from .base import Panel, Param, Result, Strategy, clip01, cross_up, ema, rsi, sma


class RsiRebound(Strategy):
    def __init__(self):
        super().__init__(
            key="rsi", name="RSI 과매도 반등", category="역추세",
            summary="RSI가 과매도 기준 아래로 내려갔다가 다시 위로 올라온 종목",
            description=("RSI는 최근 상승폭과 하락폭을 비교한 지표로, 30 아래면 단기간에 과하게 팔렸다고 봅니다. "
                         "다시 기준 위로 올라오는 순간을 반등 신호로 씁니다. 하락 추세 종목은 계속 떨어질 수 있어 "
                         "기본적으로 장기 상승 추세(200일선 위) 종목만 고르는 필터를 켜 둡니다(래리 코너스 방식). "
                         "깊이 떨어졌다 올라올수록 점수가 높습니다."),
            params=[
                Param("n", "RSI 기간 (일)", {"단기": 7, "스윙": 14, "중장기": 14}, 2, 30, 1),
                Param("level", "과매도 기준", {"단기": 25, "스윙": 30, "중장기": 35}, 5, 50, 1),
                Param("trend_filter", "200일선 위 종목만", {"단기": True, "스윙": True, "중장기": True}),
            ])

    def compute(self, P: Panel, p: dict) -> Result:
        r = rsi(P.close, int(p["n"]))
        lvl = float(p["level"])
        sig = cross_up(r, lvl)
        if p["trend_filter"]:
            sig &= (P.close > sma(P.close, 200)).fillna(False)
        depth = (lvl - r.rolling(5).min()) / lvl
        return Result(sig, 50 + 50 * clip01(depth * 2).fillna(0))

    def reason(self, P, t, p, date):
        r = rsi(P.close[[t]], int(p["n"]))[t]
        low = r.rolling(5).min().loc[date]
        tail = ", 200일선 위 (장기 상승 추세)" if p["trend_filter"] else ""
        return f"RSI({p['n']})가 {low:.0f}까지 내려갔다가 {r.loc[date]:.0f}로 회복 ({date:%m/%d}){tail}"


class BollingerRebound(Strategy):
    def __init__(self):
        super().__init__(
            key="bollinger", name="볼린저밴드 하단 반등", category="역추세",
            summary="주가가 볼린저밴드 하단 밖으로 나갔다가 다시 안으로 들어온 종목",
            description=("볼린저밴드는 이동평균 ± 표준편차 2배로 그린 띠이고, 주가는 대부분 이 안에서 움직입니다. "
                         "하단 밖으로 벗어났다가 안으로 돌아오면 과도한 하락이 끝나고 평균으로 되돌아갈 가능성이 "
                         "있다고 봅니다. 강한 하락 추세에서는 밴드를 타고 계속 내려갈 수 있습니다."),
            params=[
                Param("n", "기간 (일)", {"단기": 20, "스윙": 20, "중장기": 50}, 5, 100, 1),
                Param("k", "표준편차 배수", {"단기": 2.0, "스윙": 2.0, "중장기": 2.0}, 1.0, 3.5, 0.1),
                Param("trend_filter", "200일선 위 종목만", {"단기": False, "스윙": False, "중장기": True}),
            ])

    def _bands(self, close, p):
        n, k = int(p["n"]), float(p["k"])
        mid = sma(close, n)
        sd = close.rolling(n, min_periods=n).std()
        return mid - k * sd, mid, mid + k * sd

    def compute(self, P: Panel, p: dict) -> Result:
        lo, mid, up = self._bands(P.close, p)
        sig = ((P.close.shift(1) < lo.shift(1)) & (P.close > lo)).fillna(False)
        if p["trend_filter"]:
            sig &= (P.close > sma(P.close, 200)).fillna(False)
        width = (up - lo).replace(0, float("nan"))
        depth = (lo.shift(1) - P.close.shift(1)) / width.shift(1)
        return Result(sig, 50 + 50 * clip01(depth * 5).fillna(0))

    def reason(self, P, t, p, date):
        lo, mid, _ = self._bands(P.close[[t]], p)
        c = P.close[t]
        return (f"전날 하단밴드 아래({c.shift(1).loc[date]:,.2f} < {lo[t].shift(1).loc[date]:,.2f})에서 "
                f"밴드 안으로 복귀 ({date:%m/%d}), 중심선까지 {(mid[t].loc[date] / c.loc[date] - 1) * 100:+.1f}%")


class MacdCross(Strategy):
    def __init__(self):
        super().__init__(
            key="macd", name="MACD 상향 교차", category="역추세",
            summary="MACD선이 시그널선을 아래에서 위로 교차",
            description=("MACD는 단기·장기 지수이동평균의 차이로 추세의 힘(모멘텀)을 나타냅니다. MACD가 시그널선을 "
                         "위로 뚫으면 하락 힘이 약해지고 상승 쪽으로 돌아선다고 봅니다. 0선 아래(바닥권)에서 "
                         "교차하면 이른 전환 신호로, 주가가 60일선 위에 있으면 추세 확인으로 보고 점수를 더 줍니다."),
            params=[
                Param("fast", "단기 EMA", {"단기": 12, "스윙": 12, "중장기": 24}, 2, 50, 1),
                Param("slow", "장기 EMA", {"단기": 26, "스윙": 26, "중장기": 52}, 5, 120, 1),
                Param("signal", "시그널 EMA", {"단기": 9, "스윙": 9, "중장기": 18}, 2, 40, 1),
            ])

    def _lines(self, close, p):
        m = ema(close, int(p["fast"])) - ema(close, int(p["slow"]))
        return m, ema(m, int(p["signal"]))

    def compute(self, P: Panel, p: dict) -> Result:
        m, s = self._lines(P.close, p)
        sig = cross_up(m, s)
        strength = 60 + 20 * (m < 0).astype(float) + 20 * (P.close > sma(P.close, 60)).astype(float)
        return Result(sig, strength)

    def reason(self, P, t, p, date):
        m, _ = self._lines(P.close[[t]], p)
        zone = "0선 아래(바닥권) 교차" if m[t].loc[date] < 0 else "0선 위(상승 추세 중) 교차"
        return f"MACD 상향 교차 ({date:%m/%d}), {zone}"
