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


# ── 박스권 오실레이터 신호 (볼린저밴드 + 스토캐스틱) ──────────────────────────────

def oscillator_signals(df: pd.DataFrame, regime_result: dict) -> dict:
    """
    볼린저밴드 + 스토캐스틱 역추세 신호.
    국면 필터: 박스권(ranging)일 때만 active=True, 추세 국면이면 신호 비활성화.

    df 는 analyzer.add_indicators() 결과 (BB_*, Stoch_K/D 컬럼 필요).

    Returns dict:
        active        : bool  — 박스권이면 True (신호 유효)
        regime        : str
        reason        : str   — 활성/비활성 사유
        bb            : dict   — 현재 볼린저 상태
        stoch         : dict   — 현재 스토캐스틱 상태
        signals       : list   — 개별 신호 (역추세)
        combined      : dict | None — 볼린저+스토캐스틱 동시 충족 신호
        squeeze       : bool   — 밴드폭 수축 (추세 전환 임박 경고)
    """
    need = ["BB_Upper", "BB_Lower", "BB_Mid", "BB_PctB", "BB_Width",
            "Stoch_K", "Stoch_D", "Close"]
    if df.empty or any(c not in df.columns for c in need):
        return {"active": False, "reason": "지표 데이터 부족", "signals": [],
                "combined": None, "bb": {}, "stoch": {}, "squeeze": False,
                "regime": regime_result.get("regime", "unknown")}

    regime = regime_result.get("regime", "unknown")
    is_ranging = (regime == "ranging")

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    price   = float(last["Close"])
    bb_up   = float(last["BB_Upper"])
    bb_lo   = float(last["BB_Lower"])
    bb_mid  = float(last["BB_Mid"])
    pct_b   = float(last["BB_PctB"])
    width   = float(last["BB_Width"])
    k_now   = float(last["Stoch_K"])
    d_now   = float(last["Stoch_D"])
    k_prev  = float(prev["Stoch_K"])
    d_prev  = float(prev["Stoch_D"])

    # 밴드폭 수축 감지 (최근 20봉 대비 하위 20% 수준이면 squeeze)
    width_series = df["BB_Width"].dropna().tail(20)
    squeeze = bool(len(width_series) >= 10 and
                   width <= width_series.quantile(0.20))

    # ── 스토캐스틱 크로스 판정 ─────────────────────────────────────────────────
    golden_cross = (k_prev <= d_prev) and (k_now > d_now)   # %K가 %D 상향 돌파
    dead_cross   = (k_prev >= d_prev) and (k_now < d_now)   # %K가 %D 하향 돌파

    bb = {
        "price": price, "upper": bb_up, "lower": bb_lo, "mid": bb_mid,
        "pct_b": round(pct_b, 2), "width": round(width, 2),
        "position": ("상단 돌파" if price >= bb_up
                     else "하단 이탈" if price <= bb_lo
                     else "밴드 내부"),
    }
    stoch = {
        "k": round(k_now, 1), "d": round(d_now, 1),
        "zone": ("과매수" if k_now >= 80 else "과매도" if k_now <= 20 else "중립"),
        "cross": ("골든크로스" if golden_cross else "데드크로스" if dead_cross else "—"),
    }

    signals = []

    # ── 개별 신호 ──────────────────────────────────────────────────────────────
    # 볼린저 하단 매수
    if price <= bb_lo:
        signals.append({"type": "buy", "src": "볼린저밴드",
                        "msg": f"종가가 하단밴드({bb_lo:,.0f}) 터치 — 평균회귀 매수 구간"})
    elif price >= bb_up:
        signals.append({"type": "sell", "src": "볼린저밴드",
                        "msg": f"종가가 상단밴드({bb_up:,.0f}) 터치 — 평균회귀 매도 구간"})

    # 스토캐스틱 과매도 골든크로스 / 과매수 데드크로스
    if k_now <= 20 and golden_cross:
        signals.append({"type": "buy", "src": "스토캐스틱",
                        "msg": f"%K({k_now:.0f}) 과매도 + 골든크로스 — 강한 반등 신호"})
    elif k_now <= 20:
        signals.append({"type": "buy", "src": "스토캐스틱",
                        "msg": f"%K({k_now:.0f}) 과매도 구간 — 반등 대기"})
    if k_now >= 80 and dead_cross:
        signals.append({"type": "sell", "src": "스토캐스틱",
                        "msg": f"%K({k_now:.0f}) 과매수 + 데드크로스 — 강한 조정 신호"})
    elif k_now >= 80:
        signals.append({"type": "sell", "src": "스토캐스틱",
                        "msg": f"%K({k_now:.0f}) 과매수 구간 — 차익 대기"})

    # ── 결합 신호 (두 지표 동시 충족 = 고확률) ────────────────────────────────
    combined = None
    bb_buy   = price <= bb_lo
    bb_sell  = price >= bb_up
    st_buy   = k_now <= 20 and golden_cross
    st_sell  = k_now >= 80 and dead_cross
    if bb_buy and st_buy:
        combined = {"type": "buy",
                    "msg": "🚀 볼린저 하단 + 스토캐스틱 과매도 골든크로스 동시 충족 — 박스권 저점 고확률 매수"}
    elif bb_sell and st_sell:
        combined = {"type": "sell",
                    "msg": "🔻 볼린저 상단 + 스토캐스틱 과매수 데드크로스 동시 충족 — 박스권 고점 고확률 매도"}

    # ── 국면 필터 적용 ─────────────────────────────────────────────────────────
    if is_ranging:
        reason = "박스권 국면 → 역추세(평균회귀) 전략 유효"
    else:
        trend_name = "강세 추세" if regime == "trending_bull" else \
                     "약세 추세" if regime == "trending_bear" else "추세"
        reason = (f"{trend_name} 국면 → 역추세 전략 자동 비활성화. "
                  f"추세 추종 지표(MA·MACD)를 사용하세요.")

    return {
        "active":  is_ranging,
        "regime":  regime,
        "reason":  reason,
        "bb":      bb,
        "stoch":   stoch,
        "signals": signals,
        "combined": combined,
        "squeeze": squeeze,
    }


def plot_oscillators(
    df: pd.DataFrame,
    title: str = "",
    show: bool = True,
) -> go.Figure:
    """
    볼린저밴드(가격축) + 스토캐스틱(하단) 차트.
    Row 1: 캔들 + 볼린저밴드 상·중·하단 (밴드 영역 음영)
    Row 2: 스토캐스틱 %K / %D + 20·80 기준선
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            f"{title} — 볼린저밴드 (20, 2σ)",
            "스토캐스틱 (%K 14, %D 3)",
        ),
        row_heights=[0.66, 0.34],
    )

    # ── 볼린저밴드 영역 ────────────────────────────────────────────────────────
    if "BB_Upper" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Upper"],
            line=dict(color="rgba(148,163,184,0.5)", width=1),
            name="상단밴드", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Lower"],
            line=dict(color="rgba(148,163,184,0.5)", width=1),
            fill="tonexty", fillcolor="rgba(99,102,241,0.08)",
            name="하단밴드", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Mid"],
            line=dict(color="#facc15", width=1, dash="dot"),
            name="중심선(MA20)",
        ), row=1, col=1)

    # 캔들스틱
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        name="주가", showlegend=False,
    ), row=1, col=1)

    # ── 스토캐스틱 ─────────────────────────────────────────────────────────────
    if "Stoch_K" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Stoch_K"].round(1),
            line=dict(color="#38bdf8", width=1.6), name="%K",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Stoch_D"].round(1),
            line=dict(color="#fb923c", width=1.4, dash="dot"), name="%D",
        ), row=2, col=1)

    for lvl, color in ((80, "rgba(239,68,68,0.4)"), (20, "rgba(34,197,94,0.4)")):
        fig.add_hline(y=lvl, row=2, col=1,
                      line=dict(color=color, dash="dash", width=1))
    fig.add_hrect(y0=20, y1=80, row=2, col=1,
                  fillcolor="rgba(255,255,255,0.03)", line_width=0)

    fig.update_layout(
        height=560,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="Noto Sans KR", color="#e2e8f0"),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.04, x=0,
                    bgcolor="rgba(0,0,0,0)", font_size=11),
        margin=dict(l=0, r=20, t=60, b=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                     rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(range=[0, 100], row=2, col=1)

    if show:
        fig.show()
    return fig
