"""주식 수익 계산기 & 추세 분석 페이지."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis import FeeConfig, add_indicators, best_trade, calc_trade, summarize_trend
from data import detect_market, load_prices

UP, DOWN, NEUTRAL = "#d62728", "#1f77b4", "#7f7f7f"   # 한국식: 상승 빨강, 하락 파랑
FEE_DEFAULTS = {  # (매수 수수료 %, 매도 수수료 %, 매도 거래세 %)
    "KR": (0.015, 0.015, 0.20),
    "US": (0.25, 0.25, 0.0),
}
LOOKBACK_DAYS = 200  # 지표(MA120 등) 계산용으로 조회 시작일 이전 데이터를 더 받는다


@st.cache_data(ttl=3600, show_spinner=False)
def cached_load(query: str, start: dt.date, end: dt.date):
    return load_prices(query, start, end)


def money(v: float, cur: str, sign: bool = False) -> str:
    s = "+" if sign and v > 0 else ""
    if cur == "KRW":
        return f"{s}{v:,.0f}원"
    return f"{s}${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def price_str(v: float, cur: str) -> str:
    return f"{v:,.0f}원" if cur == "KRW" else f"${v:,.2f}"


# ───────────────────────── 사이드바 입력 ─────────────────────────
with st.sidebar:
    st.header("종목 · 기간")
    st.session_state.setdefault("calc_query", "005930")
    query = st.text_input("종목", key="calc_query",
                          help="한국: 6자리 코드(005930) 또는 종목명(삼성전자)\n미국: 티커(AAPL, TSLA)")
    today = dt.date.today()
    start = st.date_input("조회 시작", today - dt.timedelta(days=365), max_value=today)
    end = st.date_input("조회 종료", today, max_value=today)

    st.header("매매 시뮬레이션")
    buy_date = st.date_input("매수일", start, min_value=start, max_value=end)
    sell_date = st.date_input("매도일", end, min_value=start, max_value=end)
    labels = {"시가": "Open", "종가": "Close"}
    c1, c2 = st.columns(2)
    buy_field = labels[c1.radio("매수 가격", list(labels), index=1, horizontal=True)]
    sell_field = labels[c2.radio("매도 가격", list(labels), index=1, horizontal=True)]

    mode = st.radio("투자 방식", ["투자금", "수량"], horizontal=True)
    market = detect_market(query) if query.strip() else "KR"
    if mode == "투자금":
        default_amt = 10_000_000 if market == "KR" else 10_000
        amount = st.number_input(f"투자금 ({'원' if market == 'KR' else 'USD'})",
                                 min_value=0.0, value=float(default_amt), step=float(default_amt / 10))
        quantity = None
    else:
        quantity = st.number_input("수량 (주)", min_value=0.0, value=10.0, step=1.0)
        amount = None
    fractional = st.checkbox("소수점 주식 허용", value=False) if mode == "투자금" else False

    with st.expander("수수료 · 세금 설정"):
        d_bc, d_sc, d_tax = FEE_DEFAULTS[market]
        bc = st.number_input("매수 수수료 (%)", 0.0, 5.0, d_bc, 0.005, format="%.3f", key=f"bc_{market}")
        sc = st.number_input("매도 수수료 (%)", 0.0, 5.0, d_sc, 0.005, format="%.3f", key=f"sc_{market}")
        tax = st.number_input("매도 거래세 (%)", 0.0, 5.0, d_tax, 0.01, format="%.2f", key=f"tx_{market}")
        st.caption("기본값은 대략적인 예시입니다. 이용 중인 증권사 수수료와 현행 세율로 바꿔 주세요. "
                   "환율, 양도소득세, 배당은 반영하지 않습니다.")

    st.header("추세 분석")
    window = st.slider("회귀 분석 구간 (거래일)", 10, 120, 20, 5)

# ───────────────────────── 데이터 로드 ─────────────────────────
st.title("📈 주식 수익 계산기 & 추세 분석")

if not query.strip():
    st.info("왼쪽에서 종목을 입력하세요.")
    st.stop()
if start >= end:
    st.error("조회 시작일은 종료일보다 앞이어야 합니다.")
    st.stop()

try:
    with st.spinner("시세를 불러오는 중..."):
        pdata = cached_load(query.strip(), start - dt.timedelta(days=LOOKBACK_DAYS), end)
except Exception as e:
    st.error(str(e))
    st.stop()

cur = pdata.currency
full = add_indicators(pdata.df)
period = full.loc[pd.Timestamp(start):pd.Timestamp(end)]
if period.empty:
    st.error("선택한 기간에 거래 데이터가 없습니다.")
    st.stop()

last, prev = period.iloc[-1], (period.iloc[-2] if len(period) > 1 else period.iloc[-1])
chg = (last["Close"] / prev["Close"] - 1) * 100
st.subheader(f"{pdata.name} ({pdata.symbol}) · {'한국' if pdata.market == 'KR' else '미국'}")
st.caption(f"최근 거래일 {period.index[-1]:%Y-%m-%d} 종가 **{price_str(last['Close'], cur)}** "
           f"({chg:+.2f}%) · 데이터 {len(period)}거래일")

# ───────────────────────── 매매 결과 ─────────────────────────
fees = FeeConfig(bc / 100, sc / 100, tax / 100)
trade = None
try:
    trade = calc_trade(period, buy_date, sell_date, buy_field, sell_field, fees,
                       quantity=quantity, amount=amount, fractional=fractional)
except ValueError as e:
    st.warning(f"매매 시뮬레이션: {e}")

if trade:
    st.markdown("### 💰 매매 결과")
    m = st.columns(4)
    m[0].metric("순손익 (비용 차감 후)", money(trade.net_profit, cur, sign=True),
                f"{trade.return_pct:+.2f}%")
    m[1].metric(f"매수 · {trade.buy_date:%Y-%m-%d}", price_str(trade.buy_price, cur))
    m[2].metric(f"매도 · {trade.sell_date:%Y-%m-%d}", price_str(trade.sell_price, cur),
                f"{(trade.sell_price / trade.buy_price - 1) * 100:+.2f}% (주가 변동)")
    m[3].metric("보유 기간", f"{trade.holding_days}일",
                f"연환산 {trade.annualized_pct:+.1f}%" if trade.annualized_pct is not None else "연환산: 30일 미만",
                delta_color="normal" if trade.annualized_pct is not None else "off")
    for n in trade.notes:
        st.caption(f"ℹ️ {n}")

    qty_txt = f"{trade.quantity:,.4f}".rstrip("0").rstrip(".")
    detail = pd.DataFrame({
        "항목": ["수량", "매수 금액", "매수 수수료", "총 투입금", "매도 금액", "매도 수수료", "거래세",
               "총 회수금", "비용 차감 전 손익", "총 비용", "순손익"],
        "값": [f"{qty_txt}주", money(trade.buy_amount, cur), money(trade.buy_fee, cur),
              money(trade.buy_amount + trade.buy_fee, cur), money(trade.sell_amount, cur),
              money(trade.sell_fee, cur), money(trade.sell_tax, cur),
              money(trade.sell_amount - trade.sell_fee - trade.sell_tax, cur),
              money(trade.gross_profit, cur, sign=True),
              money(trade.buy_fee + trade.sell_fee + trade.sell_tax, cur),
              money(trade.net_profit, cur, sign=True)],
    })
    with st.expander("상세 내역"):
        st.dataframe(detail, hide_index=True, width="stretch")

    bt = best_trade(period)
    if bt:
        st.caption(f"참고: 이 기간 종가 기준 최적 매매는 {bt[0]:%Y-%m-%d} 매수 → {bt[1]:%Y-%m-%d} 매도 "
                   f"({bt[2]:+.1f}%, 비용 제외)였습니다. 사후에만 알 수 있는 값입니다.")

# ───────────────────────── 추세 요약 ─────────────────────────
st.markdown("### 🧭 시황 추세")
try:
    tr = summarize_trend(full, period, window)
except ValueError as e:
    st.warning(str(e))
    tr = None

if tr:
    color = UP if tr.score >= 20 else DOWN if tr.score <= -20 else NEUTRAL
    left, right = st.columns([1, 2])
    with left:
        st.markdown(
            f"<div style='border:1px solid {color};border-radius:12px;padding:16px;text-align:center'>"
            f"<div style='font-size:0.9rem;opacity:.7'>현재 추세 판정</div>"
            f"<div style='font-size:2rem;font-weight:700;color:{color}'>{tr.label}</div>"
            f"<div style='font-size:0.9rem'>점수 {tr.score:+d} / ±100</div></div>",
            unsafe_allow_html=True)
        k = st.columns(2)
        k[0].metric("기간 수익률", f"{tr.period_return_pct:+.1f}%")
        k[1].metric("최대 낙폭", f"{tr.max_drawdown_pct:.1f}%")
        k = st.columns(2)
        k[0].metric("연 변동성", f"{tr.volatility_pct:.1f}%")
        k[1].metric("RSI(14)", f"{tr.rsi:.0f}" if tr.rsi is not None else "-")
    with right:
        icon = {"up": "🔺", "down": "🔻", "neutral": "▫️"}
        st.markdown("**판단 근거**")
        st.markdown("\n".join(f"- {icon[k]} {msg}" for k, msg in tr.signals))
        st.caption("점수 구성: 회귀 기울기×R²(±35), 이동평균 배열(±25), 20일선 위치(±10), "
                   "최근 골든·데드크로스(±10), MACD(±10). RSI는 과열/침체 경고로만 사용합니다.")

# ───────────────────────── 차트 ─────────────────────────
st.markdown("### 📊 차트")
show = st.multiselect("표시할 지표", ["MA5", "MA20", "MA60", "MA120", "볼린저밴드"],
                      default=["MA5", "MA20", "MA60"])
fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                    row_heights=[0.55, 0.15, 0.15, 0.15],
                    subplot_titles=("가격", "거래량", "RSI(14)", "MACD"))
fig.add_trace(go.Candlestick(x=period.index, open=period["Open"], high=period["High"],
                             low=period["Low"], close=period["Close"], name="가격",
                             increasing_line_color=UP, decreasing_line_color=DOWN), 1, 1)
ma_colors = {"MA5": "#ff7f0e", "MA20": "#2ca02c", "MA60": "#9467bd", "MA120": "#8c564b"}
for ma, c in ma_colors.items():
    if ma in show:
        fig.add_trace(go.Scatter(x=period.index, y=period[ma], name=ma, line=dict(width=1.2, color=c)), 1, 1)
if "볼린저밴드" in show:
    fig.add_trace(go.Scatter(x=period.index, y=period["BB_upper"], name="BB 상단",
                             line=dict(width=0.8, dash="dot", color="gray")), 1, 1)
    fig.add_trace(go.Scatter(x=period.index, y=period["BB_lower"], name="BB 하단", fill="tonexty",
                             fillcolor="rgba(128,128,128,0.08)",
                             line=dict(width=0.8, dash="dot", color="gray")), 1, 1)
if trade:
    fig.add_trace(go.Scatter(x=[trade.buy_date], y=[trade.buy_price], mode="markers+text", name="매수",
                             text=["매수"], textposition="bottom center",
                             marker=dict(symbol="triangle-up", size=14, color="#00a65a",
                                         line=dict(width=1, color="black"))), 1, 1)
    fig.add_trace(go.Scatter(x=[trade.sell_date], y=[trade.sell_price], mode="markers+text", name="매도",
                             text=["매도"], textposition="top center",
                             marker=dict(symbol="triangle-down", size=14, color="#e6a700",
                                         line=dict(width=1, color="black"))), 1, 1)
    fig.add_vrect(x0=trade.buy_date, x1=trade.sell_date, fillcolor="rgba(0,166,90,0.06)",
                  line_width=0, row=1, col=1)

vol_colors = [UP if c >= o else DOWN for o, c in zip(period["Open"], period["Close"])]
fig.add_trace(go.Bar(x=period.index, y=period["Volume"], marker_color=vol_colors, name="거래량",
                     showlegend=False), 2, 1)
fig.add_trace(go.Scatter(x=period.index, y=period["RSI"], name="RSI", line=dict(color="#9467bd"),
                         showlegend=False), 3, 1)
for lvl in (30, 70):
    fig.add_hline(y=lvl, line_dash="dash", line_color="gray", line_width=0.8, row=3, col=1)
hist_colors = [UP if v >= 0 else DOWN for v in period["MACD_hist"].fillna(0)]
fig.add_trace(go.Bar(x=period.index, y=period["MACD_hist"], marker_color=hist_colors, name="MACD 히스토그램",
                     showlegend=False), 4, 1)
fig.add_trace(go.Scatter(x=period.index, y=period["MACD"], name="MACD", line=dict(width=1, color="#1f77b4"),
                         showlegend=False), 4, 1)
fig.add_trace(go.Scatter(x=period.index, y=period["MACD_signal"], name="Signal",
                         line=dict(width=1, color="#ff7f0e"), showlegend=False), 4, 1)

fig.update_layout(height=850, xaxis_rangeslider_visible=False, hovermode="x unified",
                  margin=dict(l=10, r=10, t=40, b=10),
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
fig.update_yaxes(range=[0, 100], row=3, col=1)
fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])  # 주말 공백 제거
st.plotly_chart(fig, width="stretch")

with st.expander("원본 데이터"):
    st.dataframe(period[["Open", "High", "Low", "Close", "Volume"]].sort_index(ascending=False),
                 width="stretch")

st.caption("⚠️ 과거 데이터 기반 시뮬레이션과 기술적 지표일 뿐이며 투자 권유가 아닙니다. "
           "데이터 출처: FinanceDataReader(네이버 등), Yahoo Finance.")
