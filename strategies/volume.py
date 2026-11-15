"""수급 매매법: 거래량 급증."""
from __future__ import annotations

from .base import Panel, Param, Result, Strategy, clip01


class VolumeSurge(Strategy):
    def __init__(self):
        super().__init__(
            key="volume", name="거래량 급증 양봉", category="수급",
            summary="평소보다 거래량이 크게 늘면서 주가가 오른 종목",
            description=("거래량은 가격보다 먼저 움직인다는 말이 있습니다. 평소의 몇 배 거래량과 함께 오른 날은 "
                         "기관·대형 자금이 들어왔을 가능성이 있다고 봅니다. 뉴스로 인한 일회성 급등일 수도 있으니 "
                         "다른 추세 매매법과 함께 쓰는 것이 좋습니다. 거래량 배수가 클수록 점수가 높습니다."),
            params=[
                Param("ratio", "평소 대비 거래량 배수", {"단기": 3.0, "스윙": 2.5, "중장기": 2.0}, 1.2, 10.0, 0.1),
                Param("avg_n", "평소 거래량 기간 (일)", {"단기": 20, "스윙": 20, "중장기": 50}, 5, 120, 1),
            ])

    def _ratio(self, P, p):
        n = int(p["avg_n"])
        return P.volume / P.volume.rolling(n, min_periods=n).mean().shift(1)

    def compute(self, P: Panel, p: dict) -> Result:
        vr = self._ratio(P, p)
        r = float(p["ratio"])
        sig = ((vr >= r) & (P.close > P.open) & (P.close > P.close.shift(1))).fillna(False)
        return Result(sig, 50 + 50 * clip01((vr - r) / r).fillna(0))

    def reason(self, P, t, p, date):
        vr = self._ratio(P.subset([t]), p)[t].loc[date]
        chg = (P.close[t].loc[date] / P.close[t].shift(1).loc[date] - 1) * 100
        return f"거래량 평소의 {vr:.1f}배, 주가 {chg:+.1f}% 상승 ({date:%m/%d})"
