import requests
from bs4 import BeautifulSoup
import streamlit as st
import plotly.graph_objects as go

FEAR_WORDS = [
    "폭락", "위기", "경기침체", "하락", "붕괴", "공포", "패닉", "손실",
    "적자", "불안", "부도", "파산", "침체", "약세", "급락", "충격",
    "위험", "하락세", "매도세", "서킷브레이커", "긴축", "금리인상",
    "인플레이션", "스태그플레이션", "디폴트", "채무불이행", "경고",
    "역대최저", "신저가", "최저가",
]

GREED_WORDS = [
    "급등", "신고가", "호황", "상승", "강세", "매수", "낙관", "기대",
    "수익", "흑자", "돌파", "랠리", "반등", "활황", "성장",
    "최고", "최대", "우상향", "역대최고", "금리인하",
    "경기회복", "실적개선", "호실적", "신고점", "최고가",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_SOURCES = [
    (
        "https://finance.naver.com/news/mainnews.naver",
        ["dd.articleSubject a", ".articleSubject a", ".newsList li a"],
        "euc-kr",
    ),
    (
        "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
        ["dd.articleSubject a", ".title a", "li dt a"],
        "euc-kr",
    ),
]


@st.cache_data(ttl=21600)  # 6시간 캐시 (오전·오후 각 1회)
def fetch_market_news() -> list[str]:
    headlines: list[str] = []
    for url, selectors, encoding in _SOURCES:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=8)
            r.encoding = encoding
            soup = BeautifulSoup(r.text, "html.parser")
            for sel in selectors:
                tags = soup.select(sel)
                found = [t.get_text(strip=True) for t in tags if len(t.get_text(strip=True)) >= 8]
                headlines.extend(found)
                if found:
                    break
        except Exception:
            pass
    return list(dict.fromkeys(headlines))[:60]  # 중복 제거, 순서 유지


def analyze_sentiment(headlines: list[str]) -> tuple[int, list[str], list[str], list[tuple[str, str]]]:
    """
    Returns:
        score      0(극공포) ~ 100(극탐욕)
        fear_hits  검출된 공포 키워드
        greed_hits 검출된 탐욕 키워드
        colored    (아이콘, 헤드라인) 리스트 (최대 20개)
    """
    if not headlines:
        return 50, [], [], []

    text = " ".join(headlines)

    fear_hits  = [w for w in FEAR_WORDS  if w in text]
    greed_hits = [w for w in GREED_WORDS if w in text]

    fear_count  = sum(text.count(w) for w in FEAR_WORDS)
    greed_count = sum(text.count(w) for w in GREED_WORDS)
    total = fear_count + greed_count

    if total == 0:
        score = 50
    else:
        raw = greed_count / total * 100
        # 10~90 범위로 스케일: 순수 키워드 카운팅의 극단화 완화
        score = max(0, min(100, int(raw * 0.8 + 10)))

    colored: list[tuple[str, str]] = []
    for h in headlines[:20]:
        has_fear  = any(w in h for w in FEAR_WORDS)
        has_greed = any(w in h for w in GREED_WORDS)
        if has_fear and not has_greed:
            icon = "🔵"
        elif has_greed and not has_fear:
            icon = "🔴"
        else:
            icon = "⚪"
        colored.append((icon, h))

    return score, fear_hits, greed_hits, colored


def score_label(score: int) -> tuple[str, str]:
    """(레이블, 색상 hex)"""
    if score <= 20:   return "극도의 공포", "#1565C0"
    elif score <= 40: return "공포",        "#42A5F5"
    elif score <= 60: return "중립",        "#FFA726"
    elif score <= 80: return "탐욕",        "#EF5350"
    else:             return "극도의 탐욕", "#B71C1C"


def sentiment_gauge(score: int) -> go.Figure:
    label, color = score_label(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "점", "font": {"size": 48}},
        title={
            "text": (
                f"시장 감성 지수<br>"
                f"<span style='font-size:1.4em;font-weight:bold;color:{color}'>{label}</span>"
            )
        },
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "gray"},
            "bar":  {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "borderwidth": 1,
            "bordercolor": "gray",
            "steps": [
                {"range": [0,  20], "color": "#BBDEFB"},
                {"range": [20, 40], "color": "#E3F2FD"},
                {"range": [40, 60], "color": "#FFFDE7"},
                {"range": [60, 80], "color": "#FFEBEE"},
                {"range": [80, 100], "color": "#FFCDD2"},
            ],
            "threshold": {
                "line":      {"color": "black", "width": 4},
                "thickness": 0.75,
                "value":     score,
            },
        },
    ))
    fig.update_layout(height=360, margin=dict(t=80, b=20))
    return fig
