"""페이지: 지수 · 환율 — 코스피·코스닥, 환율, 해외 지수, 금리·원자재·심리 지표."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import (
    page_header, chip, now_kst,
    cached_market_quotes, cached_index_history, cached_recent_history,
    quote_card_html, fmt_quote_value,
    UP_COLOR, DOWN_COLOR,
)
from market_index import ITEMS, GROUPS, PERIODS

_FLOW_DAYS = 180

# 카드 전체를 클릭 영역으로: 카드 위에 투명 버튼을 겹치고, 마우스를 올리면 살짝 떠오름
_CLICK_CSS = """
<style>
[class*="st-key-qcard_"] { position: relative; }
[class*="st-key-qcard_"] .qcard { min-height: 132px; }
[class*="st-key-qbtn_"] {
    position: absolute !important; inset: 0; z-index: 3;
    width: 100% !important; height: 100% !important;
}
[class*="st-key-qbtn_"] div, [class*="st-key-qbtn_"] button {
    width: 100% !important; height: 100% !important;
}
[class*="st-key-qbtn_"] button { opacity: 0 !important; cursor: pointer !important; }
[class*="st-key-qcard_"]:hover .qcard {
    transform: translateY(-2px);
    box-shadow: 0 0 0 1px #3b82f6, 0 6px 18px rgba(59,130,246,0.35) !important;
}
@media (max-width: 640px) {   /* 휴대폰: 카드가 한 줄씩 쌓일 때 간격 */
    [class*="st-key-qcard_"] { margin-bottom: 8px; }
}
</style>
"""

# 180일 흐름 창 아래에 보여줄 한 줄 도움말 (초보자용)
_TIPS = {
    "KOSPI":  "한국 대형주 중심의 대표 지수예요.",
    "KOSDAQ": "중소·기술·바이오주 중심 지수라 코스피보다 변동이 큰 편이에요.",
    "KPI200": "코스피 상위 200개 종목으로 만든 지수로, 선물·ETF의 기준이 돼요.",
    "USDKRW": "오르면 원화 약세(달러 강세). 수출주엔 유리할 수 있지만 외국인 자금 이탈 신호일 때도 있어요.",
    "JPYKRW": "100엔당 원화 가격. 일본 여행 경비, 일본과 경쟁하는 수출 기업과 관련이 있어요.",
    "EURKRW": "1유로당 원화 가격. 유럽 경기와 달러 흐름의 영향을 함께 받아요.",
    "CNYKRW": "1위안당 원화 가격. 중국은 최대 교역국이라 수출 기업에 영향을 줘요.",
    "DJI":    "미국 대표 우량주 30개 지수. 미국 증시 흐름은 다음 날 한국 증시에 영향을 주는 경우가 많아요.",
    "SPX":    "미국 대형주 500개 지수로, 미국 증시 전체를 가장 잘 보여 줘요.",
    "IXIC":   "기술주 중심 지수. 국내 IT·성장주와 함께 움직이는 경향이 있어요.",
    "SOX":    "미국 반도체 지수. 삼성전자·SK하이닉스 등 국내 반도체주와 함께 움직이는 경향이 있어요.",
    "US10Y":  "전 세계 금리의 기준. 오르면 성장주·기술주 주가에 부담이 되는 경향이 있어요.",
    "KR3Y":   "한국 기준금리 전망을 잘 반영하는 금리예요.",
    "DXY":    "주요 통화 대비 달러의 힘. 보통 원/달러 환율과 같은 방향으로 움직여요.",
    "WTI":    "국제 유가. 오르면 물가와 항공·화학 업종에 영향을 줘요.",
    "GOLD":   "대표적인 안전자산. 시장이 불안할 때 오르는 경향이 있어요.",
    "VIX":    "시장의 불안 정도. 20을 넘으면 불안, 낮을수록 안정된 상태로 봐요.",
}


def _stat_box(label: str, value: str, sub: str = "", color: str = "#f0f4f8") -> str:
    sub_html = f'<div style="color:#64748b; font-size:0.75rem;">{sub}</div>' if sub else ""
    return (f'<div style="background:#1a2035; border:1px solid rgba(255,255,255,0.07);'
            f' border-radius:10px; padding:10px 14px;">'
            f'<div style="color:#94a3b8; font-size:0.78rem; font-weight:600;">{label}</div>'
            f'<div style="color:{color}; font-size:1.2rem; font-weight:700;">{value}</div>{sub_html}</div>')


def _render_flow(key: str, quote: dict | None) -> None:
    it = ITEMS[key]
    dec, unit = it.get("dec", 2), it.get("unit", "")
    with st.spinner("흐름 데이터를 불러오는 중..."):
        s = cached_recent_history(key, _FLOW_DAYS).copy()

    # 마지막 점을 카드의 현재 값으로 맞춤 (24시간 시장은 일별 시세가 어제까지라 오늘 값을 덧붙임)
    if quote and quote.get("time"):
        try:
            qd = pd.Timestamp(str(quote["time"])[:10])
            if s.empty or qd >= s.index[-1]:
                s.loc[qd] = quote["price"]
                s = s.sort_index()
        except Exception:
            pass

    if len(s) < 2:
        st.info("흐름 데이터를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    first, last = float(s.iloc[0]), float(s.iloc[-1])
    hi_d, lo_d = s.idxmax(), s.idxmin()
    hi, lo = float(s.max()), float(s.min())
    color = UP_COLOR if last >= first else DOWN_COLOR
    fill = "rgba(239,68,68,0.12)" if last >= first else "rgba(59,130,246,0.12)"
    # 금리처럼 단위가 %인 지표는 %p(차이), 나머지는 변동률
    change = (f"{last - first:+.{dec}f}%p" if unit == "%"
              else f"{(last / first - 1) * 100:+.2f}%")

    stats = [
        _stat_box("현재", fmt_quote_value(last, dec, unit), s.index[-1].strftime("%Y-%m-%d")),
        _stat_box(f"{_FLOW_DAYS}일 전 대비", change,
                  f"{fmt_quote_value(first, dec, unit)}에서", color),
        _stat_box("기간 최고", fmt_quote_value(hi, dec, unit), hi_d.strftime("%Y-%m-%d"), UP_COLOR),
        _stat_box("기간 최저", fmt_quote_value(lo, dec, unit), lo_d.strftime("%Y-%m-%d"), DOWN_COLOR),
    ]
    st.markdown('<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));'
                f' gap:10px; margin-bottom:6px;">{"".join(stats)}</div>', unsafe_allow_html=True)

    pad = (hi - lo) * 0.12 or abs(lo) * 0.01
    floor = lo - pad
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=[floor] * len(s), mode="lines",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", line=dict(color=color, width=2.2),
        fill="tonexty", fillcolor=fill, showlegend=False,
        hovertemplate=f"%{{x|%Y-%m-%d}}<br><b>%{{y:,.{dec}f}}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[hi_d, lo_d], y=[hi, lo], mode="markers+text",
        marker=dict(size=9, color=[UP_COLOR, DOWN_COLOR], line=dict(width=1.5, color="#0e1117")),
        text=[f"최고 {fmt_quote_value(hi, dec, unit)}", f"최저 {fmt_quote_value(lo, dec, unit)}"],
        textposition=["top center", "bottom center"], textfont=dict(size=12, color="#e2e8f0"),
        hoverinfo="skip", showlegend=False, cliponaxis=False,
    ))
    fig.add_hline(y=first, line_dash="dash", line_width=1, line_color="rgba(255,255,255,0.35)",
                  annotation_text=f"{_FLOW_DAYS}일 전 {fmt_quote_value(first, dec, unit)}",
                  annotation_position="bottom right", annotation_font=dict(size=11, color="#94a3b8"))
    if key == "VIX":
        fig.add_hline(y=20, line_dash="dot", line_width=1.2, line_color="#fbbf24",
                      annotation_text="불안 기준 20", annotation_position="top left",
                      annotation_font=dict(size=11, color="#fbbf24"))
    top = max(hi, 20 if key == "VIX" else hi) + pad
    fig.update_layout(
        height=380, template="plotly_dark",
        margin=dict(t=24, b=24, l=10, r=10),
        yaxis=dict(range=[floor, top], tickformat=f",.{dec}f"),
        hoverlabel=dict(font_size=13),
    )
    st.plotly_chart(fig, width="stretch")

    tip = _TIPS.get(key)
    if tip:
        st.markdown(f"💡 {tip}")
    st.caption(f"출처: 네이버 증권 일별 시세 · 최근 {_FLOW_DAYS}일 · 마지막 점은 카드의 현재 값입니다.")


def _open_flow_dialog(key: str, quote: dict | None) -> None:
    @st.dialog(f"{ITEMS[key]['name']} · 최근 {_FLOW_DAYS}일 흐름", width="large")
    def _dialog():
        _render_flow(key, quote)
    _dialog()


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

    st.markdown(_CLICK_CSS, unsafe_allow_html=True)
    clicked = []

    def _group_cards(group: str) -> None:
        keys = [k for k, it in ITEMS.items() if it["group"] == group and k in quotes]
        if not keys:
            return
        chip(GROUPS[group])
        for col, k in zip(st.columns(len(keys)), keys):
            with col, st.container(key=f"qcard_{k}"):
                st.markdown(quote_card_html(quotes[k], hint=f"📈 {_FLOW_DAYS}일"),
                            unsafe_allow_html=True)
                # 카드 전체를 덮는 투명 버튼 (CSS) → 카드 아무 곳이나 클릭하면 열림
                if st.button(f"{quotes[k]['name']} {_FLOW_DAYS}일 흐름 보기", key=f"qbtn_{k}"):
                    clicked.append(k)
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    st.caption(f"💡 카드를 누르면 최근 {_FLOW_DAYS}일 흐름을 볼 수 있어요.")

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

    st.caption("※ 현재 값·180일 흐름: 네이버 증권 (환율은 하나은행 고시 기준, 일부 해외 지표는 10~15분 지연) · "
               "추이 차트: Yahoo Finance ('오늘' 국내 지수는 약 20분 지연)")

    if clicked:
        _open_flow_dialog(clicked[0], quotes.get(clicked[0]))
