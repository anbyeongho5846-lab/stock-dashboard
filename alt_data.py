"""
대체 데이터 (Alternative Data)
1. 네이버 데이터랩 — 검색 트렌드 (Naver Client ID/Secret 필요)
2. 관세청 수출 데이터 — 품목별 월간 수출액 (무역협회 KITA 기반)
   · 매월 1일·11일·21일 공개되는 수출 현황 활용
"""

import json
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

# ── 네이버 데이터랩 ───────────────────────────────────────────────────────────

_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


def fetch_naver_trend(
    keywords: list,
    client_id: str,
    client_secret: str,
    start_date: str = None,    # "YYYY-MM-DD"
    end_date: str   = None,
    time_unit: str  = "week",  # "date" | "week" | "month"
) -> pd.DataFrame:
    """
    네이버 데이터랩 통합 검색 트렌드 API.
    키워드별 검색량 지수(0~100)를 반환합니다.

    Returns: DataFrame, index=period(datetime), columns=keywords
    """
    if not start_date:
        start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.today().strftime("%Y-%m-%d")

    # 최대 5개 키워드 그룹
    keyword_groups = [
        {"groupName": kw, "keywords": [kw]}
        for kw in keywords[:5]
    ]

    body = {
        "startDate":     start_date,
        "endDate":       end_date,
        "timeUnit":      time_unit,
        "keywordGroups": keyword_groups,
        "device":        "",
        "ages":          [],
        "gender":        "",
    }
    headers = {
        "X-Naver-Client-Id":     client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type":          "application/json",
    }
    resp = requests.post(
        _DATALAB_URL,
        headers=headers,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for item in data.get("results", []):
        name = item["title"]
        for pt in item.get("data", []):
            rows.append({"period": pt["period"], "keyword": name, "ratio": pt["ratio"]})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["period"] = pd.to_datetime(df["period"])
    pivot = df.pivot(index="period", columns="keyword", values="ratio")
    return pivot.sort_index()


def calc_lead_lag(
    trend_df: pd.DataFrame,
    price_df: pd.DataFrame,
    max_lag: int = 12,
    freq: str = "W",
) -> pd.DataFrame:
    """
    검색 트렌드와 주가 수익률의 리드-래그 교차 상관 분석.
    lag > 0 → 검색량이 lag주 후 주가 변화와 상관
    Returns: DataFrame index=lag, columns=keywords, values=correlation
    """
    if trend_df.empty or price_df.empty:
        return pd.DataFrame()

    price_ret = (
        price_df["Close"]
        .resample(freq).last()
        .pct_change()
        .dropna()
    )

    results = {}
    for kw in trend_df.columns:
        kw_chg = trend_df[kw].pct_change().dropna()
        corrs  = {}
        for lag in range(-max_lag, max_lag + 1):
            shifted = kw_chg.shift(lag)
            aligned = pd.concat([shifted, price_ret], axis=1).dropna()
            if len(aligned) >= 5:
                corrs[lag] = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
            else:
                corrs[lag] = float("nan")
        results[kw] = corrs

    return pd.DataFrame(results)


# ── 관세청 수출 데이터 ────────────────────────────────────────────────────────

# 섹터별 HS코드 매핑 (주요 품목)
EXPORT_SECTORS = {
    "반도체":    {"hs": ["8542", "8541"], "keywords": ["삼성전자", "SK하이닉스", "반도체"]},
    "자동차":    {"hs": ["8703", "8708"], "keywords": ["현대차", "기아", "자동차"]},
    "이차전지":  {"hs": ["8507"],         "keywords": ["LG에너지솔루션", "삼성SDI", "배터리"]},
    "디스플레이":{"hs": ["9013", "8524"], "keywords": ["LG디스플레이", "삼성디스플레이", "OLED"]},
    "조선":      {"hs": ["8901", "8902"], "keywords": ["HD현대중공업", "삼성중공업", "조선"]},
    "철강":      {"hs": ["7208", "7209"], "keywords": ["포스코", "현대제철", "철강"]},
    "K-뷰티":   {"hs": ["3304", "3305"], "keywords": ["아모레퍼시픽", "LG생활건강", "K뷰티"]},
    "K-푸드":   {"hs": ["1902", "2106"], "keywords": ["농심", "오리온", "비비고"]},
    "변압기":    {"hs": ["8504"],         "keywords": ["현대일렉트릭", "효성중공업", "변압기"]},
    "석유화학":  {"hs": ["2901", "2902"], "keywords": ["LG화학", "롯데케미칼", "석유화학"]},
}

# 관세청 수출 현황 (공개 데이터 URL)
_CUSTOMS_STAT_URL = (
    "https://www.customs.go.kr/kcs/ad/exp/expImpPerfList.do"
)
_KITA_STAT_URL = "https://stat.kita.net/stat/kts/ExItemStatsVoCount.screen"


def fetch_customs_monthly(sector: str) -> pd.DataFrame:
    """
    관세청 / 무역협회 월별 수출 데이터 조회.
    공개 API 미인증 시 → 안내 메시지만 반환.

    Returns: DataFrame with [year_month, amount_musd, yoy_pct]
             or empty DataFrame
    """
    # 실제 관세청 공개 API는 인증키 발급 후 사용 가능
    # (unipass.customs.go.kr → 개발자 포털 → API 신청)
    # MVP: 빈 DataFrame 반환, UI에서 안내 표시
    return pd.DataFrame()


def scrape_kita_export(hs_code: str, months: int = 12) -> pd.DataFrame:
    """
    한국무역협회(KITA) 수출 통계 스크래핑 시도.
    실패 시 빈 DataFrame 반환.
    """
    try:
        end_ym   = datetime.today().strftime("%Y%m")
        start_ym = (datetime.today() - timedelta(days=months * 31)).strftime("%Y%m")

        url = (
            f"https://stat.kita.net/stat/kts/ExItemStatsVoCount.screen"
            f"?hsCd={hs_code}&startYm={start_ym}&endYm={end_ym}"
        )
        resp = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        if resp.status_code != 200:
            return pd.DataFrame()

        tables = pd.read_html(resp.text, flavor="lxml")
        for t in tables:
            if len(t) > 3 and t.shape[1] >= 3:
                return t
    except Exception:
        pass
    return pd.DataFrame()


# ── 차트 ─────────────────────────────────────────────────────────────────────

def plot_trend_vs_price(
    trend_df: pd.DataFrame,
    price_df: pd.DataFrame,
    ticker: str = "",
    title: str = "검색 트렌드 vs 주가",
    show: bool = True,
) -> go.Figure:
    """
    검색 트렌드(오른쪽 보조축) vs 주가(왼쪽 주축) 이중축 차트.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 주가 (주축)
    if not price_df.empty:
        price_weekly = price_df["Close"].resample("W").last().dropna()
        fig.add_trace(go.Scatter(
            x=price_weekly.index, y=price_weekly.values,
            name=f"{ticker} 주가",
            line=dict(color="#60a5fa", width=2.2),
            fill="tozeroy",
            fillcolor="rgba(96,165,250,0.06)",
        ), secondary_y=False)

    # 검색 트렌드 (보조축)
    palette = ["#f59e0b", "#a78bfa", "#34d399", "#f87171", "#fb923c"]
    for i, col in enumerate(trend_df.columns):
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=trend_df.index, y=trend_df[col],
            name=f"🔍 {col}",
            line=dict(color=color, width=1.8, dash="dot"),
        ), secondary_y=True)

    fig.update_layout(
        height=420,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="Noto Sans KR", color="#e2e8f0"),
        title=dict(text=title, font=dict(size=14)),
        legend=dict(
            orientation="h", y=1.05, x=0,
            bgcolor="rgba(0,0,0,0)", font_size=11,
        ),
        margin=dict(l=0, r=0, t=55, b=0),
    )
    fig.update_yaxes(
        title_text="주가 (원)",
        secondary_y=False,
        showgrid=True,
        gridcolor="rgba(255,255,255,0.05)",
    )
    fig.update_yaxes(
        title_text="검색량 지수 (0~100)",
        secondary_y=True,
        showgrid=False,
        range=[0, 110],
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    if show:
        fig.show()
    return fig


def plot_lead_lag(lead_lag_df: pd.DataFrame, show: bool = True) -> go.Figure:
    """
    리드-래그 상관 계수 막대 차트.
    x축: lag (주), y축: 상관계수
    """
    if lead_lag_df.empty:
        return go.Figure()

    palette = ["#f59e0b", "#a78bfa", "#34d399", "#f87171", "#fb923c"]
    fig = go.Figure()

    for i, col in enumerate(lead_lag_df.columns):
        series = lead_lag_df[col].dropna()
        fig.add_trace(go.Bar(
            x=series.index, y=series.values,
            name=col,
            marker_color=palette[i % len(palette)],
            opacity=0.8,
        ))

    fig.add_vline(x=0, line=dict(color="#64748b", dash="dash", width=1))
    fig.add_hline(y=0,  line=dict(color="#475569", width=1))

    fig.update_layout(
        height=300,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="Noto Sans KR", color="#e2e8f0"),
        title=dict(
            text="리드-래그 상관 분석  (lag < 0: 검색량이 주가보다 선행)",
            font=dict(size=13),
        ),
        barmode="group",
        legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=55, b=0),
        xaxis=dict(title="Lag (주)", dtick=2),
        yaxis=dict(title="상관계수", range=[-1, 1]),
    )

    if show:
        fig.show()
    return fig
