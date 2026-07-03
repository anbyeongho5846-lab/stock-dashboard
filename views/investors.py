"""페이지: 투자자 동향 — 외국인/기관 순매수 추적 (국내 전용)."""

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


def show_ownership():
    page_header("👥", "외국인 / 기관 매매 동향",
                "외국인·기관의 일별 순매수량과 누적 추이, 외인 보유비율 변화를 추적합니다.")
    st.info("ℹ️ 국내(KRX) 종목만 지원합니다. (네이버증권 데이터)")

    c1, c2 = st.columns([2, 2])
    with c1:
        ticker, _ = stock_picker("own", default_code="005930",
                                 label="종목 선택 (국내)", kr_only=True)
    with c2:
        days = st.slider("주가 조회 기간 (일)", 30, 180, 60, key="own_days")

    if not ticker.strip():
        return

    name = ticker.strip()
    try:
        from ownership import get_name
        name = get_name(ticker.strip())
    except Exception:
        pass

    st.markdown(f"**{name}** `{ticker.strip()}`")

    with st.spinner(f"[{ticker}] 투자자 동향 수집 중..."):
        inv   = cached_ownership(ticker.strip())
        price = cached_price_kr(ticker.strip(), days)

    if inv.empty:
        st.error("투자자 매매 데이터를 가져오지 못했습니다. 종목 코드를 확인하세요.")
        return

    cutoff       = datetime.today() - timedelta(days=days)
    inv_filtered = inv[inv.index >= pd.Timestamp(cutoff)]

    chip("투자자별 매매 동향")

    # 외국인 지표
    if "외국인_순매수" in inv_filtered.columns and not inv_filtered.empty:
        fg_total = inv_filtered["외국인_순매수"].sum()
        fg_buy   = int((inv_filtered["외국인_순매수"] > 0).sum())
        fg_sell  = int((inv_filtered["외국인_순매수"] < 0).sum())
        fg_label = "🟢 매수우위" if fg_total > 0 else "🔴 매도우위"
        c1, c2, c3 = st.columns(3)
        c1.metric("🌏 외국인 누적 순매수", f"{fg_total:+,.0f}주", fg_label)
        c2.metric("📈 외국인 매수일", f"{fg_buy}일")
        c3.metric("📉 외국인 매도일", f"{fg_sell}일")

    # 기관 지표
    if "기관_순매수" in inv_filtered.columns and not inv_filtered.empty:
        in_total = inv_filtered["기관_순매수"].sum()
        in_buy   = int((inv_filtered["기관_순매수"] > 0).sum())
        in_sell  = int((inv_filtered["기관_순매수"] < 0).sum())
        in_label = "🟢 매수우위" if in_total > 0 else "🔴 매도우위"
        c4, c5, c6 = st.columns(3)
        c4.metric("🏛️ 기관 누적 순매수", f"{in_total:+,.0f}주", in_label)
        c5.metric("📈 기관 매수일", f"{in_buy}일")
        c6.metric("📉 기관 매도일", f"{in_sell}일")

    # 외인 보유비율
    if "외인보유비율" in inv.columns:
        ratio = inv["외인보유비율"].dropna()
        if not ratio.empty:
            col1, _ = st.columns([1, 3])
            col1.metric("🌐 외인보유비율 (현재)",
                        f"{ratio.iloc[-1]:.2f}%",
                        f"최고 {ratio.max():.2f}% / 최저 {ratio.min():.2f}%")

    st.markdown("---")

    from ownership import plot as _plot_own
    fig = _plot_own(price, inv_filtered, ticker.strip(), name, show=False)
    st.plotly_chart(fig, use_container_width=True)
