"""페이지: 기업 분석 — 재무제표 + 밸류에이션 + 뉴스."""

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


def show_fundamental():
    page_header("🏢", "기업 기본 분석",
                "재무제표(매출·영업이익·순이익·EPS), 주요 밸류에이션 지표(PER·PBR·ROE)를 조회합니다.")

    c1, c2 = st.columns([5, 3])
    with c1:
        ticker, is_kr = stock_picker("fund", default_code="005930")
    with c2:
        years = st.slider("조회 기간 (년)", 1, 5, 4, key="fund_years")

    if not ticker.strip():
        return

    with st.spinner(f"[{ticker}] 기업 정보 수집 중..."):
        d = cached_fundamental(ticker.strip(), is_kr, years)

    if d is None:
        st.error("데이터를 가져오지 못했습니다. 종목 코드를 확인하세요.")
        return

    info = d["info"]
    name = info.get("longName") or info.get("shortName") or d["symbol"]
    sector_str   = info.get("sector", "")
    industry_str = info.get("industry", "")
    sub_parts = [f'<code style="background:#0e1117; padding:2px 8px; border-radius:4px;">{d["symbol"]}</code>']
    if sector_str:   sub_parts.append(sector_str)
    if industry_str: sub_parts.append(industry_str)
    sub_html = "&nbsp;&nbsp;".join(sub_parts)

    st.markdown(
        f'<div style="background:#1a2035; border-radius:12px; padding:16px 20px; margin-bottom:16px; border-left:4px solid #3b82f6;">'
        f'<div style="font-size:1.3rem; font-weight:700; color:#e2e8f0;">{name}</div>'
        f'<div style="font-size:0.82rem; color:#718096; margin-top:4px;">{sub_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # yfinance 버전에 따라 필드명이 다를 수 있어 여러 키 시도
    cur_price = (info.get("currentPrice")
                 or info.get("regularMarketPrice")
                 or info.get("previousClose"))
    # history에서도 가져오기 (최후 fallback)
    if not cur_price:
        try:
            _h = d.get("history")
            if _h is not None and not _h.empty:
                cur_price = float(_h["Close"].iloc[-1])
        except Exception:
            pass
    mkt_cap   = info.get("marketCap")
    per  = info.get("trailingPE") or info.get("forwardPE")
    pbr  = info.get("priceToBook")
    roe  = info.get("returnOnEquity")
    de   = info.get("debtToEquity")
    div  = info.get("dividendYield")
    eps  = info.get("trailingEps")
    beta = info.get("beta")

    chip("주요 지표")
    c1, c2, c3, c4 = st.columns(4)
    if cur_price: c1.metric("💰 현재가",    f"{cur_price:,.2f}")
    if mkt_cap:   c2.metric("🏦 시가총액",  fmt_market_cap(mkt_cap))
    if per  is not None: c3.metric("📊 PER", f"{per:.2f}배")
    if pbr  is not None: c4.metric("📘 PBR", f"{pbr:.2f}배")

    c5, c6, c7, c8 = st.columns(4)
    if roe  is not None: c5.metric("💹 ROE",      f"{roe*100:.2f}%")
    if de   is not None: c6.metric("📐 부채비율",  f"{de:.2f}%")
    if div  is not None: c7.metric("💸 배당수익률", f"{div*100:.2f}%")
    if beta is not None: c8.metric("🎢 Beta",      f"{beta:.3f}")

    st.markdown("---")

    from fundamental import plot as _plot_fund
    fig = _plot_fund(d, show=False)
    st.plotly_chart(fig, width="stretch")

    # 회사 설명
    summary = info.get("longBusinessSummary")
    if summary:
        with st.expander("📝 기업 소개", expanded=False):
            st.write(summary)

    # ── 뉴스 피드 ──────────────────────────────────────────────────────────────
    st.markdown("---")
    chip("📰 관련 뉴스 & 감성 분석")
    _render_news(ticker.strip(), corp_name=name, is_kr=is_kr)
