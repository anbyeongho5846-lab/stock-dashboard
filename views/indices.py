"""페이지: 지수 · 환율 — 코스피·코스닥, 환율, 해외 지수, 금리·원자재·심리 지표."""

import plotly.graph_objects as go
import streamlit as st

from common import (
    page_header, chip, now_kst,
    cached_market_quotes, cached_index_history, quote_cards_html,
    UP_COLOR, DOWN_COLOR,
)
from market_index import ITEMS, GROUPS, PERIODS


def _plot_history(key: str, period: str, quote: dict | None) -> None:
    it = ITEMS[key]
    s = cached_index_history(key, period)
    if s.empty or len(s) < 2:
        st.info(f"{it['name']}의 {period} 추이 데이터를 가져오지 못했습니다. "
                "(해외 시장은 장이 열리지 않은 시간엔 '오늘' 데이터가 없을 수 있습니다)")
        return

    last = float(s.iloc[-1])
    # 기준선: '오늘'은 전일 종가(현재가 - 전일 대비), 그 외는 기간 시작 값
    base = float(s.iloc[0])
    base_label = "기간 시작"
    if period == "오늘" and quote:
        base = quote["price"] - quote["change"]
        base_label = "전일 종가"
    chg = (last / base - 1) * 100 if base else 0.0
    color = UP_COLOR if last >= base else DOWN_COLOR
    fill = "rgba(239,68,68,0.12)" if last >= base else "rgba(59,130,246,0.12)"
    dec = it.get("dec", 2)

    lo = float(s.min())
    pad = (float(s.max()) - lo) * 0.08 or abs(lo) * 0.01
    floor = min(lo, base) - pad
    x_fmt = "%H:%M" if period == "오늘" else "%Y-%m-%d"

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=[floor] * len(s), mode="lines",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", line=dict(color=color, width=2.2),
        fill="tonexty", fillcolor=fill, showlegend=False,
        hovertemplate=f"%{{x|{x_fmt}}}<br><b>%{{y:,.{dec}f}}</b><extra></extra>",
    ))
    fig.add_hline(y=base, line_dash="dash", line_width=1, line_color="rgba(255,255,255,0.35)",
                  annotation_text=f"{base_label} {base:,.{dec}f}",
                  annotation_position="bottom right",
                  annotation_font=dict(size=11, color="#94a3b8"))
    fig.update_layout(
        height=420, template="plotly_dark",
        margin=dict(t=10, b=30, l=10, r=10),
        yaxis=dict(range=[floor, float(s.max()) + pad], tickformat=f",.{dec}f"),
        hoverlabel=dict(font_size=13),
    )

    st.markdown(
        f"**{it['name']}** · {period} "
        f"<span style='color:{color}; font-weight:700;'>{chg:+.2f}%</span>"
        f"<span style='color:#64748b; font-size:0.85rem;'>  ({base_label} 대비)</span>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, width="stretch")


def show_indices():
    page_header("🌐", "지수 · 환율 · 시장지표",
                "코스피·코스닥 지수와 환율, 해외 증시, 금리·원자재 등 시장 전체의 흐름을 한 화면에서 확인합니다.")

    with st.expander("💡 지표 쉽게 이해하기", expanded=False):
        st.markdown(
            "- **코스피 / 코스닥**: 한국 증시 전체의 점수. 코스피는 대형주, 코스닥은 중소·기술주 중심입니다.\n"
            "- **원/달러 환율**: 오르면 원화 가치가 떨어진 것. 수출 기업엔 유리할 수 있지만, "
            "외국인 투자 자금이 빠져나가는 신호일 때도 있습니다.\n"
            "- **미국채 10년 금리**: 전 세계 금리의 기준. 오르면 성장주·기술주 주가에 부담이 됩니다.\n"
            "- **필라델피아 반도체**: 미국 반도체 지수. 삼성전자·SK하이닉스와 함께 움직이는 경향이 있습니다.\n"
            "- **VIX(공포지수)**: 시장의 불안 정도. 보통 20을 넘으면 불안, 낮을수록 안정된 상태로 봅니다.\n"
            "- **달러인덱스**: 주요 통화 대비 달러의 힘. 높을수록 달러 강세입니다."
        )

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("🔄 새로고침", key="idx_refresh"):
            cached_market_quotes.clear()
            cached_index_history.clear()

    with st.spinner("지수·환율 수집 중..."):
        quotes = cached_market_quotes()

    with c2:
        st.caption(f"기준: {now_kst().strftime('%Y-%m-%d %H:%M')} (한국 시간) · "
                   "현재 값은 1분마다 갱신됩니다.")

    if not quotes:
        st.error("지수·환율 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해 주세요.")
        return

    def _group_cards(group: str) -> None:
        items = [quotes[k] for k, it in ITEMS.items() if it["group"] == group and k in quotes]
        if items:
            chip(GROUPS[group])
            st.markdown(quote_cards_html(items), unsafe_allow_html=True)

    # ── 국내 지수 + 추이 차트 ─────────────────────────────────────────────────
    _group_cards("kr")

    chip("📈 추이 차트")
    chartable = [k for k, it in ITEMS.items() if it.get("yf")]
    k1, k2 = st.columns([2, 3])
    with k1:
        key = st.selectbox("지표 선택 (환율·해외 지수·원자재도 볼 수 있어요)", chartable,
                           format_func=lambda k: ITEMS[k]["name"], key="idx_chart_key")
    with k2:
        period = st.radio("기간", list(PERIODS), index=2, horizontal=True, key="idx_period")
    _plot_history(key, period, quotes.get(key))

    # ── 환율 · 해외 · 금리/원자재 ───────────────────────────────────────────────
    st.markdown("---")
    _group_cards("fx")
    _group_cards("world")
    _group_cards("rates")
    _group_cards("commod")

    st.caption("※ 현재 값: 네이버 증권 (환율은 하나은행 고시 기준, 일부 해외 지표는 10~15분 지연) · "
               "추이 차트: Yahoo Finance ('오늘' 국내 지수는 약 20분 지연)")
