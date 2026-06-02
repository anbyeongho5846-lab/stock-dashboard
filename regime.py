"""
시장 국면 판별기 (Market Regime Filter)
ADX + 이동평균 정배열/역배열로 현재 시장 국면을 진단하고
국면에 맞는 적합한 지표 조합을 추천합니다.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── ADX 계산 (Wilder's Smoothing) ─────────────────────────────────────────────

def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX / +DI / -DI 계산.
    Wilder's 지수평활 (alpha = 1/period) 방식.
    """
    high  = df["High"].astype(float)
    low   = df["Low"].astype(float)
    close = df["Close"].astype(float)

    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high   - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm  = pd.Series(
        np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    # Wilder Smoothing (EWM with alpha = 1/period)
    alpha      = 1.0 / period
    atr        = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    s_plus_dm  = plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    s_minus_dm = minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    plus_di  = 100 * s_plus_dm  / atr.replace(0, np.nan)
    minus_di = 100 * s_minus_dm / atr.replace(0, np.nan)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    return pd.DataFrame({
        "ADX":      adx,
        "Plus_DI":  plus_di,
        "Minus_DI": minus_di,
    }, index=df.index)


# ── 국면 메타 정의 ─────────────────────────────────────────────────────────────

_REGIME_META = {
    "trending_bull": {
        "label":   "🟢 강세 추세 (Trending Bull)",
        "color":   "#22c55e",
        "bg":      "rgba(34,197,94,0.10)",
        "desc":    "ADX ≥ 25이고 +DI > -DI. 상승 추세가 명확합니다.\n추세 추종 전략이 유리하며, 역추세 매도는 피하세요.",
        "active":  ["이동평균 돌파 (MA5 > MA20 > MA60)", "MACD 골든크로스", "거래량 동반 상승 확인"],
        "avoid":   ["RSI 과매수 역매도", "볼린저밴드 상단 반전 매도", "스토캐스틱 역추세"],
    },
    "trending_bear": {
        "label":   "🔴 약세 추세 (Trending Bear)",
        "color":   "#ef4444",
        "bg":      "rgba(239,68,68,0.10)",
        "desc":    "ADX ≥ 25이고 -DI > +DI. 하락 추세가 강합니다.\n신규 매수보다 헤지·현금화를 고려하세요.",
        "active":  ["이동평균 데드크로스 확인", "MACD 데드크로스", "손절 기준 설정"],
        "avoid":   ["저점 매수(낙폭과대) 전략", "RSI 과매도 반등 매수"],
    },
    "ranging": {
        "label":   "⬜ 박스권 (Ranging)",
        "color":   "#94a3b8",
        "bg":      "rgba(148,163,184,0.08)",
        "desc":    "ADX < 25. 뚜렷한 방향성이 없는 박스권입니다.\n오실레이터 기반 역추세 전략이 유리합니다.",
        "active":  ["RSI 30 이하 매수 / 70 이상 매도", "스토캐스틱 과매수·과매도", "볼린저밴드 하단 반등"],
        "avoid":   ["이동평균 돌파 추종", "MACD 추세 추종 (잦은 가짜 신호)"],
    },
}


# ── 국면 탐지 ─────────────────────────────────────────────────────────────────

def detect_regime(df: pd.DataFrame, period: int = 14) -> dict:
    """
    시장 국면 판별.

    Returns dict:
        regime         : 'trending_bull' | 'trending_bear' | 'ranging' | 'unknown'
        adx            : float
        plus_di        : float
        minus_di       : float
        ma_align       : 'bullish' | 'bearish' | 'mixed'
        strength       : 'strong' | 'moderate' | 'weak'
        adx_series     : pd.Series
        plus_di_series : pd.Series
        minus_di_series: pd.Series
        meta           : dict (label, color, desc, active, avoid)
    """
    if len(df) < period * 4:
        return {"regime": "unknown", "adx": None, "meta": _REGIME_META["ranging"]}

    df = df.copy()
    for w in (5, 20, 60):
        df[f"MA{w}"] = df["Close"].rolling(w).mean()

    adx_df = calc_adx(df, period)

    last     = adx_df.iloc[-1]
    adx_val  = float(last["ADX"])
    plus_di  = float(last["Plus_DI"])
    minus_di = float(last["Minus_DI"])

    # MA 정배열 / 역배열
    ma5 = float(df["MA5"].iloc[-1])
    ma20= float(df["MA20"].iloc[-1])
    ma60= float(df["MA60"].iloc[-1])
    if   ma5 > ma20 > ma60: ma_align = "bullish"
    elif ma5 < ma20 < ma60: ma_align = "bearish"
    else:                    ma_align = "mixed"

    # 국면 판별
    if adx_val >= 25:
        regime   = "trending_bull" if plus_di >= minus_di else "trending_bear"
        strength = "strong" if adx_val >= 40 else "moderate"
    else:
        regime   = "ranging"
        strength = "weak"

    return {
        "regime":          regime,
        "adx":             round(adx_val, 2),
        "plus_di":         round(plus_di, 2),
        "minus_di":        round(minus_di, 2),
        "ma_align":        ma_align,
        "strength":        strength,
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "adx_series":      adx_df["ADX"],
        "plus_di_series":  adx_df["Plus_DI"],
        "minus_di_series": adx_df["Minus_DI"],
        "meta":            _REGIME_META[regime],
    }


# ── 차트 ─────────────────────────────────────────────────────────────────────

def plot_regime(
    df: pd.DataFrame,
    result: dict,
    title: str = "",
    show: bool = True,
) -> go.Figure:
    """
    국면 판별 차트.
    Row 1: 캔들 + 이동평균 (배경색으로 국면 표시)
    Row 2: ADX / +DI / -DI 라인 + 기준선 25·40
    """
    meta = result.get("meta", _REGIME_META["ranging"])

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            f"{title} — 주가 & 이동평균 ({meta['label']})",
            "ADX / +DI / −DI",
        ),
        row_heights=[0.62, 0.38],
    )

    # ── 캔들스틱 ──────────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        name="주가", showlegend=False,
    ), row=1, col=1)

    # 이동평균선
    ma_style = {
        "MA5":  ("#f4a261", 1.2),
        "MA20": ("#457b9d", 1.5),
        "MA60": ("#9b2226", 1.5),
    }
    for col, (color, width) in ma_style.items():
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col],
                line=dict(color=color, width=width),
                name=col,
            ), row=1, col=1)

    # ── ADX / DI ─────────────────────────────────────────────────────────────
    adx_s = result.get("adx_series")
    pdi_s = result.get("plus_di_series")
    mdi_s = result.get("minus_di_series")

    if adx_s is not None:
        fig.add_trace(go.Scatter(
            x=adx_s.index, y=adx_s.round(2),
            line=dict(color="#a78bfa", width=2.2),
            name="ADX",
        ), row=2, col=1)
    if pdi_s is not None:
        fig.add_trace(go.Scatter(
            x=pdi_s.index, y=pdi_s.round(2),
            line=dict(color="#34d399", width=1.6),
            name="+DI",
        ), row=2, col=1)
    if mdi_s is not None:
        fig.add_trace(go.Scatter(
            x=mdi_s.index, y=mdi_s.round(2),
            line=dict(color="#f87171", width=1.6),
            name="−DI",
        ), row=2, col=1)

    # 기준선
    for lvl, lbl in [(25, "추세 시작(25)"), (40, "강한 추세(40)")]:
        fig.add_hline(
            y=lvl, row=2, col=1,
            line=dict(color="#475569", dash="dash", width=1),
            annotation_text=lbl,
            annotation_position="right",
            annotation_font_size=9,
            annotation_font_color="#64748b",
        )

    fig.update_layout(
        height=560,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="Noto Sans KR", color="#e2e8f0"),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h", y=1.04, x=0,
            bgcolor="rgba(0,0,0,0)", font_size=11,
        ),
        margin=dict(l=0, r=80, t=60, b=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    if show:
        fig.show()
    return fig
