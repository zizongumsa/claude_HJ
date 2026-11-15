"""재무 기반 매매법: 그레이엄 가치, 그린블라트 마법공식, 배당주, 피터 린치 PEG.

재무 데이터는 '현재 값'만 있으므로 오늘 기준 추천에만 쓰고, 과거 성과 검증에서는 제외한다.
F: 티커를 인덱스로 하는 재무 표 (scanner.FUND_FIELDS 참고).
"""
from __future__ import annotations

import pandas as pd

from .base import Param, Strategy

ALL_H = lambda v: {"단기": v, "스윙": v, "중장기": v}  # noqa: E731  재무 매매법은 기간별 기본값이 같다


class FundamentalStrategy(Strategy):
    def screen(self, F: pd.DataFrame, p: dict) -> tuple[pd.Series, pd.Series]:  # pragma: no cover
        """(조건 충족 여부, 강도 0~100) — 둘 다 티커 인덱스."""
        raise NotImplementedError

    def reason_f(self, F: pd.DataFrame, t: str, p: dict) -> str:  # pragma: no cover
        raise NotImplementedError


def _num(F: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(F.get(col, pd.Series(index=F.index, dtype=float)), errors="coerce")


class GrahamValue(FundamentalStrategy):
    def __init__(self):
        super().__init__(
            key="graham", name="그레이엄 가치투자 (저PER·저PBR)", category="재무", kind="fundamental",
            summary="이익과 순자산에 비해 주가가 싼 흑자 기업",
            description=("'가치투자의 아버지' 벤저민 그레이엄의 기준입니다. PER(주가÷주당순이익)과 PBR(주가÷주당순자산)이 "
                         "낮을수록 싸다고 보고, 그레이엄은 PER 15 이하, PER×PBR 22.5 이하를 제시했습니다. 빚이 많은 "
                         "기업은 제외합니다. 싼 데는 이유가 있는 경우(사업 쇠퇴)도 있어 장기 보유를 전제로 합니다. "
                         "요즘 미국 대형주는 대부분 비싸서 기준을 그대로 쓰면 종목이 적게 나옵니다."),
            params=[
                Param("max_pe", "PER 최대", ALL_H(15.0), 1.0, 60.0, 1.0),
                Param("max_pepb", "PER × PBR 최대", ALL_H(22.5), 5.0, 100.0, 0.5),
                Param("max_de", "부채비율 최대 (%)", ALL_H(100.0), 10.0, 500.0, 10.0, "부채 ÷ 자기자본"),
            ])

    def screen(self, F, p):
        pe, pb, de = _num(F, "trailingPE"), _num(F, "priceToBook"), _num(F, "debtToEquity")
        pepb = pe * pb
        ok = (pe > 0) & (pb > 0) & (pe <= p["max_pe"]) & (pepb <= p["max_pepb"]) & ((de <= p["max_de"]) | de.isna())
        strength = 50 + 50 * (1 - pepb / p["max_pepb"]).clip(0, 1)
        return ok.fillna(False), strength.fillna(0)

    def reason_f(self, F, t, p):
        pe, pb, de = (_num(F, c).get(t) for c in ("trailingPE", "priceToBook", "debtToEquity"))
        tail = f", 부채비율 {de:.0f}%" if pd.notna(de) else ""
        return f"PER {pe:.1f}, PBR {pb:.2f} (PER×PBR {pe * pb:.1f}){tail}"


class MagicFormula(FundamentalStrategy):
    EXCLUDED = ("Financial Services", "Utilities", "Real Estate")

    def __init__(self):
        super().__init__(
            key="magic", name="그린블라트 마법공식", category="재무", kind="fundamental",
            summary="'좋은 회사(자본수익률 높음)'를 '싼 값(이익수익률 높음)'에",
            description=("조엘 그린블라트의 『주식시장을 이기는 작은 책』 전략입니다. 이익수익률(영업이익÷기업가치)과 "
                         "자본수익률(영업이익÷투하자본) 순위를 각각 매겨 합산 순위가 높은 종목을 고릅니다. 원래 1년 "
                         "보유 후 교체하며, 금융·유틸리티·부동산은 회계 구조가 달라 제외합니다. 여기서는 영업이익을 "
                         "영업이익률×매출로, 투하자본을 부채+자기자본−현금으로 근사합니다."),
            params=[
                Param("top_pct", "상위 몇 % 추천", ALL_H(10), 1, 50, 1),
            ])

    def _parts(self, F):
        ebit = _num(F, "operatingMargins") * _num(F, "totalRevenue")
        ev = _num(F, "enterpriseValue")
        equity = _num(F, "bookValue") * _num(F, "sharesOutstanding")
        invested = _num(F, "totalDebt").fillna(0) + equity - _num(F, "totalCash").fillna(0)
        ey = (ebit / ev).where((ev > 0) & (ebit > 0))
        roc = (ebit / invested).where((invested > 0) & (ebit > 0))
        sector = F.get("sector", pd.Series(index=F.index, dtype=object)).fillna("")
        valid = ey.notna() & roc.notna() & ~sector.isin(self.EXCLUDED)
        combined = (ey.where(valid).rank(ascending=False) + roc.where(valid).rank(ascending=False))
        pct = 1 - (combined.rank(method="min") - 1) / max(valid.sum() - 1, 1)  # 1이 최고
        return ey, roc, pct.where(valid)

    def screen(self, F, p):
        _, _, pct = self._parts(F)
        ok = pct >= 1 - p["top_pct"] / 100
        return ok.fillna(False), (pct * 100).fillna(0)

    def reason_f(self, F, t, p):
        ey, roc, pct = self._parts(F)
        n = pct.notna().sum()
        rank = int(round((1 - pct[t]) * (n - 1))) + 1
        return f"이익수익률 {ey[t] * 100:.1f}%, 자본수익률 {roc[t] * 100:.0f}% (대상 {n}개 중 {rank}위)"


class DividendStock(FundamentalStrategy):
    def __init__(self):
        super().__init__(
            key="dividend", name="고배당주", category="재무", kind="fundamental",
            summary="배당수익률이 높으면서 배당을 감당할 여력이 있는 기업",
            description=("주가 대비 배당금이 큰 종목을 고릅니다. 배당수익률이 지나치게 높으면 주가가 급락한 탓이거나 "
                         "배당 삭감 위험이 있으므로, 이익 중 배당으로 나가는 비율(배당성향)이 너무 높은 종목과 적자 "
                         "기업은 제외합니다. 주가 상승보다 꾸준한 현금 수입을 원하는 장기 투자에 맞습니다."),
            params=[
                Param("min_yield", "배당수익률 최소 (%)", ALL_H(3.0), 0.5, 15.0, 0.5),
                Param("max_payout", "배당성향 최대 (%)", ALL_H(80.0), 20.0, 150.0, 5.0, "순이익 중 배당으로 지급하는 비율"),
            ])

    def screen(self, F, p):
        y, po, roe = _num(F, "dividendYield"), _num(F, "payoutRatio") * 100, _num(F, "returnOnEquity")
        ok = (y >= p["min_yield"]) & (po > 0) & (po <= p["max_payout"]) & ((roe > 0) | roe.isna())
        return ok.fillna(False), (50 + 50 * ((y - p["min_yield"]) / p["min_yield"]).clip(0, 1)).fillna(0)

    def reason_f(self, F, t, p):
        y, po = _num(F, "dividendYield").get(t), _num(F, "payoutRatio").get(t) * 100
        avg = _num(F, "fiveYearAvgDividendYield").get(t)
        tail = f", 5년 평균 {avg:.2f}%" if pd.notna(avg) else ""
        return f"배당수익률 {y:.2f}%{tail}, 배당성향 {po:.0f}%"


class LynchPEG(FundamentalStrategy):
    def __init__(self):
        super().__init__(
            key="peg", name="피터 린치 PEG (성장 대비 저평가)", category="재무", kind="fundamental",
            summary="이익 성장 속도에 비해 PER이 낮은 성장주",
            description=("피터 린치가 즐겨 쓴 PEG(PER ÷ 이익성장률)는 성장주를 성장 속도에 맞게 평가합니다. "
                         "PEG 1 이하면 성장에 비해 싸다고 봅니다. 성장률은 애널리스트 예상치를 쓰므로 예상이 "
                         "빗나가면 결과도 틀어집니다."),
            params=[
                Param("max_peg", "PEG 최대", ALL_H(1.0), 0.2, 3.0, 0.1),
                Param("min_growth", "최근 이익 성장률 최소 (%)", ALL_H(10.0), 0.0, 100.0, 5.0),
            ])

    def screen(self, F, p):
        peg, pe, g = _num(F, "trailingPegRatio"), _num(F, "trailingPE"), _num(F, "earningsGrowth") * 100
        ok = (peg > 0) & (peg <= p["max_peg"]) & (pe > 0) & (g >= p["min_growth"])
        return ok.fillna(False), (50 + 50 * (1 - peg / p["max_peg"]).clip(0, 1)).fillna(0)

    def reason_f(self, F, t, p):
        peg, pe, g = (_num(F, c).get(t) for c in ("trailingPegRatio", "trailingPE", "earningsGrowth"))
        return f"PEG {peg:.2f}, PER {pe:.1f}, 최근 이익 성장률 {g * 100:+.0f}%"


__all__ = ["FundamentalStrategy", "GrahamValue", "MagicFormula", "DividendStock", "LynchPEG"]
