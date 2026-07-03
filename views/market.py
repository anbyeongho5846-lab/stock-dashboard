"""페이지: 시장 현황 — 네이버 등락률/거래량 순위."""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from common import (
    page_header, chip, detect_market, now_kst,
    fmt_market_cap, fmt_volume,
    _color_change, _color_opinion, _color_result, _color_excess, _color_pnl,
    cached_rankings, cached_sector, cached_stock, cached_fundamental,
    cached_ownership, cached_price_kr, cached_sector_detail, cached_scan,
    cached_news, _render_news,
    stock_picker, goto_stock,
)


def show_market():
    page_header("🏠", "시장 현황",
                "실시간 등락률 상위·하위 종목과 거래량 순위를 확인합니다.")

    col1, col2, col3 = st.columns([2, 2, 6])
    with col1:
        market = st.selectbox("시장 선택", ["KOSPI", "KOSDAQ"], key="mkt_market")
    with col2:
        top_n = st.slider("표시 종목 수", 5, 30, 20, key="mkt_top")
    with col3:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 데이터 갱신", key="mkt_refresh", use_container_width=False):
            cached_rankings.clear()

    with st.spinner(f"{market} 순위 데이터 수집 중..."):
        data = cached_rankings(market)

    if not data or all(v.empty for v in data.values()):
        st.error("데이터를 가져올 수 없습니다. 잠시 후 다시 시도해 주세요.")
        return

    # 요약 메트릭
    rise = data.get("rise", pd.DataFrame())
    fall = data.get("fall", pd.DataFrame())
    vol  = data.get("volume", pd.DataFrame())

    m1, m2, m3, m4 = st.columns(4)
    if not rise.empty:
        best = rise.iloc[0]
        name = str(best.get("종목명", "-"))
        chg  = best.get("등락률", 0)
        m1.metric("🔴 상승 1위", name, f"{chg:+.2f}%" if chg else None)
    if not fall.empty:
        worst = fall.iloc[0]
        name  = str(worst.get("종목명", "-"))
        chg   = worst.get("등락률", 0)
        m2.metric("🔵 하락 1위", name, f"{chg:+.2f}%" if chg else None)
    if not vol.empty:
        top_v = vol.iloc[0]
        m3.metric("📊 거래량 1위", str(top_v.get("종목명", "-")),
                  fmt_volume(top_v.get("거래량", 0)))
    if not rise.empty and not fall.empty:
        n_rise = len(rise[rise.get("등락률", pd.Series(dtype=float)) > 0])
        n_fall = len(fall[fall.get("등락률", pd.Series(dtype=float)) < 0])
        m4.metric("시장 분위기",
                  "상승 우세 📈" if n_rise >= n_fall else "하락 우세 📉")

    st.markdown("---")

    from ranking import plot_dashboard as _plot_ranking
    fig = _plot_ranking(data, market, top_n, show=False)
    st.plotly_chart(fig, use_container_width=True)
