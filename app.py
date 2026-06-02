"""
주식 분석 웹 대시보드 (Streamlit)
실행: streamlit run app.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ── 페이지 설정 ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="주식 분석 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── 폰트 & 기본 색상 ── */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

/* ── 메인 배경 ── */
.stApp { background-color: #0e1117; }

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111827 0%, #1a2035 100%);
    border-right: 1px solid rgba(255,255,255,0.08);
}
section[data-testid="stSidebar"] .stRadio > label { color: #a0aec0 !important; }

/* ── 페이지 헤더 ── */
.page-header {
    padding: 16px 0 8px 0;
    margin-bottom: 20px;
    border-bottom: 2px solid #3b82f6;
}
.page-header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f0f4f8;
    margin: 0 0 4px 0;
}
.page-header p {
    font-size: 0.82rem;
    color: #718096;
    margin: 0;
}

/* ── 메트릭 카드 ── */
[data-testid="stMetric"] {
    background: #1a2035;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 14px 18px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
[data-testid="stMetricLabel"]  { color: #718096 !important; font-size: 0.78rem !important; }
[data-testid="stMetricValue"]  { color: #e2e8f0 !important; font-size: 1.35rem !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"] svg { display: none; }

/* ── 버튼 ── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    color: white !important;
    border: none !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
    box-shadow: 0 4px 15px rgba(37,99,235,0.4) !important;
    transform: translateY(-1px) !important;
}

/* ── 입력 필드 ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: #1e2535 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.2) !important;
}

/* ── 셀렉트박스 ── */
.stSelectbox > div > div {
    background: #1e2535 !important;
    border-color: rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}

/* ── 슬라이더 ── */
.stSlider > div > div > div > div { background: #3b82f6 !important; }

/* ── 익스팬더 ── */
.stExpander {
    background: #141b2d !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
}
.stExpander > details > summary { font-weight: 600 !important; }

/* ── 데이터프레임 ── */
.stDataFrame { border-radius: 10px !important; overflow: hidden; }
.stDataFrame thead th {
    background: #1a2035 !important;
    color: #94a3b8 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.stDataFrame tbody tr:hover { background: rgba(59,130,246,0.08) !important; }

/* ── 스피너 ── */
.stSpinner > div { border-top-color: #3b82f6 !important; }

/* ── 구분선 ── */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── 알림 박스 ── */
.stAlert { border-radius: 10px !important; }

/* ── 섹션 구분 칩 ── */
.section-chip {
    display: inline-block;
    background: rgba(59,130,246,0.15);
    color: #60a5fa;
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 10px;
}

/* ── 상태 배지 ── */
.badge-open  { color: #34d399; font-weight: 700; }
.badge-close { color: #f87171; font-weight: 700; }
.badge-pre   { color: #fbbf24; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ── 유틸리티 함수 ─────────────────────────────────────────────────────────────

def page_header(icon: str, title: str, desc: str = "") -> None:
    """섹션 헤더 렌더링."""
    desc_html = f"<p>{desc}</p>" if desc else ""
    st.markdown(f"""
    <div class="page-header">
        <h1>{icon} {title}</h1>
        {desc_html}
    </div>
    """, unsafe_allow_html=True)


def chip(label: str) -> None:
    st.markdown(f'<span class="section-chip">{label}</span>', unsafe_allow_html=True)


def detect_market(ticker: str) -> bool:
    """6자리 숫자면 국내(KRX), 아니면 미국(US). True=국내."""
    t = ticker.strip()
    return t.isdigit() and len(t) <= 6


def market_status_html() -> str:
    """KRX / US 시장 개장 여부 HTML 반환 (UTC+9 기준)."""
    now_kst = datetime.utcnow() + timedelta(hours=9)
    now_est = datetime.utcnow() - timedelta(hours=4)   # EDT (서머타임 기준)

    wd_kst = now_kst.weekday()   # 0=Mon … 6=Sun
    wd_est = now_est.weekday()

    # KRX: 평일 09:00~15:30 KST
    krx_open = (wd_kst < 5 and
                datetime(now_kst.year, now_kst.month, now_kst.day, 9, 0)
                <= now_kst <=
                datetime(now_kst.year, now_kst.month, now_kst.day, 15, 30))
    # NYSE: 평일 09:30~16:00 EDT
    us_open  = (wd_est < 5 and
                datetime(now_est.year, now_est.month, now_est.day, 9, 30)
                <= now_est <=
                datetime(now_est.year, now_est.month, now_est.day, 16, 0))

    krx_cls = "badge-open" if krx_open else "badge-close"
    krx_lbl = "장중 🟢" if krx_open else "장마감 🔴"
    us_cls  = "badge-open" if us_open  else "badge-close"
    us_lbl  = "장중 🟢" if us_open  else "장마감 🔴"

    return (f'<span class="{krx_cls}">KRX {krx_lbl}</span> &nbsp;'
            f'<span class="{us_cls}">NYSE {us_lbl}</span>')


# ── 숫자 포매터 ───────────────────────────────────────────────────────────────

def fmt_market_cap(v: float) -> str:
    if v >= 1e12: return f"{v/1e12:.2f} 조원"
    if v >= 1e8:  return f"{v/1e8:.0f} 억원"
    return f"{v:,.0f}"


def fmt_volume(v: float) -> str:
    if v >= 1e8: return f"{v/1e8:.1f}억"
    if v >= 1e4: return f"{v/1e4:.0f}만"
    return f"{v:,.0f}"


# ── DataFrame 색칠 헬퍼 ───────────────────────────────────────────────────────

def _color_change(val: str) -> str:
    """등락률 문자열(예: '+2.30%') 셀 색상."""
    try:
        v = float(str(val).replace("%", "").replace("+", "").replace(",", ""))
        if v > 0:  return "color: #34d399; font-weight:600"
        if v < 0:  return "color: #f87171; font-weight:600"
    except Exception:
        pass
    return "color: #94a3b8"


def _color_opinion(val: str) -> str:
    """의견 (강력매수/매수/중립/매도) 셀 색상."""
    s = str(val)
    if "강력매수" in s: return "color: #34d399; font-weight:700"
    if "매수"    in s: return "color: #6ee7b7; font-weight:600"
    if "매도"    in s: return "color: #f87171; font-weight:600"
    return "color: #94a3b8"


def _color_result(val: str) -> str:
    """WIN/LOSS 셀 색상."""
    s = str(val)
    if "WIN"  in s: return "color: #34d399; font-weight:700"
    if "LOSS" in s: return "color: #f87171; font-weight:700"
    return "color: #94a3b8"


def _color_excess(val: str) -> str:
    """초과수익 / 수익률 문자열 색상."""
    try:
        v = float(str(val).replace("%", "").replace("+", ""))
        if v > 0: return "color: #34d399; font-weight:600"
        if v < 0: return "color: #f87171; font-weight:600"
    except Exception:
        pass
    return "color: #94a3b8"


def _color_pnl(val: str) -> str:
    """손익 금액 문자열(예: '+1,234원', '-567원') 셀 색상."""
    try:
        v = float(str(val).replace("원", "").replace("+", "").replace(",", ""))
        if v > 0: return "color: #34d399; font-weight:600"
        if v < 0: return "color: #f87171; font-weight:600"
    except Exception:
        pass
    return "color: #94a3b8"


# ── 공통 캐싱 함수 ────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)   # 30분 캐시 — 네이버 요청 빈도 최소화
def cached_rankings(market: str):
    from ranking import fetch_rankings
    try:
        return fetch_rankings(market)
    except Exception:
        return {}


@st.cache_data(ttl=1800)   # 30분 캐시
def cached_sector(type_: str):
    from sector import fetch_sector
    try:
        return fetch_sector(type_)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_stock(ticker: str, is_kr: bool, days: int) -> pd.DataFrame:
    from analyzer import fetch_kr, fetch_us, add_indicators
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        df = fetch_kr(ticker, start, end) if is_kr else fetch_us(ticker, start, end)
        return add_indicators(df) if not df.empty else df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_fundamental(ticker: str, is_kr: bool, years: int):
    from fundamental import fetch_all
    try:
        return fetch_all(ticker, is_kr, years)
    except Exception:
        return None


@st.cache_data(ttl=300)
def cached_ownership(ticker: str):
    from ownership import fetch_investor_trading
    try:
        return fetch_investor_trading(ticker)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_price_kr(ticker: str, days: int) -> pd.DataFrame:
    from ownership import fetch_price
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        return fetch_price(ticker, start, end)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def cached_sector_detail(type_: str, no: str) -> pd.DataFrame:
    from sector import fetch_sector_detail
    try:
        return fetch_sector_detail(type_, no)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def cached_scan(watchlist_str: str, days: int):
    from scanner import scan
    watchlist = []
    for line in watchlist_str.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if parts and parts[0]:
            ticker = parts[0].upper()
            market = parts[1].lower() if len(parts) > 1 else "us"
            watchlist.append((ticker, market))
    if not watchlist:
        return []
    return scan(watchlist, days)


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 16px 0 12px 0;">
        <div style="font-size:2.2rem;">📈</div>
        <div style="font-size:1.1rem; font-weight:700; color:#e2e8f0; margin-top:4px;">주식 분석</div>
        <div style="font-size:0.72rem; color:#4a5568; margin-top:2px;">Stock Dashboard</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    page = st.radio(
        "페이지",
        [
            "🏠 시장 현황",
            "📈 종목 분석",
            "🔄 백테스팅",
            "⚖️ 전략 비교",
            "🔍 MA 최적화",
            "🏢 기업 분석",
            "👥 투자자 동향",
            "🗂️ 섹터 / 테마",
            "📡 종목 스캐너",
            "📊 DART 스크리너",
            "💰 가상 투자",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # 시장 개장 상태
    st.markdown("**시장 상태**")
    st.markdown(market_status_html(), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.72rem; color:#4a5568; line-height:1.7;">
        📊 데이터 출처<br>
        · 네이버증권<br>
        · yfinance<br>
        · pykrx (한국거래소)<br>
        · Open DART (금융감독원)
    </div>
    """, unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:0.72rem; color:#4a5568; margin-top:8px;">
        🕐 {datetime.today().strftime('%Y-%m-%d %H:%M')}
    </div>
    """, unsafe_allow_html=True)


# ── 페이지: 시장 현황 ─────────────────────────────────────────────────────────

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


# ── 페이지: 종목 분석 ─────────────────────────────────────────────────────────

def show_analyzer():
    page_header("📈", "종목 분석",
                "캔들차트와 이동평균선(MA5·20·60·120), RSI, MACD, 볼린저밴드, 거래량을 한눈에 확인합니다.")

    col1, col2, col3 = st.columns([3, 3, 4])
    with col1:
        ticker = st.text_input("종목 코드", value="005930", key="anal_ticker",
                               help="국내: 005930  /  미국: AAPL (6자리 숫자 입력 시 국내 자동 인식)")
    with col2:
        is_kr_default = detect_market(st.session_state.get("anal_ticker", "005930"))
        market_sel = st.selectbox("시장", ["국내 (KRX)", "미국 (US)"], key="anal_market",
                                  index=0 if is_kr_default else 1)
    with col3:
        days = st.slider("조회 기간 (일)", 30, 730, 180, key="anal_days")

    is_kr = "KRX" in market_sel

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
    st.plotly_chart(fig, use_container_width=True)

    # 최근 5일 가격 테이블
    with st.expander("📋 최근 거래 데이터 (5일)", expanded=False):
        tail5 = df.tail(5).copy()
        disp = tail5[["Open", "High", "Low", "Close", "Volume"]].copy()
        disp.index = disp.index.strftime("%Y-%m-%d")
        disp.columns = ["시가", "고가", "저가", "종가", "거래량"]
        for col in ["시가", "고가", "저가", "종가"]:
            disp[col] = disp[col].apply(lambda v: f"{v:,.0f}")
        disp["거래량"] = disp["거래량"].apply(fmt_volume)
        st.dataframe(disp, use_container_width=True)


# ── 페이지: 백테스팅 ──────────────────────────────────────────────────────────

def show_backtest():
    page_header("🔄", "백테스팅",
                "이동평균 골든크로스/데드크로스 전략의 과거 성과를 시뮬레이션합니다.")

    with st.expander("⚙️ 백테스팅 설정", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker  = st.text_input("종목 코드", value="005930", key="bt_ticker")
            is_kr   = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="bt_kr")
        with c2:
            short   = st.number_input("단기 MA", min_value=2,  max_value=50,   value=5,   key="bt_short")
            long_   = st.number_input("장기 MA", min_value=10, max_value=200,  value=20,  key="bt_long")
        with c3:
            days    = st.number_input("조회 기간 (일)", min_value=90,  max_value=1825, value=365, key="bt_days")
            capital = st.number_input("초기 자본 (원)", min_value=1_000_000,
                                      value=10_000_000, step=1_000_000, key="bt_capital",
                                      format="%d")
        run_bt = st.button("▶ 백테스팅 실행", use_container_width=True, key="bt_run")

    if "bt_result" not in st.session_state:
        st.session_state.bt_result = None

    if run_bt:
        if int(short) >= int(long_):
            st.error("단기 MA는 장기 MA보다 작아야 합니다.")
            return
        with st.spinner("백테스팅 실행 중..."):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from backtester import run_backtest, plot_backtest
            bt_df, trades, metrics = run_backtest(df, int(short), int(long_), float(capital))
            title = f"{ticker.upper()} ({'KRX' if is_kr else 'US'})  MA{short}/MA{long_}"
            fig = plot_backtest(bt_df, trades, title, int(short), int(long_), show=False)
            st.session_state.bt_result = (trades, metrics, fig)

    if st.session_state.bt_result:
        trades, m, fig = st.session_state.bt_result
        excess = m["total_return"] - m["bh_return"]

        chip("성과 요약")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("📊 전략 수익률",   f"{m['total_return']:+.1f}%",
                  f"B&H 대비 {excess:+.1f}%")
        c2.metric("📈 Buy & Hold",    f"{m['bh_return']:+.1f}%")
        c3.metric("🎯 승률",          f"{m['win_rate']:.1f}%")
        c4.metric("⚡ 샤프 지수",     f"{m['sharpe']:.2f}")
        c5.metric("📉 최대낙폭(MDD)", f"{m['mdd']:.1f}%")
        c6.metric("🔁 총 거래 수",    f"{m['n_trades']}회")

        st.markdown("---")
        st.plotly_chart(fig, use_container_width=True)

        if trades:
            chip("거래 내역")
            rows = []
            for t in trades:
                rows.append({
                    "진입일":  str(t["entry_date"])[:10],
                    "청산일":  str(t["exit_date"])[:10],
                    "진입가":  f"{t['entry_price']:,.0f}",
                    "청산가":  f"{t['exit_price']:,.0f}",
                    "수익률":  f"{t['pnl_pct']:+.2f}%",
                    "결과":    "✅ WIN" if t["won"] else "❌ LOSS",
                    "미청산":  "⚠️" if t.get("open") else "",
                })
            trade_df = pd.DataFrame(rows)
            styled = (trade_df.style
                      .map(_color_result, subset=["결과"])
                      .map(_color_change, subset=["수익률"])
                      .set_properties(**{"text-align": "center"})
                      .hide(axis="index"))
            st.dataframe(styled, use_container_width=True)


# ── 페이지: 전략 비교 ─────────────────────────────────────────────────────────

def show_compare():
    page_header("⚖️", "전략 비교",
                "MA 골든크로스 · RSI 역추세 · MACD 세 가지 전략의 성과를 나란히 비교합니다.")

    with st.expander("⚙️ 설정", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ticker  = st.text_input("종목 코드", value="AAPL", key="cmp_ticker")
            is_kr   = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="cmp_kr")
        with c2:
            days    = st.slider("기간 (일)", 90, 730, 365, key="cmp_days")
            capital = st.number_input("초기 자본", 1_000_000,
                                      value=10_000_000, step=1_000_000, key="cmp_capital",
                                      format="%d")
        with c3:
            st.markdown("**MA 설정**")
            short    = st.number_input("단기 MA", 2,  50,  5,  key="cmp_short")
            long_    = st.number_input("장기 MA", 10, 200, 20, key="cmp_long")
        with c4:
            st.markdown("**RSI 설정**")
            rsi_buy  = st.number_input("매수 기준", 10, 50, 30, key="cmp_rsi_buy")
            rsi_sell = st.number_input("매도 기준", 50, 90, 70, key="cmp_rsi_sell")
        run_cmp = st.button("▶ 비교 실행", use_container_width=True, key="cmp_run")

    if "cmp_result" not in st.session_state:
        st.session_state.cmp_result = None

    if run_cmp:
        with st.spinner("세 가지 전략 비교 중..."):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from analyzer import add_indicators
            from backtester import run_backtest
            from compare import backtest_rsi, backtest_macd, plot_comparison

            df = add_indicators(df)
            df_ma,   _, m_ma   = run_backtest(df.copy(), int(short), int(long_),   float(capital))
            df_rsi,  _, m_rsi  = backtest_rsi(df.copy(), int(rsi_buy), int(rsi_sell), float(capital))
            df_macd, _, m_macd = backtest_macd(df.copy(), float(capital))

            strategies = {
                "MA":   {"df": df_ma,   "metrics": m_ma},
                "RSI":  {"df": df_rsi,  "metrics": m_rsi},
                "MACD": {"df": df_macd, "metrics": m_macd},
            }
            title = f"{ticker.upper()} ({'KRX' if is_kr else 'US'})"
            fig = plot_comparison(strategies, title, show=False)
            st.session_state.cmp_result = (strategies, fig)

    if st.session_state.cmp_result:
        strategies, fig = st.session_state.cmp_result
        bh = list(strategies.values())[0]["metrics"]["bh_return"]

        chip("전략 성과 비교")
        rows = []
        for name, data in strategies.items():
            m = data["metrics"]
            rows.append({
                "전략":     name,
                "수익률":   f"{m['total_return']:+.1f}%",
                "B&H 대비": f"{m['total_return']-bh:+.1f}%",
                "승률":     f"{m['win_rate']:.0f}%",
                "샤프":     f"{m['sharpe']:.2f}",
                "MDD":      f"{m['mdd']:.1f}%",
                "거래수":   f"{m['n_trades']}회",
            })
        tbl = pd.DataFrame(rows).set_index("전략")
        styled = (tbl.style
                  .map(_color_change, subset=["수익률", "B&H 대비"])
                  .set_properties(**{"text-align": "center"}))
        st.dataframe(styled, use_container_width=True)

        col1, _ = st.columns([1, 3])
        col1.metric("📊 Buy & Hold 기준선", f"{bh:+.1f}%")

        st.markdown("---")
        st.plotly_chart(fig, use_container_width=True)


# ── 페이지: MA 최적화 ─────────────────────────────────────────────────────────

def show_optimizer():
    page_header("🔍", "MA 파라미터 최적화",
                "다양한 단기·장기 이동평균 조합을 브루트포스로 탐색하여 최적 파라미터를 찾습니다.")

    with st.expander("⚙️ 설정", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ticker = st.text_input("종목 코드", value="005930", key="opt_ticker")
            is_kr  = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="opt_kr")
        with c2:
            days    = st.number_input("기간 (일)", 90, 1825, 365, key="opt_days")
            capital = st.number_input("초기 자본", 1_000_000, 100_000_000,
                                      10_000_000, step=1_000_000, key="opt_capital",
                                      format="%d")
        with c3:
            shorts_str = st.text_input("단기 MA 후보 (공백 구분)", "3 5 10 15 20", key="opt_shorts")
        with c4:
            longs_str  = st.text_input("장기 MA 후보 (공백 구분)", "20 30 60 120", key="opt_longs")
        run_opt = st.button("▶ 최적화 실행", use_container_width=True, key="opt_run")

    if "opt_result" not in st.session_state:
        st.session_state.opt_result = None

    if run_opt:
        try:
            shorts = [int(x) for x in shorts_str.split()]
            longs  = [int(x) for x in longs_str.split()]
        except ValueError:
            st.error("MA 기간은 숫자만 입력하세요 (예: 3 5 10 20).")
            return
        n_pairs = sum(1 for s in shorts for l in longs if s < l)
        with st.spinner(f"총 {n_pairs}개 조합 탐색 중... (수십 초 소요)"):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from optimizer import optimize, plot_results as _plot_opt
            results = optimize(df, shorts, longs, float(capital))
            fig = _plot_opt(results, ticker.strip().upper(), show=False)
            st.session_state.opt_result = (results, fig)

    if st.session_state.opt_result:
        results, fig = st.session_state.opt_result
        bh   = results["bh_return"].iloc[0]
        beat = int((results["excess"] > 0).sum())

        chip("최적화 결과")
        c1, c2, c3 = st.columns(3)
        c1.metric("📊 Buy & Hold",       f"{bh:+.1f}%")
        c2.metric("🏆 B&H 초과 달성 조합", f"{beat} / {len(results)}")
        c3.metric("🥇 최고 수익 조합",
                  results.iloc[0]["label"],
                  f"{results.iloc[0]['total_return']:+.1f}%")

        st.plotly_chart(fig, use_container_width=True)

        chip("전체 조합 결과")
        show_df = results[["label", "total_return", "excess",
                            "win_rate", "sharpe", "mdd", "n_trades"]].copy()
        show_df.columns = ["조합", "수익률(%)", "초과(%)", "승률(%)", "샤프", "MDD(%)", "거래수"]
        show_df["수익률(%)"] = show_df["수익률(%)"].apply(lambda v: f"{v:+.1f}%")
        show_df["초과(%)"]   = show_df["초과(%)"].apply(lambda v: f"{v:+.1f}%")
        show_df["MDD(%)"]    = show_df["MDD(%)"].apply(lambda v: f"{v:.1f}%")
        styled = (show_df.style
                  .map(_color_excess,  subset=["수익률(%)", "초과(%)"])
                  .set_properties(**{"text-align": "center"})
                  .hide(axis="index"))
        st.dataframe(styled, use_container_width=True)


# ── 페이지: 기업 분석 ─────────────────────────────────────────────────────────

def show_fundamental():
    page_header("🏢", "기업 기본 분석",
                "재무제표(매출·영업이익·순이익·EPS), 주요 밸류에이션 지표(PER·PBR·ROE)를 조회합니다.")

    c1, c2, c3 = st.columns([3, 2, 5])
    with c1:
        ticker = st.text_input("종목 코드", value="005930", key="fund_ticker",
                               help="국내: 005930 (6자리 숫자 자동 인식)  /  미국: AAPL")
    with c2:
        years = st.slider("조회 기간 (년)", 1, 5, 4, key="fund_years")
    with c3:
        st.info("💡 6자리 숫자 입력 시 국내 종목으로 자동 인식됩니다.")

    if not ticker.strip():
        return

    is_kr = detect_market(ticker.strip())

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
    st.plotly_chart(fig, use_container_width=True)

    # 회사 설명
    summary = info.get("longBusinessSummary")
    if summary:
        with st.expander("📝 기업 소개", expanded=False):
            st.write(summary)


# ── 페이지: 투자자 동향 ───────────────────────────────────────────────────────

def show_ownership():
    page_header("👥", "외국인 / 기관 매매 동향",
                "외국인·기관의 일별 순매수량과 누적 추이, 외인 보유비율 변화를 추적합니다.")
    st.info("ℹ️ 국내(KRX) 종목만 지원합니다. (네이버증권 데이터)")

    c1, c2 = st.columns([2, 2])
    with c1:
        ticker = st.text_input("종목 코드 (국내)", value="005930", key="own_ticker")
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


# ── 페이지: 섹터 / 테마 ───────────────────────────────────────────────────────

def show_sector():
    page_header("🗂️", "섹터 / 테마 현황",
                "네이버증권 업종별·테마별 등락률 현황을 히트맵과 바차트로 시각화합니다. "
                "업종/테마를 선택하면 소속 종목을 확인할 수 있습니다.")

    c1, c2, c3 = st.columns([2, 2, 6])
    with c1:
        type_label = st.selectbox("분류 선택", ["업종", "테마"], key="sec_type")
    with c2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 갱신", key="sec_refresh"):
            cached_sector.clear()
            cached_sector_detail.clear()

    type_code = "upjong" if type_label == "업종" else "theme"

    with st.spinner(f"{type_label} 데이터 수집 중..."):
        df = cached_sector(type_code)

    if df.empty:
        st.error("데이터를 가져오지 못했습니다.")
        return

    has_chg = "등락률" in df.columns and df["등락률"].notna().any()

    if has_chg:
        chg = df["등락률"].dropna()
        rising  = int((chg > 0).sum())
        falling = int((chg < 0).sum())
        flat    = len(df) - rising - falling
        avg_chg = float(chg.mean())

        chip("시장 요약")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"📋 전체 {type_label}", f"{len(df)}개")
        c2.metric("🔴 상승",  f"{rising}개",  f"{rising/len(df)*100:.0f}%")
        c3.metric("🔵 하락",  f"{falling}개", f"-{falling/len(df)*100:.0f}%")
        c4.metric("⬜ 보합",  f"{flat}개")
        c5.metric("📊 평균 등락률", f"{avg_chg:+.2f}%")

        if "상승수" in df.columns and "하락수" in df.columns:
            c6, c7, _, _ = st.columns(4)
            c6.metric("📈 종목 상승 합계", f"{int(df['상승수'].sum())}종목")
            c7.metric("📉 종목 하락 합계", f"{int(df['하락수'].sum())}종목")

    st.markdown("---")

    # ── 메인 차트 (클릭 이벤트 캡처) ────────────────────────────────────────────
    from sector import plot as _plot_sector
    fig = _plot_sector(df, type_label, show=False)

    chart_event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        key=f"sec_chart_{type_code}",
    )

    # 클릭한 섹터 이름 추출 (트리맵: label / 바차트: y)
    if chart_event and chart_event.selection and chart_event.selection.points:
        pt = chart_event.selection.points[0]
        clicked = pt.get("label") or pt.get("y")
        if clicked and isinstance(clicked, str) and len(clicked) > 1:
            st.session_state["sec_selected"] = clicked

    # ── 전체 데이터 테이블 ────────────────────────────────────────────────────────
    with st.expander(f"📋 전체 {type_label} 데이터 ({len(df)}개)", expanded=False):
        display_cols = [c for c in ["섹터명", "등락률", "종목수", "상승수", "하락수"]
                        if c in df.columns]
        show_df = df[display_cols].copy()
        if "등락률" in show_df.columns:
            show_df = show_df.sort_values("등락률", ascending=False).reset_index(drop=True)
        fmt_df = show_df.copy()
        if "등락률" in fmt_df.columns:
            fmt_df["등락률"] = fmt_df["등락률"].apply(
                lambda v: f"{v:+.2f}%" if pd.notna(v) else "-")
        styled = fmt_df.style
        if "등락률" in fmt_df.columns:
            styled = styled.map(_color_change, subset=["등락률"])
        styled = styled.hide(axis="index")
        st.dataframe(styled, use_container_width=True)

    # ── 드릴다운: 소속 종목 조회 ─────────────────────────────────────────────────
    st.markdown("---")
    chip(f"🔎 {type_label} 드릴다운 — 소속 종목 조회")

    has_no = "sector_no" in df.columns and df["sector_no"].notna().any()

    if not has_no:
        st.info("섹터 번호를 가져오지 못해 드릴다운을 사용할 수 없습니다.")
    else:
        # 등락률 순으로 정렬한 섹터 목록
        sorted_sectors = (df.dropna(subset=["등락률"])
                            .sort_values("등락률", ascending=False)["섹터명"]
                            .tolist())
        options = ["— 선택 안 함 —"] + sorted_sectors

        # 클릭으로 설정된 섹터를 기본 선택으로
        default_idx = 0
        pre = st.session_state.get("sec_selected", "")
        if pre in options:
            default_idx = options.index(pre)

        selected = st.selectbox(
            f"조회할 {type_label} 선택  (차트 셀을 클릭하면 자동 선택됩니다)",
            options,
            index=default_idx,
            key="sec_drill_select",
        )

        if selected and selected != "— 선택 안 함 —":
            row = df[df["섹터명"] == selected]
            if row.empty or pd.isna(row["sector_no"].iloc[0]):
                st.warning("해당 섹터의 번호를 찾을 수 없습니다.")
            else:
                no = str(row["sector_no"].iloc[0]).split(".")[0]  # float → str

                with st.spinner(f"[{selected}] 소속 종목 수집 중..."):
                    detail = cached_sector_detail(type_code, no)

                if detail.empty:
                    st.warning("소속 종목 데이터를 가져오지 못했습니다.")
                else:
                    # 섹터 요약 헤더
                    chg_val = float(row["등락률"].iloc[0]) if "등락률" in row.columns else 0.0
                    n_stock = int(row["종목수"].iloc[0]) if "종목수" in row.columns else len(detail)
                    hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns(4)
                    hdr_col1.metric(f"📂 {selected}", f"{n_stock}개 종목",
                                    f"{chg_val:+.2f}%")
                    if "등락률" in detail.columns and detail["등락률"].notna().any():
                        d_chg = detail["등락률"].dropna()
                        hdr_col2.metric("🔴 상승 종목",
                                        f"{int((d_chg > 0).sum())}개")
                        hdr_col3.metric("🔵 하락 종목",
                                        f"{int((d_chg < 0).sum())}개")
                        hdr_col4.metric("📊 평균 등락률",
                                        f"{float(d_chg.mean()):+.2f}%")

                    # 소속 종목 바차트
                    if "등락률" in detail.columns and detail["등락률"].notna().any():
                        name_col = "종목명" if "종목명" in detail.columns else detail.columns[0]
                        bar_d = (detail.dropna(subset=["등락률"])
                                       .sort_values("등락률", ascending=True))

                        bar_colors = ["#e63946" if v >= 0 else "#457b9d"
                                      for v in bar_d["등락률"]]
                        bar_texts  = [f"{v:+.2f}%" for v in bar_d["등락률"]]

                        import plotly.graph_objects as _go
                        fig2 = _go.Figure()
                        fig2.add_trace(_go.Bar(
                            x=bar_d["등락률"],
                            y=bar_d[name_col].astype(str),
                            orientation="h",
                            marker_color=bar_colors,
                            text=bar_texts,
                            textposition="outside",
                            textfont=dict(size=10, color="rgba(230,230,230,0.95)"),
                            cliponaxis=False,
                            hovertemplate="<b>%{y}</b><br>등락률: %{x:+.2f}%<extra></extra>",
                        ))
                        max_abs2 = float(bar_d["등락률"].abs().max()) if len(bar_d) > 0 else 1.0
                        fig2.update_layout(
                            height=max(360, len(bar_d) * 26 + 80),
                            template="plotly_dark",
                            title=dict(
                                text=f"{selected} — 소속 종목 등락률",
                                font=dict(size=15),
                            ),
                            margin=dict(l=10, r=90, t=50, b=30),
                            xaxis=dict(
                                title="등락률 (%)",
                                range=[-(max_abs2 * 1.5), max_abs2 * 1.5],
                            ),
                            showlegend=False,
                        )
                        st.plotly_chart(fig2, use_container_width=True)

                    # 소속 종목 테이블
                    chip("종목 상세 테이블")
                    disp_cols = [c for c in ["종목명", "현재가", "등락률", "거래량", "시가총액"]
                                 if c in detail.columns]
                    tbl = detail[disp_cols].copy()
                    if "등락률" in tbl.columns:
                        tbl = tbl.sort_values("등락률", ascending=False).reset_index(drop=True)
                    fmt_tbl = tbl.copy()
                    if "등락률"  in fmt_tbl.columns:
                        fmt_tbl["등락률"]  = fmt_tbl["등락률"].apply(
                            lambda v: f"{v:+.2f}%" if pd.notna(v) else "-")
                    if "현재가"  in fmt_tbl.columns:
                        fmt_tbl["현재가"]  = fmt_tbl["현재가"].apply(
                            lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
                    if "거래량"  in fmt_tbl.columns:
                        fmt_tbl["거래량"]  = fmt_tbl["거래량"].apply(
                            lambda v: fmt_volume(v) if pd.notna(v) else "-")
                    if "시가총액" in fmt_tbl.columns:
                        fmt_tbl["시가총액"] = fmt_tbl["시가총액"].apply(
                            lambda v: fmt_market_cap(v * 1e8) if pd.notna(v) else "-")

                    styled2 = fmt_tbl.style
                    if "등락률" in fmt_tbl.columns:
                        styled2 = styled2.map(_color_change, subset=["등락률"])
                    styled2 = styled2.hide(axis="index")
                    st.dataframe(styled2, use_container_width=True)


# ── 페이지: 종목 스캐너 ───────────────────────────────────────────────────────

_DEFAULT_WATCHLIST = """\
005930,kr   # 삼성전자
000660,kr   # SK하이닉스
035420,kr   # NAVER
035720,kr   # 카카오
207940,kr   # 삼성바이오로직스
AAPL,us
MSFT,us
NVDA,us
TSLA,us
AMZN,us"""


def show_scanner():
    page_header("📡", "종목 스캐너",
                "감시 목록의 종목을 일괄 분석하여 매수·매도 신호와 기술적 점수를 제공합니다.")

    with st.expander("📋 감시 목록 설정", expanded=True):
        watchlist_str = st.text_area(
            "종목 목록  (형식: 종목코드,시장  # 설명)",
            value=_DEFAULT_WATCHLIST,
            height=200,
            key="scn_watchlist",
            help="국내는 kr, 미국은 us. 줄 단위 입력.",
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            days = st.slider("데이터 기간 (일)", 60, 365, 120, key="scn_days")
        with c2:
            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
            run_scn = st.button("▶ 스캔 실행", use_container_width=True, key="scn_run")

    if "scn_result" not in st.session_state:
        st.session_state.scn_result = None

    if run_scn:
        n = sum(1 for l in watchlist_str.splitlines() if l.split("#")[0].strip())
        with st.spinner(f"{n}개 종목 스캔 중... (30초~1분 소요)"):
            results = cached_scan(watchlist_str, int(days))
        st.session_state.scn_result = results
        if not results:
            st.warning("분석 결과가 없습니다. 종목 코드와 인터넷 연결을 확인하세요.")

    if st.session_state.scn_result:
        results = st.session_state.scn_result
        if not results:
            return

        # 요약 통계
        total = len(results)
        n_buy  = sum(1 for r in results if "매수" in r.get("opinion", ""))
        n_sell = sum(1 for r in results if "매도" in r.get("opinion", ""))
        n_neut = total - n_buy - n_sell
        avg_score = sum(r.get("score", 0) for r in results) / total if total else 0

        chip("스캔 요약")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 종목 수",    f"{total}개")
        c2.metric("🟢 매수 신호", f"{n_buy}개",  f"{n_buy/total*100:.0f}%")
        c3.metric("🔴 매도 신호", f"{n_sell}개", f"{n_sell/total*100:.0f}%")
        c4.metric("⭐ 평균 점수", f"{avg_score:.1f}")

        st.markdown("---")

        from scanner import plot_dashboard as _plot_scn
        fig = _plot_scn(results, show=False)
        st.plotly_chart(fig, use_container_width=True)

        chip("종목별 상세")
        rows = []
        for r in results:
            rows.append({
                "종목":      r["ticker"],
                "시장":      r["market"].upper(),
                "현재가":    f"{r['close']:,.0f}",
                "등락":      f"{r['change_pct']:+.1f}%",
                "RSI":       f"{r['rsi']:.0f}",
                "MA":        "🌟 골든" if r["ma_golden"] else "💀 데드",
                "MACD":      "▲ UP" if r["macd_up"] else "▼ DN",
                "점수":      f"{r['score']:.1f}",
                "의견":      r["opinion"],
                "매수 신호": ", ".join(r["buys"]) if r["buys"] else "-",
            })
        scan_df = pd.DataFrame(rows)
        styled = (scan_df.style
                  .map(_color_opinion, subset=["의견"])
                  .map(_color_change,  subset=["등락"])
                  .set_properties(**{"text-align": "center"})
                  .hide(axis="index"))
        st.dataframe(styled, use_container_width=True)


# ── 페이지: DART 기본적 분석 스크리너 ────────────────────────────────────────

def _get_dart_api_key() -> str | None:
    try:
        return st.secrets["dart"]["api_key"]
    except Exception:
        return None


def _fmt_per(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{v:.1f}배"


def _fmt_pbr(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{v:.2f}배"


def _color_grade(val: str) -> str:
    if "강력매수" in val: return "color:#34d399; font-weight:700"
    if "매수"    in val: return "color:#6ee7b7; font-weight:600"
    if "주의"    in val: return "color:#fbbf24; font-weight:600"
    if "매도"    in val: return "color:#f87171; font-weight:600"
    return "color:#94a3b8"


@st.cache_data(ttl=3600)
def cached_dart_financials(ticker: str, api_key: str, years: int):
    from dart_screener import (get_corp_code, fetch_annual_financials,
                                fetch_price_history, calc_band, DartNetworkError)
    try:
        cc = get_corp_code(ticker, api_key)
    except DartNetworkError as e:
        raise e
    if not cc:
        return None, None, None, None
    try:
        fin_df = fetch_annual_financials(api_key, cc, years, ticker=ticker)
    except DartNetworkError as e:
        raise e
    price_df = fetch_price_history(ticker, years + 1)
    band_df  = calc_band(fin_df, price_df) if not fin_df.empty and not price_df.empty else None
    return cc, fin_df, price_df, band_df


@st.cache_data(ttl=3600)
def cached_corp_name(corp_code: str, api_key: str) -> str:
    from dart_screener import _get_corp_name
    return _get_corp_name(api_key, corp_code) or corp_code


def _show_dart_network_error(detail: str = "") -> None:
    """DART 네트워크 오류 공통 안내 박스."""
    st.error(
        "**DART API 연결 실패** — Streamlit Cloud(해외 서버)에서는 "
        "`opendart.fss.or.kr`에 접속이 차단될 수 있습니다.\n\n"
        "**해결 방법:** 로컬 PC에서 아래 명령을 실행하여 "
        "`dart_corp_codes.json`을 생성한 뒤 GitHub에 커밋하세요.\n\n"
        "```\n"
        "cd stock_analyzer\n"
        "python generate_dart_cache.py\n"
        "git add dart_corp_codes.json\n"
        "git commit -m \"Add DART corp codes cache\"\n"
        "git push\n"
        "```"
    )
    if detail:
        with st.expander("상세 오류"):
            st.code(detail)


def show_dart_screener():
    page_header(
        "📊", "DART 기본적 분석 스크리너",
        "Open DART API 기반 EPS·BPS 수집 → 역사적 PER/PBR 밴드 분석 → 저평가 종목 스크리닝",
    )

    api_key = _get_dart_api_key()
    if not api_key:
        st.error(
            "DART API 키가 설정되지 않았습니다.  \n"
            "`.streamlit/secrets.toml`에 `[dart] api_key = \"발급받은키\"`를 추가하거나 "
            "Streamlit Cloud → Settings → Secrets에 등록해 주세요."
        )
        st.code("""[dart]\napi_key = "발급받은키\"""", language="toml")
        return

    tab_single, tab_screen = st.tabs(["📈 개별 종목 밴드 분석", "🔍 저평가 스크리너"])

    # ── 탭1: 개별 종목 ─────────────────────────────────────────────────────────
    with tab_single:
        from dart_screener import search_corps, get_corp_name_map

        chip("종목 검색")
        sc1, sc2 = st.columns([4, 1])
        with sc1:
            search_q = st.text_input(
                "회사명 또는 종목코드 입력",
                placeholder="예: 삼성전자  /  현대차  /  005930",
                key="dart_search_q",
                label_visibility="collapsed",
            )
        with sc2:
            s_years = st.slider("기간(년)", 3, 7, 5, key="dart_single_years",
                                label_visibility="collapsed")

        # 검색 결과
        s_ticker = st.session_state.get("dart_selected_ticker", "")
        s_name   = st.session_state.get("dart_selected_name",   "")

        if search_q:
            hits = search_corps(search_q, max_results=50)
            if not hits:
                st.warning("검색 결과가 없습니다.")
            else:
                opts = []
                for h in hits:
                    badge = "✅" if h["has_cache"] else "⬜"
                    eps_str = f"  EPS:{h['latest_eps']:,.0f}" if h.get("latest_eps") else ""
                    opts.append(f"{badge} {h['corp_name']} ({h['ticker']}){eps_str}")

                picked = st.selectbox(
                    f"검색 결과 {len(hits)}개 (✅=재무데이터 있음)",
                    opts,
                    key="dart_search_sel",
                )
                if st.button("이 종목 분석", key="dart_search_go", use_container_width=False):
                    idx = opts.index(picked)
                    st.session_state["dart_selected_ticker"] = hits[idx]["ticker"]
                    st.session_state["dart_selected_name"]   = hits[idx]["corp_name"]
                    s_ticker = hits[idx]["ticker"]
                    s_name   = hits[idx]["corp_name"]
                    st.rerun()

        if not s_ticker:
            st.info("위 검색창에서 종목을 찾아 선택하세요.  \n"
                    "예) '삼성' 입력 → 삼성전자, 삼성바이오로직스... 목록 표시")
            return

        with st.spinner(f"[{s_ticker}] DART 재무 데이터 수집 중..."):
            try:
                cc, fin_df, price_df, band_df = cached_dart_financials(
                    s_ticker.strip(), api_key, s_years
                )
            except Exception as e:
                err_msg = str(e)
                _show_dart_network_error(err_msg)
                return

        if cc is None:
            st.error("DART에서 해당 종목코드를 찾을 수 없습니다.  \n"
                     "`dart_corp_codes.json` 캐시가 없으면 로컬에서 먼저 실행해야 합니다.")
            return
        if fin_df is None or fin_df.empty:
            st.error("재무 데이터를 가져오지 못했습니다. 종목코드 또는 API 키를 확인하세요.")
            return

        name = s_name or cached_corp_name(cc, api_key)
        cur_price = float(price_df["Close"].iloc[-1]) if price_df is not None and not price_df.empty else 0

        from dart_screener import score_stock, plot_valuation_band
        s = score_stock(band_df if band_df is not None else pd.DataFrame(),
                        cur_price, fin_df)

        # ── 종목 헤더 ──────────────────────────────────────────────────────────
        grade_color_map = {
            "강력매수": "#34d399", "매수": "#6ee7b7",
            "중립": "#94a3b8", "주의": "#fbbf24", "매도": "#f87171",
        }
        g_color = grade_color_map.get(s["grade"], "#94a3b8")
        st.markdown(
            f'<div style="background:#1a2035; border-radius:12px; padding:16px 20px; '
            f'margin-bottom:16px; border-left:4px solid #3b82f6;">'
            f'<div style="font-size:1.3rem; font-weight:700; color:#e2e8f0;">{name}</div>'
            f'<div style="font-size:0.82rem; color:#718096; margin-top:4px;">'
            f'<code style="background:#0e1117; padding:2px 8px; border-radius:4px;">{s_ticker}</code>'
            f'&nbsp;&nbsp;DART 코드: {cc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── 핵심 지표 ──────────────────────────────────────────────────────────
        chip("핵심 밸류에이션")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("💰 현재가",  f"{cur_price:,.0f}원" if cur_price else "N/A")
        c2.metric("📊 현재 PER", _fmt_per(s["cur_per"]))
        c3.metric("📘 현재 PBR", _fmt_pbr(s["cur_pbr"]))
        c4.metric("💵 EPS",     f"{s['eps']:,.0f}원" if s["eps"] else "N/A")
        c5.metric("🏦 BPS",     f"{s['bps']:,.0f}원" if s["bps"] else "N/A")

        # 역사적 평균 PER/PBR
        if band_df is not None and not band_df.empty:
            chip("역사적 밴드 요약")
            c6, c7, c8, c9 = st.columns(4)
            if "per_avg" in band_df.columns and band_df["per_avg"].notna().any():
                p_avg = band_df["per_avg"].dropna().mean()
                p_lo  = band_df["per_low"].dropna().mean()
                p_hi  = band_df["per_high"].dropna().mean()
                c6.metric("📉 PER 역사 평균",  f"{p_avg:.1f}배")
                c7.metric("📉 PER 역사 범위",  f"{p_lo:.1f}~{p_hi:.1f}배")
            if "pbr_avg" in band_df.columns and band_df["pbr_avg"].notna().any():
                q_avg = band_df["pbr_avg"].dropna().mean()
                q_lo  = band_df["pbr_low"].dropna().mean()
                q_hi  = band_df["pbr_high"].dropna().mean()
                c8.metric("📉 PBR 역사 평균",  f"{q_avg:.2f}배")
                c9.metric("📉 PBR 역사 범위",  f"{q_lo:.2f}~{q_hi:.2f}배")

        # ── 저평가 점수 ────────────────────────────────────────────────────────
        chip("저평가 종합 점수")
        sc1, sc2 = st.columns([1, 3])
        sc1.metric(
            f"종합 점수 ({s['grade']})",
            f"{s['score']} / 100",
        )
        if s["reasons"]:
            with sc2:
                for reason in s["reasons"]:
                    st.markdown(
                        f'<div style="font-size:0.82rem; color:#94a3b8; '
                        f'padding:2px 0;">• {reason}</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("---")

        # ── 밴드 차트 ──────────────────────────────────────────────────────────
        if price_df is not None and not price_df.empty:
            fig = plot_valuation_band(
                s_ticker, name, price_df, fin_df,
                band_df if band_df is not None else pd.DataFrame(),
                show=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("주가 데이터를 가져오지 못했습니다.")

        # ── 재무 데이터 테이블 ─────────────────────────────────────────────────
        with st.expander("📋 연간 재무 데이터 (DART)", expanded=False):
            disp = fin_df.copy()
            fmt_cols = {
                "revenue":   "매출액",
                "op_income": "영업이익",
                "net_income":"순이익",
                "eps":       "EPS(원)",
                "bps":       "BPS(원)",
            }
            disp = disp.rename(columns={"year": "연도", **fmt_cols})
            for col in ["매출액", "영업이익", "순이익"]:
                if col in disp.columns:
                    disp[col] = disp[col].apply(
                        lambda v: f"{v/1e8:,.0f}억원" if pd.notna(v) else "-"
                    )
            for col in ["EPS(원)", "BPS(원)"]:
                if col in disp.columns:
                    disp[col] = disp[col].apply(
                        lambda v: f"{v:,.0f}" if pd.notna(v) else "-"
                    )
            drop = [c for c in ["fs_div"] if c in disp.columns]
            st.dataframe(disp.drop(columns=drop).set_index("연도"),
                         use_container_width=True)

        if band_df is not None and not band_df.empty:
            with st.expander("📋 연간 PER/PBR 밴드 데이터", expanded=False):
                bd = band_df.copy()
                for col in ["per_high", "per_low", "per_avg",
                            "pbr_high", "pbr_low", "pbr_avg"]:
                    if col in bd.columns:
                        bd[col] = bd[col].apply(
                            lambda v: f"{v:.1f}배" if pd.notna(v) else "-"
                        )
                for col in ["p_high", "p_low", "p_avg"]:
                    if col in bd.columns:
                        bd[col] = bd[col].apply(
                            lambda v: f"{v:,.0f}" if pd.notna(v) else "-"
                        )
                st.dataframe(bd.set_index("year"), use_container_width=True)

    # ── 탭2: 저평가 스크리너 ───────────────────────────────────────────────────
    with tab_screen:
        from dart_screener import _load_fin_cache, score_stock as _score

        fin_cache = _load_fin_cache()
        n_cached  = len(fin_cache)

        # ── 필터 설정 ──────────────────────────────────────────────────────────
        chip("스크리닝 설정")
        with st.expander("⚙️ 필터 / 검색 옵션", expanded=True):
            fc1, fc2, fc3 = st.columns([3, 2, 2])
            with fc1:
                sc_search = st.text_input(
                    "회사명 또는 종목코드 필터 (비우면 전체)",
                    placeholder="예: 현대  /  삼성  /  005930",
                    key="dart_sc_search",
                )
            with fc2:
                sc_grade = st.multiselect(
                    "의견 필터",
                    ["강력매수", "매수", "중립", "주의", "매도"],
                    default=["강력매수", "매수"],
                    key="dart_sc_grade",
                )
            with fc3:
                sc_min_score = st.slider("최소 점수", 0, 100, 50, key="dart_sc_minscore")

            run_sc = st.button(
                f"▶ 캐시 종목 스크리닝 실행 ({n_cached:,}개 종목, 즉시)",
                use_container_width=True, key="dart_sc_run",
            )
            st.caption(
                "💡 재무 데이터가 캐시된 종목만 스크리닝합니다.  "
                "로컬에서 `python generate_dart_cache.py --all` 실행 후 커밋하면 전체 상장사 검색 가능."
            )

        if "dart_sc_result" not in st.session_state:
            st.session_state.dart_sc_result = None

        if run_sc:
            if not fin_cache:
                st.error("재무 데이터 캐시(dart_fin_cache.json)가 없습니다.")
            else:
                # 캐시에서 바로 스크리닝 (API 호출 없음)
                with st.spinner(f"캐시 {n_cached:,}개 종목 스크리닝 중..."):
                    from dart_screener import (
                        pd as _pd, fetch_price_history, calc_band,
                        get_corp_name_map,
                    )
                    name_map_sc = get_corp_name_map()
                    q_lower = sc_search.strip().lower()

                    results = []
                    for tk, entry in fin_cache.items():
                        # 이름/코드 필터
                        corp_nm = entry.get("corp_name", tk)
                        if q_lower and q_lower not in corp_nm.lower() and q_lower not in tk.lower():
                            continue

                        rows = entry.get("financials", [])
                        if not rows:
                            continue
                        fin_df = pd.DataFrame(rows)
                        if fin_df.empty:
                            continue

                        try:
                            price_df = fetch_price_history(tk, 7)
                            if price_df.empty:
                                continue
                            cur_price = float(price_df["Close"].iloc[-1])
                            band_df   = calc_band(fin_df, price_df)
                            s         = _score(band_df, cur_price, fin_df)

                            # 의견/점수 필터
                            if sc_grade and s["grade"] not in sc_grade:
                                continue
                            if s["score"] < sc_min_score:
                                continue

                            results.append(dict(
                                ticker=tk,
                                name=corp_nm,
                                cur_price=cur_price,
                                fin_df=fin_df,
                                price_df=price_df,
                                band_df=band_df,
                                **s,
                            ))
                        except Exception:
                            continue

                    results.sort(key=lambda x: x["score"], reverse=True)

                st.session_state.dart_sc_result = results
                if not results:
                    st.warning("조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.")

        if st.session_state.dart_sc_result:
            results = st.session_state.dart_sc_result
            if not results:
                return

            # ── 요약 메트릭 ────────────────────────────────────────────────────
            n_buy  = sum(1 for r in results if r["grade"] in ("강력매수", "매수"))
            n_sell = sum(1 for r in results if r["grade"] in ("주의", "매도"))
            n_neut = len(results) - n_buy - n_sell
            top    = results[0]

            chip("스크리닝 요약")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📋 분석 종목", f"{len(results)}개")
            c2.metric("🟢 매수 의견", f"{n_buy}개")
            c3.metric("⬜ 중립 의견", f"{n_neut}개")
            c4.metric("🔴 주의/매도",  f"{n_sell}개")

            st.markdown("---")

            # ── 버블 차트 ──────────────────────────────────────────────────────
            from dart_screener import plot_screener_result
            fig_sc = plot_screener_result(results, show=False)
            st.plotly_chart(fig_sc, use_container_width=True)

            # ── 결과 테이블 ────────────────────────────────────────────────────
            chip("종목별 결과 (점수 순)")
            rows = []
            for r in results:
                rows.append({
                    "종목명":   r.get("name", r["ticker"]),
                    "코드":     r["ticker"],
                    "현재가":   f"{r['cur_price']:,.0f}",
                    "현재PER":  _fmt_per(r.get("cur_per")),
                    "현재PBR":  _fmt_pbr(r.get("cur_pbr")),
                    "EPS":      f"{r['eps']:,.0f}원" if r.get("eps") else "N/A",
                    "BPS":      f"{r['bps']:,.0f}원" if r.get("bps") else "N/A",
                    "점수":     f"{r['score']}",
                    "의견":     r["grade"],
                    "주요 근거": r["reasons"][0] if r.get("reasons") else "-",
                })

            sc_df = pd.DataFrame(rows)
            styled = (
                sc_df.style
                .map(_color_grade, subset=["의견"])
                .set_properties(**{"text-align": "center"})
                .hide(axis="index")
            )
            st.dataframe(styled, use_container_width=True)

            # ── 개별 상세 조회 (탭2 내 드릴다운) ─────────────────────────────
            st.markdown("---")
            chip("📌 개별 종목 상세 분석")
            ticker_opts = [f"{r.get('name', r['ticker'])} ({r['ticker']})"
                           for r in results]
            selected_opt = st.selectbox(
                "상세 분석할 종목 선택", ticker_opts, key="dart_drill_sel"
            )
            if selected_opt:
                idx   = ticker_opts.index(selected_opt)
                r_sel = results[idx]

                if r_sel.get("price_df") is not None and not r_sel["price_df"].empty:
                    from dart_screener import plot_valuation_band
                    fig_d = plot_valuation_band(
                        r_sel["ticker"], r_sel.get("name", r_sel["ticker"]),
                        r_sel["price_df"], r_sel["fin_df"],
                        r_sel.get("band_df", pd.DataFrame()),
                        show=False,
                    )
                    st.plotly_chart(fig_d, use_container_width=True)
                else:
                    st.warning("주가 데이터를 가져오지 못했습니다.")

                if r_sel.get("reasons"):
                    with st.expander("📝 저평가 판단 근거", expanded=True):
                        for reason in r_sel["reasons"]:
                            st.markdown(f"• {reason}")


# ── 페이지: 가상 투자 ────────────────────────────────────────────────────────

def show_virtual_portfolio():
    from virtual_portfolio import (
        load_portfolio, save_portfolio, reset_portfolio,
        buy as vp_buy, sell as vp_sell,
        evaluate, plot_portfolio, get_current_price,
        search_kr_stocks, search_us_stocks, rebuild_kr_ticker_db,
        KR_BUY_FEE, KR_SELL_FEE, KR_SELL_TAX,
    )

    page_header("💰", "가상 투자",
                "가상 자금으로 국내·미국 주식을 매수·매도하고 포트폴리오 성과를 추적합니다.")

    # ── 포트폴리오 로드 & 평가 ─────────────────────────────────────────────────
    p  = load_portfolio()
    ev = evaluate(p)

    # ── 상단 요약 메트릭 ────────────────────────────────────────────────────────
    chip("포트폴리오 요약")
    c1, c2, c3, c4, c5 = st.columns(5)
    pnl_sign  = "+" if ev["total_pnl"] >= 0 else ""
    pnl_color = "#34d399" if ev["total_pnl"] >= 0 else "#f87171"
    c1.metric("💼 총 자산",     f"{ev['total_value']:,.0f}원")
    c2.metric("💵 현금 잔고",   f"{ev['cash']:,.0f}원")
    c3.metric("📦 주식 평가액", f"{ev['holdings_value']:,.0f}원")
    c4.metric("💹 총 손익",
              f"{pnl_sign}{ev['total_pnl']:,.0f}원",
              f"{ev['total_pnl_pct']:+.2f}%")
    c5.metric("🏦 초기 자본",   f"{ev['initial_capital']:,.0f}원")

    st.markdown("---")

    # ── 차트 (자산 구성 파이 + 종목별 수익률 바) ────────────────────────────────
    fig_pf = plot_portfolio(ev, show=False)
    st.plotly_chart(fig_pf, use_container_width=True)

    # ── 보유 종목 테이블 ────────────────────────────────────────────────────────
    if ev["rows"]:
        chip("보유 종목")
        hold_rows = []
        for r in ev["rows"]:
            hold_rows.append({
                "종목명":   r["종목명"],
                "티커":     r["티커"],
                "시장":     r["시장"],
                "수량":     f"{r['수량']:,}주",
                "평균단가": f"{r['평균단가']:,.0f}원",
                "현재가":   f"{r['현재가']:,.0f}원",
                "평가금액": f"{r['평가금액']:,.0f}원",
                "손익":     f"{r['손익']:+,.0f}원",
                "수익률":   f"{r['수익률']:+.2f}%",
            })
        hold_df = pd.DataFrame(hold_rows)
        styled_hold = (hold_df.style
                       .map(_color_pnl,    subset=["손익"])
                       .map(_color_change, subset=["수익률"])
                       .set_properties(**{"text-align": "center"})
                       .hide(axis="index"))
        st.dataframe(styled_hold, use_container_width=True)
    else:
        st.info("보유 종목이 없습니다. 아래 [🛒 매수] 탭에서 종목을 매수해 보세요.")

    st.markdown("---")

    # ── 탭: 매수 / 매도 / 거래 내역 / 설정 ────────────────────────────────────
    tab_buy, tab_sell, tab_hist, tab_cfg = st.tabs(
        ["🛒 매수", "💸 매도", "📋 거래 내역", "⚙️ 설정"]
    )

    # ── 매수 탭 ────────────────────────────────────────────────────────────────
    with tab_buy:
        # ── 종목 검색 섹션 ─────────────────────────────────────────────────────
        chip("종목 검색")
        sc1, sc2, sc3 = st.columns([4, 2, 1])
        with sc1:
            search_q = st.text_input(
                "종목명으로 검색",
                placeholder="예: 삼성전자 / 카카오 / Apple / Tesla",
                key="vp_sq",
                label_visibility="collapsed",
            )
        with sc2:
            search_mkt = st.selectbox(
                "검색 시장",
                ["국내 (KR)", "미국 (US)"],
                key="vp_sm",
                label_visibility="collapsed",
            )
        with sc3:
            st.markdown("<div style='margin-top:2px'></div>", unsafe_allow_html=True)
            do_search = st.button("🔍 검색", key="vp_do_search", use_container_width=True)

        if do_search:
            if not search_q.strip():
                st.warning("검색어를 입력하세요.")
            else:
                sm_code = "kr" if "KR" in search_mkt else "us"
                with st.spinner("검색 중..."):
                    sr = (search_kr_stocks(search_q.strip())
                          if sm_code == "kr"
                          else search_us_stocks(search_q.strip()))
                st.session_state["vp_sr"]     = sr
                st.session_state["vp_sr_mkt"] = sm_code
                if not sr:
                    st.warning("검색 결과가 없습니다. 검색어를 바꿔 보세요.")

        # 검색 결과 표시
        sr      = st.session_state.get("vp_sr", [])
        sr_mkt  = st.session_state.get("vp_sr_mkt", "kr")
        if sr:
            if sr_mkt == "kr":
                opts = [f"{r['name']}  ({r['code']})" for r in sr]
            else:
                opts = [
                    f"{r['name']}  [{r['ticker']}] — {r.get('exchange', r['type'])}"
                    for r in sr
                ]
            rc1, rc2 = st.columns([5, 1])
            with rc1:
                picked = st.selectbox("검색 결과", opts, key="vp_sr_sel",
                                      label_visibility="collapsed")
            with rc2:
                if st.button("✅ 선택", key="vp_pick", use_container_width=True):
                    idx  = opts.index(picked)
                    r    = sr[idx]
                    code = r.get("code") or r.get("ticker", "")
                    st.session_state["vp_buy_ticker"] = code
                    st.session_state["vp_buy_market"] = (
                        "국내 (KR)" if sr_mkt == "kr" else "미국 (US)"
                    )
                    st.session_state["vp_sr"] = []   # 결과 초기화
                    st.rerun()

        st.markdown("---")

        # ── 매수 주문 폼 ───────────────────────────────────────────────────────
        chip("매수 주문")
        col_a, col_b = st.columns(2)

        with col_a:
            buy_ticker = st.text_input(
                "종목 코드",
                value="005930",
                key="vp_buy_ticker",
                help="위에서 검색 후 선택하거나 직접 입력 (국내: 005930 / 미국: AAPL)",
            )
            buy_market = st.selectbox("시장", ["국내 (KR)", "미국 (US)"], key="vp_buy_market")
            buy_mkt_code = "kr" if "KR" in buy_market else "us"

        with col_b:
            if st.button("💲 현재가 조회", key="vp_buy_lookup"):
                with st.spinner("현재가 조회 중..."):
                    cur_p = get_current_price(buy_ticker.strip().upper(), buy_mkt_code)
                if cur_p:
                    st.session_state["vp_buy_price_val"] = cur_p
                    st.success(f"현재가: {cur_p:,.0f}원")
                else:
                    st.error("현재가를 가져오지 못했습니다.")

            buy_price = st.number_input(
                "매수 가격 (원)",
                min_value=1.0,
                step=100.0,
                value=float(st.session_state.get("vp_buy_price_val", 70000)),
                key="vp_buy_price",
                format="%.0f",
            )
            buy_qty = st.number_input(
                "수량 (주)", min_value=1, value=1, step=1, key="vp_buy_qty"
            )

        est_buy_amt = buy_price * buy_qty
        est_buy_fee = round(est_buy_amt * KR_BUY_FEE) if buy_mkt_code == "kr" else 0
        st.info(
            f"예상 매수금액: **{est_buy_amt:,.0f}원** + 수수료 {est_buy_fee:,.0f}원"
            f" = **{est_buy_amt + est_buy_fee:,.0f}원**  |  현금 잔고: {p['cash']:,.0f}원"
        )

        if st.button("✅ 매수 실행", key="vp_buy_exec", use_container_width=True):
            ok, msg = vp_buy(
                p, buy_ticker.strip().upper(), buy_mkt_code,
                int(buy_qty), float(buy_price),
            )
            if ok:
                save_portfolio(p)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # ── 매도 탭 ────────────────────────────────────────────────────────────────
    with tab_sell:
        chip("종목 매도")
        if not p["holdings"]:
            st.info("보유 종목이 없습니다.")
        else:
            holding_keys = list(p["holdings"].keys())
            holding_labels = [
                f"{h['name']} ({h['ticker']}/{h['market'].upper()}) — {h['quantity']:,}주"
                for h in p["holdings"].values()
            ]
            sell_choice = st.selectbox("매도할 종목", holding_labels, key="vp_sell_choice")
            sell_key    = holding_keys[holding_labels.index(sell_choice)]
            sell_h      = p["holdings"][sell_key]

            col_c, col_d = st.columns(2)
            with col_c:
                if st.button("🔍 현재가 조회", key="vp_sell_lookup"):
                    with st.spinner("현재가 조회 중..."):
                        s_cur = get_current_price(sell_h["ticker"], sell_h["market"])
                    if s_cur:
                        st.session_state["vp_sell_price_val"] = s_cur
                        st.success(f"현재가: {s_cur:,.0f}원")
                    else:
                        st.error("현재가를 가져오지 못했습니다.")

                sell_price = st.number_input(
                    "매도 가격 (원)",
                    min_value=1.0,
                    step=100.0,
                    value=float(st.session_state.get("vp_sell_price_val",
                                                     sell_h["avg_price"])),
                    key="vp_sell_price",
                    format="%.0f",
                )

            with col_d:
                sell_qty = st.number_input(
                    "수량 (주)",
                    min_value=1,
                    max_value=sell_h["quantity"],
                    value=sell_h["quantity"],
                    step=1,
                    key="vp_sell_qty",
                )
                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096; margin-top:8px;'>"
                    f"평균단가: {sell_h['avg_price']:,.0f}원 &nbsp;|&nbsp; "
                    f"보유: {sell_h['quantity']:,}주</div>",
                    unsafe_allow_html=True,
                )

            sell_mkt      = sell_h["market"]
            est_sell_fee  = (round(sell_price * sell_qty * (KR_SELL_FEE + KR_SELL_TAX))
                             if sell_mkt == "kr" else 0)
            est_net       = sell_price * sell_qty - est_sell_fee
            est_pnl       = round((sell_price - sell_h["avg_price"]) * sell_qty - est_sell_fee)
            est_pnl_color = "#34d399" if est_pnl >= 0 else "#f87171"
            est_pnl_sign  = "+" if est_pnl >= 0 else ""
            st.markdown(
                f'<div style="background:#1a2035; border-radius:8px; padding:12px 16px; margin:8px 0;">'
                f'예상 수령액: <b>{est_net:,.0f}원</b> (수수료+세금: {est_sell_fee:,.0f}원)'
                f'&nbsp;&nbsp;|&nbsp;&nbsp;'
                f'예상 손익: <span style="color:{est_pnl_color}; font-weight:700;">'
                f'{est_pnl_sign}{est_pnl:,.0f}원</span></div>',
                unsafe_allow_html=True,
            )

            if st.button("✅ 매도 실행", key="vp_sell_exec", use_container_width=True):
                ok, msg = vp_sell(
                    p, sell_h["ticker"], sell_h["market"],
                    int(sell_qty), float(sell_price),
                )
                if ok:
                    save_portfolio(p)
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # ── 거래 내역 탭 ───────────────────────────────────────────────────────────
    with tab_hist:
        chip("거래 내역")
        txs = p.get("transactions", [])
        if not txs:
            st.info("거래 내역이 없습니다.")
        else:
            def _color_action(val: str) -> str:
                if val == "BUY":  return "color:#60a5fa; font-weight:700"
                if val == "SELL": return "color:#f87171; font-weight:700"
                return ""

            tx_rows = []
            for t in txs:
                pnl_str = (f"{t['pnl']:+,.0f}원"
                           if t.get("pnl") is not None else "—")
                tx_rows.append({
                    "일시":     t["date"],
                    "구분":     t["action"],
                    "종목명":   t["name"],
                    "티커":     t["ticker"],
                    "시장":     t["market"],
                    "가격":     f"{t['price']:,.0f}원",
                    "수량":     f"{t['quantity']:,}주",
                    "거래금액": f"{t['amount']:,.0f}원",
                    "수수료":   f"{t['fee']:,.0f}원",
                    "손익":     pnl_str,
                })
            tx_df = pd.DataFrame(tx_rows)
            styled_tx = (tx_df.style
                         .map(_color_action, subset=["구분"])
                         .map(_color_pnl,    subset=["손익"])
                         .set_properties(**{"text-align": "center"})
                         .hide(axis="index"))
            st.dataframe(styled_tx, use_container_width=True)

    # ── 설정 탭 ────────────────────────────────────────────────────────────────
    with tab_cfg:
        chip("포트폴리오 정보")
        st.markdown(
            f'<div style="background:#1a2035; border-radius:10px; padding:16px 20px; margin-bottom:16px;">'
            f'<div style="color:#94a3b8; font-size:0.78rem;">생성일</div>'
            f'<div style="color:#e2e8f0; margin-bottom:10px;">{p.get("created_at", "—")}</div>'
            f'<div style="color:#94a3b8; font-size:0.78rem;">초기 자본</div>'
            f'<div style="color:#e2e8f0;">{p["initial_capital"]:,.0f}원</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        with st.expander("✏️ 평균단가 수정", expanded=False):
            if not p["holdings"]:
                st.info("보유 종목이 없습니다.")
            else:
                avg_keys   = list(p["holdings"].keys())
                avg_labels = [
                    f"{h['name']} ({h['ticker']}/{h['market'].upper()})"
                    for h in p["holdings"].values()
                ]
                avg_choice = st.selectbox(
                    "수정할 종목", avg_labels, key="vp_avg_choice"
                )
                avg_key = avg_keys[avg_labels.index(avg_choice)]
                avg_h   = p["holdings"][avg_key]

                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096; margin-bottom:6px;'>"
                    f"현재 평균단가: <b style='color:#e2e8f0;'>{avg_h['avg_price']:,.2f}원</b>"
                    f"&nbsp;|&nbsp; 보유 수량: {avg_h['quantity']:,}주</div>",
                    unsafe_allow_html=True,
                )
                new_avg = st.number_input(
                    "새 평균단가 (원)",
                    min_value=0.01,
                    value=float(avg_h["avg_price"]),
                    step=100.0,
                    format="%.2f",
                    key="vp_avg_price_input",
                )
                if st.button("✅ 평균단가 적용", key="vp_avg_apply"):
                    p["holdings"][avg_key]["avg_price"] = round(float(new_avg), 4)
                    save_portfolio(p)
                    st.success(
                        f"{avg_h['name']} 평균단가를 {new_avg:,.2f}원으로 수정했습니다."
                    )
                    st.rerun()

        from virtual_portfolio import _KR_DB_PATH
        with st.expander("🗂️ 국내 종목 DB 관리", expanded=False):
            db_exists = _KR_DB_PATH.exists()
            if db_exists:
                import os
                mtime = datetime.fromtimestamp(os.path.getmtime(_KR_DB_PATH))
                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096;'>"
                    f"마지막 갱신: {mtime.strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; "
                    f"경로: kr_tickers.json</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.warning("kr_tickers.json 파일이 없습니다. 갱신 버튼을 눌러 주세요.")

            if st.button("🔄 국내 종목 DB 갱신 (KOSPI+KOSDAQ)", key="vp_rebuild_db",
                         use_container_width=True):
                with st.spinner("KOSPI + KOSDAQ 종목 목록 수집 중... (20~30초 소요)"):
                    ok, msg = rebuild_kr_ticker_db()
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        with st.expander("⚠️ 포트폴리오 초기화 (모든 데이터 삭제)", expanded=False):
            new_capital = st.number_input(
                "새 초기 자본 (원)",
                min_value=100_000,
                value=10_000_000,
                step=1_000_000,
                format="%d",
                key="vp_reset_capital",
            )
            st.warning("초기화하면 모든 보유 종목과 거래 내역이 삭제됩니다.")
            confirm_reset = st.checkbox("정말 초기화하겠습니다", key="vp_reset_confirm")
            if st.button("🔄 포트폴리오 초기화", key="vp_reset_exec",
                         disabled=not confirm_reset):
                reset_portfolio(float(new_capital))
                st.success(f"포트폴리오가 {new_capital:,.0f}원으로 초기화되었습니다.")
                st.rerun()


# ── 라우팅 ────────────────────────────────────────────────────────────────────

if   "시장 현황"   in page: show_market()
elif "종목 분석"   in page: show_analyzer()
elif "백테스팅"    in page: show_backtest()
elif "전략 비교"   in page: show_compare()
elif "MA 최적화"   in page: show_optimizer()
elif "기업 분석"   in page: show_fundamental()
elif "투자자 동향" in page: show_ownership()
elif "섹터"        in page: show_sector()
elif "스캐너"      in page: show_scanner()
elif "DART"        in page: show_dart_screener()
elif "가상"        in page: show_virtual_portfolio()
