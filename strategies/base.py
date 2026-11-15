"""매매법 공통 규격.

모든 매매법은 종목 전체(날짜 × 티커 표)를 한 번에 계산하는 벡터 방식으로 구현한다.
같은 계산 결과를 '오늘의 추천'과 '과거 성과 검증'에 함께 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HORIZONS = {
    # 이름: (설명, 기본 보유 거래일, 최근 신호 인정 거래일)
    "단기": ("며칠 ~ 1주 보유", 5, 2),
    "스윙": ("몇 주 보유", 20, 5),
    "중장기": ("몇 달 보유", 60, 10),
}


@dataclass
class Panel:
    """날짜 × 티커 가격 표 묶음."""
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame

    @property
    def tickers(self) -> list[str]:
        return list(self.close.columns)

    def subset(self, tickers: list[str]) -> "Panel":
        return Panel(*(getattr(self, f)[tickers] for f in ("open", "high", "low", "close", "volume")))


@dataclass
class Param:
    key: str
    label: str
    defaults: dict[str, float | int | bool]  # 투자 기간별 기본값
    min: float | None = None
    max: float | None = None
    step: float | None = None
    help: str | None = None

    def default(self, horizon: str):
        return self.defaults[horizon]


@dataclass
class Result:
    signal: pd.DataFrame    # bool: 해당 날짜에 신호 발생(이벤트형) 또는 조건 충족(상태형)
    strength: pd.DataFrame  # 0~100: 신호 강도 (순위 매기기용)


@dataclass
class Strategy:
    key: str
    name: str
    category: str      # 추세추종 / 역추세 / 수급
    summary: str       # 한 줄 요약
    description: str   # 원리와 주의점
    params: list[Param] = field(default_factory=list)
    is_state: bool = False  # True면 '조건 충족 상태'를 보는 매매법(오늘 기준으로만 판단)

    def defaults(self, horizon: str) -> dict:
        return {p.key: p.default(horizon) for p in self.params}

    def compute(self, P: Panel, p: dict) -> Result:  # pragma: no cover - 하위 클래스 구현
        raise NotImplementedError

    def reason(self, P: Panel, ticker: str, p: dict, date: pd.Timestamp) -> str:  # pragma: no cover
        raise NotImplementedError


# ───── 공통 지표 (날짜 × 티커 표 단위) ─────
def sma(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=n).mean()


def ema(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.DataFrame, n: int) -> pd.DataFrame:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return out.where(loss != 0, 100.0).where(gain.notna())


def cross_up(a: pd.DataFrame, b: pd.DataFrame | float) -> pd.DataFrame:
    """a가 b를 아래에서 위로 뚫은 날."""
    prev_a = a.shift(1)
    prev_b = b.shift(1) if isinstance(b, pd.DataFrame) else b
    return ((a > b) & (prev_a <= prev_b)).fillna(False)


def clip01(df: pd.DataFrame) -> pd.DataFrame:
    return df.clip(lower=0, upper=1)
