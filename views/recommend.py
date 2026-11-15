"""종목 추천 페이지: 매매법을 골라 미국 주식에서 조건에 맞는 종목을 찾고, 매도 계획까지 제시한다."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backtest import exit_prices, run_backtest, study_exits
from scanner import (BENCHMARK, Selection, download_fundamentals, download_panel, load_universe, parse_watchlist,
                     recommend)
from strategies import ALL_STRATEGIES, HORIZONS, Panel

UP, DOWN = "#d62728", "#1f77b4"
MARKERS = ["triangle-up", "star", "diamond", "circle", "square", "pentagon", "hexagon", "cross"]
COLORS = ["#00a65a", "#e6a700", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f"]
MARKET_OPTIONS = ["S&P 500", "나스닥 100", "S&P 500 + 나스닥 100", "관심종목 직접 입력"]
CATEGORIES = [("추세추종", "추세추종"), ("역추세", "역추세"), ("수급", "수급"), ("재무", "재무 (가치·배당·성장)")]


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=4)
def get_panel(tickers: tuple[str, ...]) -> tuple[Panel, pd.DataFrame]:
    P = download_panel(list(tickers) + [BENCHMARK])
    bench = pd.DataFrame()
    if BENCHMARK in P.tickers:
        bench = pd.DataFrame({"Open": P.open[BENCHMARK], "Close": P.close[BENCHMARK]})
        if BENCHMARK not in tickers:
            P = P.subset([t for t in P.tickers if t != BENCHMARK])
    return P, bench


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=4)
def get_fundamentals(tickers: tuple[str, ...]) -> pd.DataFrame:
    return download_fundamentals(list(tickers))


def atr_label(k: float) -> str:
    return "없음" if not np.isfinite(k) else f"{k:g} ATR"


def money(v) -> str:
    return "-" if v is None or not np.isfinite(v) else f"${v:,.2f}"


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
    horizon = st.radio("투자 기간", list(HORIZONS), index=1, horizontal=True, label_visibility="collapsed")
    h_desc, h_hold, h_recent = HORIZONS[horizon]
    st.caption(f"{horizon}: {h_desc}. 매매법 기본 설정, 매도 계획, 성과 검증 기간이 여기에 맞춰집니다.")

    st.header("3. 매매법")
    chosen = []
    for cat, label in CATEGORIES:
        st.markdown(f"**{label}**")
        for s in [x for x in ALL_STRATEGIES if x.category == cat]:
            if st.checkbox(s.name, value=s.key in ("golden_cross", "momentum"), key=f"use_{s.key}", help=s.summary):
                chosen.append(s)
    if any(s.kind == "fundamental" for s in chosen):
        st.caption("재무 매매법은 현재 재무 수치만 있어 과거 성과 검증에서 빠집니다. 중장기 투자에 어울립니다.")

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

    with st.expander("매도 계획 · 성과 검증 설정"):
        hold = st.number_input("최대 보유 기간 (거래일)", 1, 250, h_hold, key=f"hold_{horizon}",
                               help="목표가나 손절가에 닿지 않으면 이 기간이 지난 날 종가에 판다고 가정합니다.")
        cost = st.number_input("편도 거래비용 (%)", 0.0, 2.0, 0.25, 0.05, format="%.2f",
                               help="수수료와 슬리피지. 매수·매도 각각 적용합니다.")

    run = st.button("🎯 추천 받기", type="primary", width="stretch", disabled=not chosen)

# ───────────────────────── 본문 ─────────────────────────
st.title("🎯 미국 주식 종목 추천")
st.caption("유명한 매매법을 골라 규칙에 맞는 종목을 찾고, 언제 팔지(목표가·손절가)와 그 매매법의 과거 성과를 함께 보여줍니다.")

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
            "S&P 500 기준 약 1분(재무 매매법을 고르면 약 30초 추가)이 걸리고, 이후에는 바로 나옵니다.")
    st.stop()
if universe.empty:
    st.warning("종목을 입력하세요.")
    st.stop()

tickers = tuple(sorted(universe["ticker"]))
try:
    with st.spinner(f"{len(tickers)}개 종목 시세를 받는 중... (처음 한 번만 오래 걸립니다)"):
        P, bench = get_panel(tickers)
    F = None
    if any(s.kind == "fundamental" for s in chosen):
        with st.spinner(f"{len(tickers)}개 종목 재무 데이터를 받는 중..."):
            F = get_fundamentals(tickers)
except Exception as e:
    st.error(f"데이터를 받지 못했습니다: {e}")
    st.stop()

missing = sorted(set(tickers) - set(P.tickers))
sels = [Selection(s, params[s.key]) for s in chosen]
price_sels = [s for s in sels if s.strategy.kind == "price"]
last_date = P.close.index[-1]

if len(P.tickers) < 20 and any(s.key in ("momentum", "magic") for s in chosen):
    st.warning("모멘텀·마법공식은 종목들끼리 순위를 비교하는 매매법이라, 종목이 적으면 결과의 의미가 약합니다.")

rec = recommend(P, sels, universe, mode, recent, top_n, min_price, F)

# 과거 검증과 매도 규칙 (가격 기반 매매법이 있을 때만)
bt = study = None
if price_sels:
    with st.spinner("과거 신호와 매도 규칙을 검증하는 중..."):
        bt = run_backtest(P, price_sels, mode, recent, int(hold), cost, bench if not bench.empty else None, min_price)
        study = study_exits(P, bt)
    rule = study.best
else:
    from backtest import DEFAULT_RULE, ExitRule
    rule = ExitRule(*DEFAULT_RULE, source="일반 기준")

# ── 추천 결과 ──
st.subheader(f"추천 종목 {len(rec)}개")
st.caption(f"기준일 {last_date:%Y-%m-%d} (최근 거래일 종가) · 대상 {len(P.tickers)}종목 · "
           f"{'모두 만족' if mode == 'and' else '점수 합산'} · 투자 기간 {horizon}"
           + (f" · 시세 없음: {', '.join(missing[:10])}{' 외' if len(missing) > 10 else ''}" if missing else ""))

if rec.empty:
    st.warning("조건에 맞는 종목이 없습니다. '최근 며칠 안의 신호' 기간을 늘리거나, '점수 합산'으로 바꾸거나, "
               "매매법 세부 기준을 완화해 보세요.")
else:
    plans = {t: exit_prices(P, t, rule) for t in rec["ticker"]}
    names = {s.strategy.key: s.strategy.name for s in sels}

    def pct(v, base):
        return (v / base - 1) if v is not None else None

    table = pd.DataFrame({
        "순위": range(1, len(rec) + 1),
        "티커": rec["ticker"],
        "종목명": rec["name"],
        "현재가": rec["price"],
        "전일 대비": rec["chg_1d"] / 100,
        "점수": rec["score"],
        "목표가": [plans[t]["target"] for t in rec["ticker"]],
        "목표 수익": [pct(plans[t]["target"], plans[t]["price"]) for t in rec["ticker"]],
        "손절가": [plans[t]["stop"] for t in rec["ticker"]],
        "손절 손실": [pct(plans[t]["stop"], plans[t]["price"]) for t in rec["ticker"]],
        "신호": [" · ".join(f"{names[s.strategy.key]}" + ("" if s.strategy.kind == "fundamental" else f" ({d:%m/%d})")
                          for s, d in hits) for hits in rec["hits"]],
        "섹터": rec["sector"],
    })
    event = st.dataframe(
        table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={
            "현재가": st.column_config.NumberColumn(format="$%.2f"),
            "전일 대비": st.column_config.NumberColumn(format="percent"),
            "점수": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "목표가": st.column_config.NumberColumn(format="$%.2f"),
            "목표 수익": st.column_config.NumberColumn(format="percent"),
            "손절가": st.column_config.NumberColumn(format="$%.2f"),
            "손절 손실": st.column_config.NumberColumn(format="percent"),
            "신호": st.column_config.TextColumn(width="large"),
        })
    st.caption(f"행을 누르면 아래에 상세 근거, 매도 계획, 차트가 나옵니다. 목표가·손절가는 현재가에 매수한다고 가정하고 "
               f"종목별 변동폭(ATR)에 맞춰 계산했습니다: 목표 +{atr_label(rule.tp)}, 손절 −{atr_label(rule.sl)}, "
               f"최대 {int(hold)}거래일 보유 ({'과거 검증으로 선택' if rule.source == '검증' else '일반 기준'}).")
    st.download_button("추천 목록 CSV 받기", table.to_csv(index=False).encode("utf-8-sig"),
                       f"recommend_{last_date:%Y%m%d}.csv", "text/csv")

    # ── 상세 ──
    sel_rows = event.selection.rows if event and event.selection else []
    i = sel_rows[0] if sel_rows else 0
    row = rec.iloc[i]
    t = row["ticker"]
    plan = plans[t]
    st.divider()
    head, btn = st.columns([4, 1])
    head.subheader(f"{t} · {row['name']}")
    if btn.button("수익 계산기에서 열기", width="stretch"):
        st.session_state["calc_query"] = t
        st.switch_page("views/calculator.py")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**추천 근거**")
        for s, d in row["hits"]:
            why = (s.strategy.reason_f(F, t, s.params) if s.strategy.kind == "fundamental"
                   else s.strategy.reason(P, t, s.params, d))
            st.markdown(f"- **{s.strategy.name}**: {why}")
        hit_keys = {h.strategy.key for h, _ in row["hits"]}
        for s in sels:
            if s.strategy.key not in hit_keys:
                st.markdown(f"- <span style='opacity:.55'>{s.strategy.name}: 현재 신호 없음</span>",
                            unsafe_allow_html=True)
    with right:
        st.markdown("**📌 매도 계획** (오늘 종가에 매수 가정)")
        p0 = plan["price"]
        lines = [f"| 매수 기준가 | {money(p0)} | |", "|---|---|---|"]
        if plan["target"] is not None:
            lines.append(f"| 🎯 목표가 | **{money(plan['target'])}** | {(plan['target'] / p0 - 1) * 100:+.1f}% |")
        if plan["stop"] is not None:
            lines.append(f"| 🛑 손절가 | **{money(plan['stop'])}** | {(plan['stop'] / p0 - 1) * 100:+.1f}% |")
        lines.append(f"| ⏱ 최대 보유 | {int(hold)}거래일 | 만료 시 매도 |")
        lines.append(f"| 52주 최고가 | {money(plan['hi52'])} | {(plan['hi52'] / p0 - 1) * 100:+.1f}% |")
        lines.append(f"| 볼린저 상단 | {money(plan['bb_up'])} | {(plan['bb_up'] / p0 - 1) * 100:+.1f}% |")
        st.markdown("\n".join(lines))
        rr = f", 손익비 {plan['rr']:.1f} : 1" if plan["rr"] else ""
        st.caption(f"ATR(14) = {money(plan['atr'])} (하루 평균 변동폭, 주가의 {plan['atr'] / p0 * 100:.1f}%){rr}. "
                   "목표가 전에 52주 최고가·볼린저 상단 같은 저항선이 있으면 그 근처에서 일부 매도하는 것도 방법입니다.")

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
    for k, s in enumerate(price_sels):
        sig = s.strategy.compute(P.subset([t]), s.params).signal[t].loc[win]
        if s.strategy.is_state:  # 상태형은 조건이 새로 충족된 날만 표시
            sig = sig & ~sig.shift(1, fill_value=False)
        dates = sig[sig].index
        if len(dates):
            fig.add_trace(go.Scatter(
                x=dates, y=lo.loc[dates] * 0.97, mode="markers", name=s.strategy.name,
                marker=dict(symbol=MARKERS[k % len(MARKERS)], size=11, color=COLORS[k % len(COLORS)],
                            line=dict(width=1, color="black"))), 1, 1)
    if plan["target"] is not None:
        fig.add_hline(y=plan["target"], line_dash="dash", line_color="#00a65a", row=1, col=1,
                      annotation_text=f"목표 {money(plan['target'])}", annotation_position="top left")
    if plan["stop"] is not None:
        fig.add_hline(y=plan["stop"], line_dash="dash", line_color="#d62728", row=1, col=1,
                      annotation_text=f"손절 {money(plan['stop'])}", annotation_position="bottom left")
    fig.add_trace(go.Bar(x=win, y=v, showlegend=False, name="거래량",
                         marker_color=[UP if cc >= oo else DOWN for oo, cc in zip(o, c)]), 2, 1)
    fig.update_layout(height=560, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(fig, width="stretch")
    st.caption("아래쪽 표시는 지난 1년 동안 각 매매법 신호가 나온 날, 점선은 목표가·손절가입니다.")

# ── 과거 성과 검증 ──
st.divider()
st.subheader("📜 이 매매법의 과거 성과")
if bt is None:
    st.info("재무 매매법만 골라서 과거 성과를 검증할 수 없습니다. 재무 수치는 현재 값만 있어 과거 시점의 추천을 "
            "재현할 수 없기 때문입니다. 매도 계획은 일반 기준(목표 +3 ATR, 손절 −2 ATR)을 사용했습니다.")
    st.stop()

if len(price_sels) < len(sels):
    st.caption("ℹ️ 재무 매매법은 과거 시점의 재무 수치가 없어 검증에서 빠졌습니다. 아래는 가격 기반 매매법만의 결과입니다.")
stats = bt.stats()
st.caption(f"검증 기간 {bt.start:%Y-%m-%d} ~ {bt.end:%Y-%m-%d} · 대상 종목 전체에서 추천 조건이 새로 충족된 날 "
           f"다음 날 시가에 사서 {bt.hold}거래일 뒤 종가에 판 것으로 계산 · 비용 편도 {bt.cost_pct:.2f}% 반영")
if not stats:
    st.info("검증 기간에 신호가 한 번도 없었습니다.")
    st.stop()

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
    hist.add_vline(x=stats["평균"], line_color=UP, line_dash="dash", annotation_text=f"평균 {stats['평균']:+.1f}%")
    hist.update_layout(title="거래별 수익률 분포 (%)", height=320, margin=dict(l=10, r=10, t=40, b=10),
                       showlegend=False)
    st.plotly_chart(hist, width="stretch")
with right:
    tr = bt.trades.copy()
    tr["분기"] = tr["signal_date"].dt.to_period("Q").astype(str)
    q = tr.groupby("분기")["ret"].agg(["mean", "count"]).reset_index()
    bar = go.Figure(go.Bar(x=q["분기"], y=q["mean"], text=q["count"].map(lambda n: f"{n}회"),
                           marker_color=[UP if x >= 0 else DOWN for x in q["mean"]]))
    bar.update_layout(title="분기별 평균 수익률 (%)과 신호 횟수", height=320, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(bar, width="stretch")

# ── 매도 규칙 검증 ──
st.markdown("### 🎯 언제 팔아야 했나: 매도 규칙 비교")
if study.grid.empty:
    st.info(f"과거 거래가 {study.n}회뿐이라 매도 규칙을 검증하지 않고 일반 기준(목표 +3 ATR, 손절 −2 ATR)을 썼습니다.")
else:
    st.caption(f"같은 과거 신호 {study.n}회에 여러 매도 규칙을 적용해 봤습니다. 목표가·손절가는 매수 시점 ATR(하루 평균 "
               f"변동폭)의 배수이고, 둘 다 닿지 않으면 {bt.hold}거래일 뒤 종가에 팝니다. 하루에 둘 다 닿으면 손절로 계산합니다.")
    rows = []
    for label, r in (("추천 규칙", study.best), ("일반 기준", study.default), ("목표·손절 없이 보유", study.hold_only)):
        rows.append({"규칙": label, "목표": "+" + atr_label(r.tp), "손절 기준": "−" + atr_label(r.sl),
                     "평균 수익률(%)": r.mean, "승률(%)": r.win, "목표가 도달(%)": r.tp_rate,
                     "손절 발생(%)": r.sl_rate})
    cmp = pd.DataFrame(rows)
    st.dataframe(cmp, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.1f")
                                for c in cmp.columns if "(%)" in c})

    b, ho = study.best, study.hold_only
    diff = b.mean - ho.mean
    if diff >= 0.2:
        msg = (f"이 매매법은 **목표 +{atr_label(b.tp)}에서 이익 실현, −{atr_label(b.sl)}에서 손절**했을 때 그냥 보유한 것보다 "
               f"평균 {diff:+.2f}%p 나았습니다.")
    elif diff > -0.2:
        msg = (f"목표가·손절가를 두든 그냥 보유하든 평균 성과가 비슷했습니다. 손실을 제한하는 효과를 위해 "
               f"**목표 +{atr_label(b.tp)}, 손절 −{atr_label(b.sl)}**를 권합니다.")
    else:
        msg = (f"이 기간에는 **목표가 없이 보유한 쪽이 평균 {-diff:.2f}%p 더 좋았습니다** (오르는 종목을 일찍 팔지 않는 게 "
               f"유리했던 상승장). 목표가를 둔다면 **+{atr_label(b.tp)}처럼 넉넉하게**, 손절은 −{atr_label(b.sl)} 정도가 "
               f"가장 덜 손해였습니다.")
    st.markdown(msg)

    with st.expander("모든 목표·손절 조합의 평균 수익률 보기"):
        g = study.grid
        z = g.to_numpy(dtype=float)
        heat = go.Figure(go.Heatmap(
            z=z, x=["−" + atr_label(x) for x in g.columns], y=["+" + atr_label(y) for y in g.index],
            colorscale="RdBu", zmid=float(ho.mean), text=np.round(z, 2), texttemplate="%{text}",
            colorbar=dict(title="평균 %")))
        heat.update_layout(height=460, margin=dict(l=10, r=10, t=30, b=10),
                           xaxis_title="손절 기준", yaxis_title="목표 기준")
        st.plotly_chart(heat, width="stretch")
        st.caption("가운데 색(흰색)이 '그냥 보유'한 경우의 평균입니다. 빨간색일수록 그보다 나쁘고, 파란색일수록 좋습니다. "
                   "추천 규칙은 우연히 튄 한 칸을 고르지 않도록 이웃 칸과 평균낸 값으로 골랐습니다.")

with st.expander("과거 거래 내역 보기"):
    st.dataframe(bt.trades.drop(columns=["i", "j"]).sort_values("signal_date", ascending=False).rename(columns={
        "ticker": "티커", "signal_date": "신호일", "exit_date": "매도일", "ret": "수익률(%)"}),
        hide_index=True, width="stretch",
        column_config={"수익률(%)": st.column_config.NumberColumn(format="%+.2f")})

st.caption("⚠️ 추천과 매도 계획은 정해진 규칙에 따른 계산 결과이며 투자 권유가 아닙니다. 과거 성과 검증은 현재 지수 "
           "구성 종목만 사용하므로(생존 편향) 실제보다 좋게 나올 수 있고, 과거 성과가 미래 수익을 보장하지 않습니다. "
           "데이터: Yahoo Finance (수정주가·재무).")
