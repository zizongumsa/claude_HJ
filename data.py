"""시세 데이터 로더: 한국(6자리 코드/종목명)과 미국(티커) 일봉을 공통 형식으로 반환한다."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


@dataclass
class PriceData:
    symbol: str      # 정규화된 코드/티커
    name: str        # 표시용 이름
    market: str      # "KR" | "US"
    currency: str    # "KRW" | "USD"
    df: pd.DataFrame  # index=DatetimeIndex, columns=COLUMNS


def detect_market(symbol: str) -> str:
    s = symbol.strip().upper()
    if re.fullmatch(r"\d{4}[0-9A-Z]\d", s) or s.endswith((".KS", ".KQ")):
        return "KR"
    if re.fullmatch(r"[A-Z0-9.\-^]+", s):
        return "US"
    return "KR"  # 한글 종목명 등


_krx_listing: pd.DataFrame | None = None
KR_CODE = re.compile(r"\d{4}[0-9A-Z]\d")  # 005930, 0162Z0 등


def _naver_search(query: str) -> list[tuple[str, str]]:
    import requests
    r = requests.get("https://ac.stock.naver.com/ac", params={"q": query, "target": "stock"}, timeout=5)
    r.raise_for_status()
    return [(it["code"], it["name"]) for it in r.json().get("items", [])
            if it.get("nationCode") == "KOR" and KR_CODE.fullmatch(it.get("code", ""))]


def _get_krx_listing() -> pd.DataFrame:
    global _krx_listing
    if _krx_listing is None:
        import FinanceDataReader as fdr
        _krx_listing = fdr.StockListing("KRX")[["Code", "Name"]]
    return _krx_listing


def resolve_kr_name(query: str) -> tuple[str, str]:
    """'삼성전자' 같은 종목명 또는 코드를 (코드, 이름)으로 변환한다. 네이버 검색 → KRX 목록 순으로 시도."""
    q = query.strip()
    code_q = q.upper().removesuffix(".KS").removesuffix(".KQ")
    is_code = bool(KR_CODE.fullmatch(code_q))

    try:
        items = _naver_search(code_q if is_code else q)
        if is_code:
            for c, n in items:
                if c == code_q:
                    return c, n
        elif items:
            exact = [it for it in items if it[1] == q]
            return (exact or items)[0]
    except Exception:
        pass

    try:
        listing = _get_krx_listing()
        if is_code:
            row = listing[listing["Code"] == code_q]
            return code_q, (row.iloc[0]["Name"] if not row.empty else code_q)
        exact = listing[listing["Name"] == q]
        hit = exact if not exact.empty else listing[listing["Name"].str.contains(q, regex=False)]
        if not hit.empty:
            return hit.iloc[0]["Code"], hit.iloc[0]["Name"]
    except Exception:
        if is_code:
            return code_q, code_q

    if is_code:
        return code_q, code_q
    raise ValueError(f"'{q}'에 해당하는 한국 종목을 찾지 못했습니다. 6자리 종목코드로 입력해 보세요.")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):  # yfinance 다중 컬럼
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated()].sort_index()
    return df[df["Close"] > 0]


def _fetch_fdr(symbol: str, start, end) -> pd.DataFrame:
    import FinanceDataReader as fdr
    return fdr.DataReader(symbol, start, end)


def _fetch_yf(ticker: str, start, end) -> pd.DataFrame:
    import yfinance as yf
    # end는 미포함이므로 하루 더한다. auto_adjust=False → 실제 체결가 기준
    return yf.download(ticker, start=start, end=pd.Timestamp(end) + pd.Timedelta(days=1),
                       progress=False, auto_adjust=False)


def load_prices(query: str, start, end) -> PriceData:
    market = detect_market(query)
    errors: list[str] = []

    if market == "KR":
        code, name = resolve_kr_name(query)
        attempts = [("FinanceDataReader", lambda: _fetch_fdr(code, start, end)),
                    ("yfinance(.KS)", lambda: _fetch_yf(code + ".KS", start, end)),
                    ("yfinance(.KQ)", lambda: _fetch_yf(code + ".KQ", start, end))]
        symbol, currency = code, "KRW"
    else:
        symbol = name = query.strip().upper()
        attempts = [("yfinance", lambda: _fetch_yf(symbol, start, end)),
                    ("FinanceDataReader", lambda: _fetch_fdr(symbol, start, end))]
        currency = "USD"

    for source, fn in attempts:
        try:
            df = _normalize(fn())
            if not df.empty:
                return PriceData(symbol, name, market, currency, df)
            errors.append(f"{source}: 데이터 없음")
        except Exception as e:  # 네트워크/파싱 오류 시 다음 소스로
            errors.append(f"{source}: {e}")
    raise RuntimeError(f"'{query}' 시세를 가져오지 못했습니다.\n" + "\n".join(errors))
