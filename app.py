"""
주식 분석 웹 대시보드 (Streamlit) — 진입점
실행: streamlit run app.py

페이지 코드는 views/ 폴더에, 공통 헬퍼는 common.py에 있습니다.
"""

import streamlit as st

# ── 페이지 설정 ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="주식 분석 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

import common
from common import inject_css, market_status_html, now_kst

inject_css()

# ── 페이지 등록 ───────────────────────────────────────────────────────────────

from views.market import show_market
from views.sectors import show_sector
from views.market_sentiment import show_sentiment
from views.stock import show_analyzer
from views.company import show_fundamental
from views.investors import show_ownership
from views.advanced import show_advanced_analysis
from views.backtest import show_backtest
from views.strategy_compare import show_compare
from views.ma_optimizer import show_optimizer
from views.watchlist_scanner import show_scanner
from views.dart import show_dart_screener
from views.buy_timing import show_signal_monitor
from views.portfolio import show_virtual_portfolio

PAGES = {
    "market":    st.Page(show_market,            title="시장 현황",     icon="🏠", url_path="market", default=True),
    "sectors":   st.Page(show_sector,            title="섹터 / 테마",   icon="🗂️", url_path="sectors"),
    "sentiment": st.Page(show_sentiment,         title="시장 감성",     icon="🧠", url_path="sentiment"),
    "stock":     st.Page(show_analyzer,          title="종목 분석",     icon="📈", url_path="stock"),
    "company":   st.Page(show_fundamental,       title="기업 분석",     icon="🏢", url_path="company"),
    "investors": st.Page(show_ownership,         title="투자자 동향",   icon="👥", url_path="investors"),
    "advanced":  st.Page(show_advanced_analysis, title="심화 분석",     icon="🔬", url_path="advanced"),
    "backtest":  st.Page(show_backtest,          title="백테스팅",      icon="🔄", url_path="backtest"),
    "compare":   st.Page(show_compare,           title="전략 비교",     icon="⚖️", url_path="compare"),
    "optimizer": st.Page(show_optimizer,         title="MA 최적화",     icon="🔍", url_path="optimizer"),
    "scanner":   st.Page(show_scanner,           title="종목 스캐너",   icon="📡", url_path="scanner"),
    "dart":      st.Page(show_dart_screener,     title="DART 스크리너", icon="📊", url_path="dart"),
    "timing":    st.Page(show_signal_monitor,    title="매수 타이밍",   icon="📌", url_path="timing"),
    "portfolio": st.Page(show_virtual_portfolio, title="가상 투자",     icon="💰", url_path="portfolio"),
}

# 페이지 간 이동(goto_stock)용 레지스트리
common.NAV = PAGES

nav = st.navigation(
    {
        "시장":       [PAGES["market"], PAGES["sectors"], PAGES["sentiment"]],
        "종목":       [PAGES["stock"], PAGES["company"], PAGES["investors"], PAGES["advanced"]],
        "전략":       [PAGES["backtest"], PAGES["compare"], PAGES["optimizer"]],
        "스크리닝":   [PAGES["scanner"], PAGES["dart"], PAGES["timing"]],
        "포트폴리오": [PAGES["portfolio"]],
    },
    expanded=True,
)

# ── 사이드바 공통 정보 ────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("**시장 상태**")
    st.markdown(market_status_html(), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.72rem; color:#4a5568; line-height:1.7;">
        📊 데이터 출처<br>
        · 네이버증권<br>
        · yfinance<br>
        · pykrx (한국거래소)<br>
        · Open DART (금융감독원)<br>
        · 네이버 데이터랩
    </div>
    """, unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:0.72rem; color:#4a5568; margin-top:8px;">
        🕐 {now_kst().strftime('%Y-%m-%d %H:%M')} KST
    </div>
    """, unsafe_allow_html=True)

nav.run()
