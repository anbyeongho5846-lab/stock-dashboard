"""페이지: 종목 분석 — 캔들차트 + 기술지표 + 뉴스."""

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


def show_analyzer():
    page_header("📈", "종목 분석",
                "캔들차트와 이동평균선(MA5·20·60·120), RSI, MACD, 볼린저밴드, 거래량을 한눈에 확인합니다.")

    col1, col2 = st.columns([5, 5])
    with col1:
        ticker, is_kr = stock_picker("anal", default_code="005930")
    with col2:
        days = st.slider("조회 기간 (일)", 30, 730, 180, key="anal_days")

    if not ticker.strip():
        st.info("종목 코드를 입력하세요.")
        return

    with st.spinner(f"[{ticker.upper()}] 데이터 수집 중..."):
        df = cached_stock(ticker.strip().upper(), is_kr, days)

    if df.empty:
        st.error("데이터를 가져오지 못했습니다. 종목 코드를 확인하세요.")
        return

    last   = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else last
    change = ((last["Close"] - prev["Close"]) / prev["Close"] * 100
              if prev["Close"] != 0 else 0)
    chg_color = "#34d399" if change >= 0 else "#f87171"

    # 지표 메트릭
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("현재가",    f"{last['Close']:,.0f}", f"{change:+.2f}%")
    rsi_val  = last.get('RSI', float('nan'))
    rsi_warn = ("⚠️ 과매수" if rsi_val > 70 else "⚠️ 과매도" if rsi_val < 30 else "✅ 정상") if pd.notna(rsi_val) else "-"
    c2.metric("RSI (14)", f"{rsi_val:.1f}" if pd.notna(rsi_val) else "-", rsi_warn)
    c3.metric("MA 5",  f"{last.get('MA5',  0):,.0f}" if pd.notna(last.get('MA5'))  else "-")
    c4.metric("MA 20", f"{last.get('MA20', 0):,.0f}" if pd.notna(last.get('MA20')) else "-")
    c5.metric("MA 60", f"{last.get('MA60', 0):,.0f}" if pd.notna(last.get('MA60')) else "-")

    st.markdown("---")

    from analyzer import plot as _plot_chart
    title = f"{ticker.upper()} ({'KRX' if is_kr else 'US'})"
    fig = _plot_chart(df, title, show=False)
    st.plotly_chart(fig, width="stretch")

    # 최근 5일 가격 테이블
    with st.expander("📋 최근 거래 데이터 (5일)", expanded=False):
        tail5 = df.tail(5).copy()
        disp = tail5[["Open", "High", "Low", "Close", "Volume"]].copy()
        disp.index = disp.index.strftime("%Y-%m-%d")
        disp.columns = ["시가", "고가", "저가", "종가", "거래량"]
        for col in ["시가", "고가", "저가", "종가"]:
            disp[col] = disp[col].apply(lambda v: f"{v:,.0f}")
        disp["거래량"] = disp["거래량"].apply(fmt_volume)
        st.dataframe(disp, width="stretch")

    # ── 뉴스 피드 ──────────────────────────────────────────────────────────────
    st.markdown("---")
    chip("📰 관련 뉴스 & 감성 분석")
    _render_news(ticker.strip().upper(), corp_name="", is_kr=is_kr)
