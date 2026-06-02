"""
스마트 머니 추적 + 매물대(Volume Profile) 분석
- Volume Profile: OHLCV에서 가격대별 거래량 분포 계산
- 핵심 가격대(POC, 저항·지지) 추출
- 매물대 돌파 신호 탐지
- 외국인/기관 순매수 추이 (pykrx, 로컬 전용)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── 투자자별 매매 동향 (pykrx) ─────────────────────────────────────────────────

def fetch_investor_flow(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    외국인 / 기관 / 개인 순매수 금액.
    pykrx 사용 → Streamlit Cloud에서는 빈 DataFrame 반환.

    Returns: index=date, columns 포함 [개인, 기관합계, 외국인합계]
    """
    from datetime import datetime, timedelta

    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days + 20)).strftime("%Y%m%d")

    try:
        from pykrx import stock as krx
        df = krx.get_market_trading_value_by_date(start, end, ticker)
        if df is None or df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        # 컬럼 정규화 (pykrx 버전별로 이름이 다를 수 있음)
        rename = {}
        for c in df.columns:
            if "개인" in c:   rename[c] = "개인"
            elif "기관" in c: rename[c] = "기관합계"
            elif "외국인" in c: rename[c] = "외국인합계"
        df = df.rename(columns=rename)
        keep = [c for c in ["개인", "기관합계", "외국인합계"] if c in df.columns]
        return df[keep].tail(days)
    except Exception:
        return pd.DataFrame()


# ── Volume Profile ────────────────────────────────────────────────────────────

def calc_volume_profile(df: pd.DataFrame, bins: int = 40) -> pd.DataFrame:
    """
    OHLCV → 가격대별 거래량 분포 (Volume Profile).
    각 봉의 거래량을 고가~저가 구간에 균등 배분합니다.

    Returns DataFrame: [price_low, price_high, price_mid, volume, pct]
    """
    if df.empty:
        return pd.DataFrame()

    price_min = float(df["Low"].min())
    price_max = float(df["High"].max())
    if price_min >= price_max:
        return pd.DataFrame()

    edges   = np.linspace(price_min, price_max, bins + 1)
    volumes = np.zeros(bins)

    for _, row in df.iterrows():
        lo  = float(row["Low"])
        hi  = float(row["High"])
        vol = float(row["Volume"])
        if pd.isna(lo) or pd.isna(hi) or pd.isna(vol) or hi <= lo:
            continue
        overlap = np.where((edges[1:] >= lo) & (edges[:-1] <= hi))[0]
        if len(overlap):
            volumes[overlap] += vol / len(overlap)

    total = volumes.sum()
    pct   = (volumes / total * 100) if total else np.zeros(bins)

    return pd.DataFrame({
        "price_low":  edges[:-1],
        "price_high": edges[1:],
        "price_mid":  (edges[:-1] + edges[1:]) / 2,
        "volume":     volumes,
        "pct":        pct,
    })


def find_key_levels(vp: pd.DataFrame, cur_price: float, top_n: int = 5) -> dict:
    """
    Volume Profile에서 핵심 가격대 추출.

    Returns:
        poc        : Point of Control (최다 거래 가격대)
        resistance : 현재가 위 주요 매물대 (저항선)
        support    : 현재가 아래 주요 매물대 (지지선)
    """
    if vp.empty:
        return {"poc": None, "resistance": [], "support": []}

    poc_price = float(vp.loc[vp["volume"].idxmax(), "price_mid"])

    top_prices = vp.nlargest(top_n, "volume")["price_mid"].tolist()
    resistance = sorted([p for p in top_prices if p > cur_price])
    support    = sorted([p for p in top_prices if p <= cur_price], reverse=True)

    return {"poc": poc_price, "resistance": resistance, "support": support}


def detect_breakout(df: pd.DataFrame, key_levels: dict) -> dict:
    """
    현재가가 주요 매물대(저항선)를 거래량 급증과 함께 돌파하는지 탐지.

    Returns:
        signals  : list of signal dicts
        vol_ratio: 현재 거래량 / 20일 평균 거래량
    """
    if df.empty:
        return {"signals": [], "vol_ratio": 1.0}

    cur_price = float(df["Close"].iloc[-1])
    cur_vol   = float(df["Volume"].iloc[-1])
    avg_vol_s = df["Volume"].rolling(20).mean()
    avg_vol   = float(avg_vol_s.iloc[-1]) if not avg_vol_s.isna().all() else 1.0
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

    signals = []
    for lvl in key_levels.get("resistance", []):
        proximity = abs(cur_price - lvl) / lvl if lvl else 1
        if proximity < 0.03:   # 현재가와 3% 이내
            strength = "강" if vol_ratio >= 2.0 else ("중" if vol_ratio >= 1.5 else "약")
            sig_type = (
                "🚀 매물대 돌파 (강한 거래량)" if vol_ratio >= 1.5
                else "⚠️ 매물대 접근 (거래량 확인 필요)"
            )
            signals.append({
                "level":     round(lvl, 0),
                "type":      sig_type,
                "vol_ratio": round(vol_ratio, 2),
                "strength":  strength,
            })

    return {"signals": signals, "vol_ratio": round(vol_ratio, 2)}


# ── 스마트 머니 점수 ──────────────────────────────────────────────────────────

def smart_money_score(investor_df: pd.DataFrame, days_check: int = 5) -> dict:
    """
    외국인 + 기관 누적 순매수로 스마트 머니 점수(0~100) 산출.
    개인이 팔고 기관+외인이 사는 '쌍끌이' 패턴을 포착합니다.
    """
    if investor_df.empty:
        return {"score": None, "label": "데이터 없음", "detail": ""}

    recent = investor_df.tail(days_check)

    foreign_net = float(recent.get("외국인합계", pd.Series([0])).sum())
    institute_net = float(recent.get("기관합계", pd.Series([0])).sum())
    individual_net = float(recent.get("개인", pd.Series([0])).sum())

    smart_net = foreign_net + institute_net   # 스마트 머니 합산
    total_abs = abs(foreign_net) + abs(institute_net) + abs(individual_net)

    if total_abs == 0:
        return {"score": 50, "label": "중립", "detail": ""}

    # 점수 산식: 스마트머니가 강하게 순매수하고 개인이 순매도할 때 최고점
    raw = smart_net / total_abs  # -1 ~ 1
    # 개인 역방향 보너스
    if individual_net < 0 and smart_net > 0:
        raw = min(1.0, raw * 1.3)   # 쌍끌이 보너스

    score = int(round((raw + 1) / 2 * 100))   # 0~100
    score = max(0, min(100, score))

    if score >= 75:   label = "🟢 강한 매집"
    elif score >= 60: label = "🔵 매집 신호"
    elif score >= 40: label = "⬜ 중립"
    elif score >= 25: label = "🟠 분산 신호"
    else:              label = "🔴 강한 분산"

    billion = 1e8
    detail = (
        f"외국인 {foreign_net/billion:+,.0f}억  "
        f"기관 {institute_net/billion:+,.0f}억  "
        f"개인 {individual_net/billion:+,.0f}억  ({days_check}일 누계)"
    )
    return {"score": score, "label": label, "detail": detail}


# ── 차트 ─────────────────────────────────────────────────────────────────────

def plot_smart_money(
    df: pd.DataFrame,
    vp: pd.DataFrame,
    investor_df: pd.DataFrame,
    key_levels: dict,
    title: str = "",
    show: bool = True,
) -> go.Figure:
    """
    상단: 캔들차트 (75%) + Volume Profile 수평 막대 (25%), Y축 공유
    하단: 투자자별 순매수 막대 (억원)
    """
    has_investor = not investor_df.empty
    row_heights  = [0.62, 0.38] if has_investor else [1.0]
    n_rows       = 2 if has_investor else 1

    # ── 서브플롯: 가격(col1) + Volume Profile(col2) ───────────────────────────
    #  shared_yaxes='rows'이면 같은 행의 y축을 공유 → VP가 가격축에 정렬됨
    fig = make_subplots(
        rows=n_rows, cols=2,
        column_widths=[0.74, 0.26],
        row_heights=row_heights,
        shared_yaxes=True,         # 같은 행: y축 공유 (가격 정렬)
        shared_xaxes=False,
        vertical_spacing=0.05,
        horizontal_spacing=0.005,
        subplot_titles=(
            f"{title}",
            "Volume Profile",
            "투자자별 순매수 (억원)" if has_investor else "",
            "",
        ),
    )

    # ── [1,1] 캔들스틱 ────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        name="주가", showlegend=False,
    ), row=1, col=1)

    # POC 라인
    poc = key_levels.get("poc")
    if poc:
        fig.add_hline(
            y=poc, row=1, col=1,
            line=dict(color="#facc15", width=1.5, dash="dot"),
            annotation_text=f"POC {poc:,.0f}",
            annotation_position="left",
            annotation_font_size=9, annotation_font_color="#facc15",
        )

    # 저항선
    for lvl in key_levels.get("resistance", [])[:3]:
        fig.add_hline(
            y=lvl, row=1, col=1,
            line=dict(color="#f87171", width=0.8, dash="dash"),
            annotation_text=f"R {lvl:,.0f}",
            annotation_position="right",
            annotation_font_size=8, annotation_font_color="#f87171",
        )

    # 지지선
    for lvl in key_levels.get("support", [])[:3]:
        fig.add_hline(
            y=lvl, row=1, col=1,
            line=dict(color="#34d399", width=0.8, dash="dash"),
            annotation_text=f"S {lvl:,.0f}",
            annotation_position="right",
            annotation_font_size=8, annotation_font_color="#34d399",
        )

    # ── [1,2] Volume Profile 수평 막대 ────────────────────────────────────────
    if not vp.empty:
        poc_idx = int(vp["volume"].idxmax())
        bar_colors = [
            "#facc15" if i == poc_idx else "#3b82f6"
            for i in vp.index
        ]
        fig.add_trace(go.Bar(
            x=vp["volume"],
            y=vp["price_mid"],
            orientation="h",
            marker_color=bar_colors,
            marker_line_width=0,
            name="거래량 프로파일",
            showlegend=False,
            width=(vp["price_high"] - vp["price_low"]).mean() * 0.9,
        ), row=1, col=2)

    # ── [2,1] 투자자별 순매수 ─────────────────────────────────────────────────
    if has_investor:
        inv_colors = {
            "개인":     "#94a3b8",
            "기관합계": "#60a5fa",
            "외국인합계": "#34d399",
        }
        for col_name, color in inv_colors.items():
            if col_name in investor_df.columns:
                vals = investor_df[col_name] / 1e8   # 억원 단위
                fig.add_trace(go.Bar(
                    x=investor_df.index,
                    y=vals,
                    name=col_name,
                    marker_color=color,
                    marker_line_width=0,
                ), row=2, col=1)

    fig.update_layout(
        height=600 if has_investor else 420,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="Noto Sans KR", color="#e2e8f0"),
        xaxis_rangeslider_visible=False,
        barmode="group",
        legend=dict(
            orientation="h", y=1.05, x=0,
            bgcolor="rgba(0,0,0,0)", font_size=11,
        ),
        margin=dict(l=0, r=80, t=60, b=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    # Volume Profile x축 레이블 숨김
    fig.update_xaxes(showticklabels=False, row=1, col=2)

    if show:
        fig.show()
    return fig
