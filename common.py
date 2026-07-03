"""
공통 유틸리티 — CSS, 헤더/포맷 헬퍼, 캐시 함수, 종목 선택 위젯.

모든 페이지(views/*)가 공유합니다.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# st.navigation 페이지 레지스트리 — app.py가 매 실행마다 채움
NAV: dict = {}

# ── 시간 (KST) ───────────────────────────────────────────────────────────────

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """한국 시간 (서버 위치와 무관하게 UTC+9 고정)."""
    return datetime.now(KST)


# ── CSS ───────────────────────────────────────────────────────────────────────

def inject_css() -> None:
    """전역 CSS 주입 (app.py에서 매 실행 시 1회 호출)."""
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


# ── 뉴스 공통 유틸 ───────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def cached_news(ticker: str, corp_name: str, is_kr: bool) -> tuple:
    """뉴스 30분 캐시 (IP 차단 방지)."""
    from news import fetch_news, sentiment_summary
    try:
        naver_id     = st.secrets.get("naver", {}).get("client_id", "")
        naver_secret = st.secrets.get("naver", {}).get("client_secret", "")
    except Exception:
        naver_id = naver_secret = ""
    items, source = fetch_news(ticker, corp_name, is_kr,
                               naver_id, naver_secret, max_items=20)
    summary = sentiment_summary(items) if items else {}
    return items, source, summary


def _render_news(ticker: str, corp_name: str = "", is_kr: bool = True) -> None:
    """뉴스 목록 + 감성 요약 렌더링 (재사용 헬퍼)."""
    from news import sentiment_summary

    with st.spinner("뉴스 로딩 중..."):
        items, source, summ = cached_news(ticker, corp_name, is_kr)

    if not items:
        st.info(
            "뉴스를 가져오지 못했습니다.  \n"
            f"👉 [네이버 금융에서 직접 확인](https://finance.naver.com/item/news.naver?code={ticker})"
            if is_kr else
            "뉴스를 가져오지 못했습니다. Naver API 키를 설정하면 미국 종목 뉴스도 지원됩니다."
        )
        return

    # ── 감성 요약 배지 ─────────────────────────────────────────────────────────
    ov = summ.get("overall", "neutral")
    ov_color = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#94a3b8"}[ov]
    ov_label = {"positive": "🟢 긍정 우세", "negative": "🔴 부정 우세", "neutral": "⬜ 중립"}[ov]

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("뉴스 건수", f"{summ['total']}건", delta=f"출처: {source}")
    sc2.metric("🟢 긍정", f"{summ['positive']}건 ({summ['pos_pct']}%)")
    sc3.metric("🔴 부정", f"{summ['negative']}건 ({summ['neg_pct']}%)")
    sc4.metric("전체 분위기", ov_label)

    st.markdown("---")

    # ── 뉴스 카드 목록 ─────────────────────────────────────────────────────────
    sent_color = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#475569"}
    sent_label = {"positive": "긍정", "negative": "부정", "neutral": "중립"}

    for item in items:
        s_color = sent_color[item["sentiment"]]
        s_label = sent_label[item["sentiment"]]
        desc    = item.get("description", "")
        desc_html = f'<div style="color:#94a3b8; font-size:0.78rem; margin-top:4px;">{desc[:120]}…</div>' if desc else ""

        st.markdown(f"""
<div style="
    background:#1a2035;
    border:1px solid rgba(255,255,255,0.06);
    border-left:3px solid {s_color};
    border-radius:8px;
    padding:12px 16px;
    margin-bottom:8px;
">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
        <a href="{item['url']}" target="_blank" style="
            color:#e2e8f0; font-size:0.88rem; font-weight:500;
            text-decoration:none; line-height:1.5; flex:1;
        ">{item['title']}</a>
        <span style="
            background:{s_color}22; color:{s_color};
            border:1px solid {s_color}55;
            border-radius:12px; padding:1px 8px;
            font-size:0.70rem; font-weight:600; white-space:nowrap;
        ">{s_label}</span>
    </div>
    {desc_html}
    <div style="color:#4a5568; font-size:0.73rem; margin-top:6px;">
        {item['press']}  ·  {item['date']}
    </div>
</div>
""", unsafe_allow_html=True)

# ── 종목 선택 위젯 ────────────────────────────────────────────────────────────

_DIRECT_LABEL = "⌨️ 직접 입력 (미국 티커 등)"


@st.cache_data
def kr_stock_labels() -> list:
    """kr_tickers.json → ["삼성전자 (005930)", ...] (가나다순)."""
    path = Path(__file__).parent / "kr_tickers.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    labels = [f"{v.get('name', '')} ({code})"
              for code, v in data.items() if v.get("name")]
    labels.sort()
    return labels


def _label_to_code(label: str) -> str:
    return label.rsplit("(", 1)[-1].rstrip(")")


def _find_label(labels: list, code: str):
    return next((l for l in labels if l.endswith(f"({code})")), None)


def stock_picker(key: str, default_code: str = "005930",
                 label: str = "종목 선택", kr_only: bool = False):
    """이름으로 검색 가능한 종목 선택 위젯.

    국내 종목은 selectbox에 이름을 타이핑해 검색하고,
    미국 종목은 '직접 입력'을 선택한 뒤 티커를 입력한다.
    반환: (ticker, is_kr)
    """
    labels = kr_stock_labels()
    options = labels if kr_only else [_DIRECT_LABEL] + labels
    sel_key, direct_key = f"{key}_sel", f"{key}_direct"

    if not options:
        # 종목 DB를 읽지 못하면 기존 방식(직접 입력)으로 동작
        ticker = st.text_input("종목 코드 / 티커", value=default_code, key=direct_key)
        ticker = ticker.strip().upper()
        return ticker, detect_market(ticker)

    # 다른 페이지에서 넘어온 종목(goto_stock) 반영
    incoming = st.session_state.pop("goto_ticker", None)
    if incoming:
        match = _find_label(labels, incoming) if incoming.isdigit() else None
        if match:
            st.session_state[sel_key] = match
        elif not kr_only:
            st.session_state[sel_key] = _DIRECT_LABEL
            st.session_state[direct_key] = incoming

    if sel_key not in st.session_state:
        st.session_state[sel_key] = _find_label(labels, default_code) or options[0]
    if st.session_state[sel_key] not in options:
        st.session_state[sel_key] = options[0]

    picked = st.selectbox(
        label, options, key=sel_key,
        help="종목 이름을 입력하면 국내 종목이 검색됩니다."
             + ("" if kr_only else "  미국 종목은 '직접 입력'을 선택하세요."),
    )
    if picked == _DIRECT_LABEL:
        ticker = st.text_input("종목 코드 / 티커", value="AAPL", key=direct_key,
                               help="국내: 005930  /  미국: AAPL")
        ticker = ticker.strip().upper()
        return ticker, detect_market(ticker)
    return _label_to_code(picked), True


def goto_stock(ticker: str) -> None:
    """다른 페이지에서 '종목 분석' 페이지로 이동 (종목 자동 선택)."""
    st.session_state["goto_ticker"] = str(ticker).strip().upper()
    page = NAV.get("stock")
    if page is not None:
        st.switch_page(page)

