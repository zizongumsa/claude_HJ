"""종목 추천 페이지: 매매법을 골라 미국 주식에서 조건에 맞는 종목을 찾는다."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backtest import run_backtest
from scanner import BENCHMARK, Selection, download_panel, load_universe, parse_watchlist, recommend
from strategies import ALL_STRATEGIES, HORIZONS, Panel

UP, DOWN = "#d62728", "#1f77b4"
MARKERS = ["triangle-up", "star", "diamond", "circle", "square", "pentagon", "hexagon", "cross"]
COLORS = ["#00a65a", "#e6a700", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f"]
MARKET_OPTIONS = ["S&P 500", "나스닥 100", "S&P 500 + 나스닥 100", "관심종목 직접 입력"]


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=4)
def get_panel(tickers: tuple[str, ...]) -> tuple[Panel, pd.DataFrame]:
    P = download_panel(list(tickers) + [BENCHMARK])
    bench = pd.DataFrame()
    if BENCHMARK in P.tickers:
        bench = pd.DataFrame({"Open": P.open[BENCHMARK], "Close": P.close[BENCHMARK]})
        if BENCHMARK not in tickers:
            P = P.subset([t for t in P.tickers if t != BENCHMARK])
    return P, bench


# ───────────────────────── 사이드바 ─────────────────────────
with st.sidebar:
    st.header("1. 대상 종목")
    market = st.selectbox("시장", MARKET_OPTIONS)
    if market == "관심종목 직접 입력":
        watch = st.text_area("티커 (쉼표 또는 줄바꿈으로 구분)", "AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO")
        universe = parse_watchlist(watch)
    else:
        universe = load_universe(market)
    st.caption(f"{len(universe)}개 종목")

    st.header("2. 투자 기간")
    horizon = st.radio("투자 기간", list(HORIZONS), index=1, horizontal=True, label_visibility="collapsed",
                       format_func=lambda h: h)
    h_desc, h_hold, h_recent = HORIZONS[horizon]
    st.caption(f"{horizon}: {h_desc}. 매매법 기본 설정과 성과 검증 기간이 여기에 맞춰집니다.")

    st.header("3. 매매법")
    chosen = []
    for cat in ("추세추종", "역추세", "수급"):
        st.markdown(f"**{cat}**")
        for s in [x for x in ALL_STRATEGIES if x.category == cat]:
            if st.checkbox(s.name, value=s.key in ("golden_cross", "momentum"), key=f"use_{s.key}", help=s.summary):
                chosen.append(s)

    mode_label = st.radio("여러 매매법을 고르면", ["점수 합산", "모두 만족 (AND)"], horizontal=True,
                          help="점수 합산: 하나라도 신호가 있으면 후보가 되고, 신호가 많고 강할수록 위로 올라갑니다.\n"
                               "모두 만족: 고른 매매법의 신호가 모두 있는 종목만 추천합니다.")
    mode = "and" if mode_label.startswith("모두") else "score"

    with st.expander("세부 설정"):
        recent = st.slider("최근 며칠 안의 신호까지 인정 (거래일)", 1, 20, h_recent, key=f"recent_{horizon}",
                           help="골든크로스·돌파 같은 '그날 발생하는' 신호를 며칠 전까지 유효하게 볼지 정합니다.")
        top_n = st.slider("추천 개수 (최대)", 5, 50, 20, 5)
        min_price = st.number_input("최소 주가 ($)", 0.0, 100.0, 5.0, 1.0, help="이보다 싼 종목은 제외합니다.")
        params: dict[str, dict] = {}
        for s in chosen:
            st.markdown(f"**{s.name}**")
            vals = {}
            for p in s.params:
                k = f"p_{s.key}_{p.key}_{horizon}"
                d = p.default(horizon)
                if isinstance(d, bool):
                    vals[p.key] = st.checkbox(p.label, d, key=k, help=p.help)
                elif isinstance(d, int):
                    vals[p.key] = int(st.number_input(p.label, int(p.min), int(p.max), d, int(p.step), key=k,
                                                      help=p.help))
                else:
                    vals[p.key] = float(st.number_input(p.label, float(p.min), float(p.max), float(d),
                                                        float(p.step), key=k, help=p.help))
            params[s.key] = vals

    with st.expander("성과 검증 설정"):
        hold = st.number_input("보유 기간 (거래일)", 1, 250, h_hold, key=f"hold_{horizon}",
                               help="신호 다음 날 시가에 사서 이 기간 뒤 종가에 판다고 가정합니다.")
        cost = st.number_input("편도 거래비용 (%)", 0.0, 2.0, 0.25, 0.05, format="%.2f",
                               help="수수료와 슬리피지. 매수·매도 각각 적용합니다.")

    run = st.button("🎯 추천 받기", type="primary", width="stretch", disabled=not chosen)

# ───────────────────────── 본문 ─────────────────────────
st.title("🎯 미국 주식 종목 추천")
st.caption("유명한 매매법을 골라 규칙에 맞는 종목을 찾고, 그 매매법이 과거에 어떤 성과를 냈는지 함께 보여줍니다.")

if not chosen:
    st.info("왼쪽에서 매매법을 하나 이상 고르세요.")
    st.stop()

if run:
    st.session_state["ran"] = True
with st.expander(f"선택한 매매법 설명 ({len(chosen)}개)", expanded=not st.session_state.get("ran")):
    for s in chosen:
        st.markdown(f"**{s.name}** · {s.category}  \n{s.summary}")
        st.caption(s.description)

if not st.session_state.get("ran"):
    st.info("설정을 마친 뒤 왼쪽 아래 **추천 받기**를 누르세요. 처음 한 번은 시세를 받느라 "
            "S&P 500 기준 약 1분이 걸리고, 이후 6시간 동안은 바로 나옵니다.")
    st.stop()
if universe.empty:
    st.warning("종목을 입력하세요.")
    st.stop()

tickers = tuple(sorted(universe["ticker"]))
try:
    with st.spinner(f"{len(tickers)}개 종목 시세를 받는 중... (처음 한 번만 오래 걸립니다)"):
        P, bench = get_panel(tickers)
except Exception as e:
    st.error(f"시세를 받지 못했습니다: {e}")
    st.stop()

missing = sorted(set(tickers) - set(P.tickers))
sels = [Selection(s, params[s.key]) for s in chosen]
last_date = P.close.index[-1]

if len(P.tickers) < 20 and any(s.key == "momentum" for s in chosen):
    st.warning("모멘텀은 종목들끼리 순위를 비교하는 매매법이라, 종목이 적으면 결과의 의미가 약합니다.")

rec = recommend(P, sels, universe, mode, recent, top_n, min_price)

# ── 추천 결과 ──
st.subheader(f"추천 종목 {len(rec)}개")
st.caption(f"기준일 {last_date:%Y-%m-%d} (최근 거래일 종가) · 대상 {len(P.tickers)}종목 · "
           f"{'모두 만족' if mode == 'and' else '점수 합산'} · 투자 기간 {horizon}"
           + (f" · 시세 없음: {', '.join(missing[:10])}{' 외' if len(missing) > 10 else ''}" if missing else ""))

if rec.empty:
    st.warning("조건에 맞는 종목이 없습니다. '최근 며칠 안의 신호' 기간을 늘리거나, '점수 합산'으로 바꾸거나, "
               "매매법을 바꿔 보세요.")
else:
    names = {s.strategy.key: s.strategy.name for s in sels}
    table = pd.DataFrame({
        "순위": range(1, len(rec) + 1),
        "티커": rec["ticker"],
        "종목명": rec["name"],
        "섹터": rec["sector"],
        "현재가": rec["price"],
        "전일 대비": rec["chg_1d"] / 100,
        "점수": rec["score"],
        "신호": [" · ".join(f"{names[s.strategy.key]} ({d:%m/%d})" for s, d in hits) for hits in rec["hits"]],
    })
    event = st.dataframe(
        table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={
            "현재가": st.column_config.NumberColumn(format="$%.2f"),
            "전일 대비": st.column_config.NumberColumn(format="percent"),
            "점수": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "신호": st.column_config.TextColumn(width="large"),
        })
    st.caption("행을 누르면 아래에 차트와 상세 근거가 나옵니다. 점수는 각 매매법 신호 강도(0~100)의 평균입니다.")
    st.download_button("추천 목록 CSV 받기", table.to_csv(index=False).encode("utf-8-sig"),
                       f"recommend_{last_date:%Y%m%d}.csv", "text/csv")

    # ── 상세 ──
    sel_rows = event.selection.rows if event and event.selection else []
    i = sel_rows[0] if sel_rows else 0
    row = rec.iloc[i]
    t = row["ticker"]
    st.divider()
    head, btn = st.columns([4, 1])
    head.subheader(f"{t} · {row['name']}")
    if btn.button("수익 계산기에서 열기", width="stretch"):
        st.session_state["calc_query"] = t
        st.switch_page("views/calculator.py")

    st.markdown("**추천 근거**")
    for s, d in row["hits"]:
        st.markdown(f"- **{s.strategy.name}**: {s.strategy.reason(P, t, s.params, d)}")
    not_hit = [s for s in sels if s.strategy.key not in {h.strategy.key for h, _ in row["hits"]}]
    for s in not_hit:
        st.markdown(f"- <span style='opacity:.55'>{s.strategy.name}: 현재 신호 없음</span>",
                    unsafe_allow_html=True)

    # 차트: 최근 1년
    win = P.close.index[-252:]
    o, h, lo, c, v = (getattr(P, f)[t].loc[win] for f in ("open", "high", "low", "close", "volume"))
    full_c = P.close[t]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=win, open=o, high=h, low=lo, close=c, name=t,
                                 increasing_line_color=UP, decreasing_line_color=DOWN), 1, 1)
    for n, col in ((20, "#ff7f0e"), (50, "#2ca02c"), (200, "#9467bd")):
        fig.add_trace(go.Scatter(x=win, y=full_c.rolling(n).mean().loc[win], name=f"MA{n}",
                                 line=dict(width=1.1, color=col)), 1, 1)
    for k, s in enumerate(sels):
        sig = s.strategy.compute(P.subset([t]), s.params).signal[t].loc[win]
        if s.strategy.is_state:  # 상태형은 조건이 새로 충족된 날만 표시
            sig = sig & ~sig.shift(1, fill_value=False)
        dates = sig[sig].index
        if len(dates):
            fig.add_trace(go.Scatter(
                x=dates, y=lo.loc[dates] * 0.97, mode="markers", name=s.strategy.name,
                marker=dict(symbol=MARKERS[k % len(MARKERS)], size=11, color=COLORS[k % len(COLORS)],
                            line=dict(width=1, color="black"))), 1, 1)
    fig.add_trace(go.Bar(x=win, y=v, showlegend=False, name="거래량",
                         marker_color=[UP if cc >= oo else DOWN for oo, cc in zip(o, c)]), 2, 1)
    fig.update_layout(height=560, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(fig, width="stretch")
    st.caption("아래쪽 표시는 지난 1년 동안 각 매매법 신호가 나온 날입니다.")

# ── 과거 성과 검증 ──
st.divider()
st.subheader("📜 이 매매법의 과거 성과")
with st.spinner("과거 신호를 검증하는 중..."):
    bt = run_backtest(P, sels, mode, recent, int(hold), cost, bench if not bench.empty else None, min_price)
stats = bt.stats()
st.caption(f"검증 기간 {bt.start:%Y-%m-%d} ~ {bt.end:%Y-%m-%d} · 대상 종목 전체에서 추천 조건이 새로 충족된 날 "
           f"다음 날 시가에 사서 {bt.hold}거래일 뒤 종가에 판 것으로 계산 · 비용 편도 {bt.cost_pct:.2f}% 반영")
if not stats:
    st.info("검증 기간에 신호가 한 번도 없었습니다.")
else:
    m = st.columns(4)
    m[0].metric("과거 신호 (거래 수)", f"{stats['거래 수']:,}회")
    m[1].metric("승률", f"{stats['승률']:.1f}%")
    m[2].metric("평균 수익률", f"{stats['평균']:+.2f}%",
                f"{stats['평균'] - bt.baseline_mean:+.2f}%p (아무 종목 매수 대비)")
    m[3].metric("중간값 수익률", f"{stats['중간값']:+.2f}%")
    m = st.columns(4)
    m[0].metric("아무 종목·아무 날 매수 평균", f"{bt.baseline_mean:+.2f}%", help="같은 종목들, 같은 기간, 같은 보유 기간")
    m[1].metric("같은 날 SPY 매수 평균", f"{bt.benchmark_mean:+.2f}%" if bt.benchmark_mean is not None else "-")
    m[2].metric("하위 10% 거래", f"{stats['하위 10%']:+.1f}% 이하", help="거래 10번 중 가장 나빴던 1번의 수준")
    m[3].metric("상위 10% 거래", f"{stats['상위 10%']:+.1f}% 이상", help="거래 10번 중 가장 좋았던 1번의 수준")

    if stats["거래 수"] < 50:
        st.warning(f"과거 신호가 {stats['거래 수']}회뿐이라 우연의 영향이 큽니다. 종목 수가 많은 시장으로 검증해 보세요.")
    edge = stats["평균"] - bt.baseline_mean
    verdict = ("아무 종목이나 산 것보다 **나았습니다**" if edge > 0.3 else
               "아무 종목이나 산 것보다 **못했습니다**" if edge < -0.3 else "아무 종목이나 산 것과 **비슷했습니다**")
    st.markdown(f"이 설정은 검증 기간 동안 평균적으로 {verdict} (차이 {edge:+.2f}%p). "
                f"가장 나빴던 거래는 {stats['최악']:+.1f}%, 가장 좋았던 거래는 {stats['최고']:+.1f}%였습니다.")

    left, right = st.columns(2)
    with left:
        hist = go.Figure(go.Histogram(x=bt.trades["ret"], nbinsx=50, marker_color="#7f7f7f"))
        hist.add_vline(x=0, line_color="black", line_width=1)
        hist.add_vline(x=stats["평균"], line_color=UP, line_dash="dash",
                       annotation_text=f"평균 {stats['평균']:+.1f}%")
        hist.update_layout(title="거래별 수익률 분포 (%)", height=320, margin=dict(l=10, r=10, t=40, b=10),
                           showlegend=False)
        st.plotly_chart(hist, width="stretch")
    with right:
        tr = bt.trades.copy()
        tr["분기"] = tr["signal_date"].dt.to_period("Q").astype(str)
        q = tr.groupby("분기")["ret"].agg(["mean", "count"]).reset_index()
        bar = go.Figure(go.Bar(x=q["분기"], y=q["mean"], text=q["count"].map(lambda n: f"{n}회"),
                               marker_color=[UP if x >= 0 else DOWN for x in q["mean"]]))
        bar.update_layout(title="분기별 평균 수익률 (%)과 신호 횟수", height=320,
                          margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(bar, width="stretch")

    with st.expander("과거 거래 내역 보기"):
        st.dataframe(bt.trades.sort_values("signal_date", ascending=False).rename(columns={
            "ticker": "티커", "signal_date": "신호일", "exit_date": "매도일", "ret": "수익률(%)"}),
            hide_index=True, width="stretch",
            column_config={"수익률(%)": st.column_config.NumberColumn(format="%+.2f")})

st.caption("⚠️ 추천은 정해진 규칙에 맞는 종목을 걸러낸 결과이며 투자 권유가 아닙니다. 과거 성과 검증은 현재 지수 "
           "구성 종목만 사용하므로(생존 편향) 실제보다 좋게 나올 수 있고, 과거 성과가 미래 수익을 보장하지 않습니다. "
           "데이터: Yahoo Finance (수정주가).")
