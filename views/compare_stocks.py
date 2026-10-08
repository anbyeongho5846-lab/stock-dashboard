"""페이지: 종목 비교 — 2~4개 종목을 지표·밸류에이션·정규화 주가로 비교."""

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import (
    page_header, chip, detect_market, now_kst,
    fmt_market_cap, fmt_volume,
    _color_change, _color_opinion, _color_result, _color_excess, _color_pnl,
    cached_rankings, cached_sector, cached_stock, cached_fundamental,
    cached_ownership, cached_price_kr, cached_sector_detail, cached_scan,
    cached_news, _render_news,
    stock_picker, goto_stock, kr_stock_labels,
)

_DEFAULTS = ["005930", "000660", "035420", "005380"]


def _kr_name(ticker: str) -> str:
    for lab in kr_stock_labels():
        if lab.endswith(f"({ticker})"):
            return lab.rsplit("(", 1)[0].strip()
    return ticker


def _collect(ticker: str, is_kr: bool, days: int) -> dict | None:
    df = cached_stock(ticker, is_kr, days)
    if df.empty:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    def _v(k):
        x = last.get(k)
        return float(x) if x is not None and pd.notna(x) else None

    ma5, ma20, ma60 = _v("MA5"), _v("MA20"), _v("MA60")
    if None not in (ma5, ma20, ma60):
        arrange = "🔴 정배열" if ma5 > ma20 > ma60 else ("🔵 역배열" if ma5 < ma20 < ma60 else "⬜ 혼합")
    else:
        arrange = "-"

    info = {}
    d = cached_fundamental(ticker, is_kr, 2)
    if d:
        info = d.get("info", {}) or {}

    sent = "-"
    try:
        _i, _s, summ = cached_news(ticker, "", is_kr)
        if summ:
            sent = {"positive": "🟢 긍정", "negative": "🔴 부정",
                    "neutral": "⬜ 중립"}.get(summ.get("overall"), "-")
    except Exception:
        pass

    change = (last["Close"] - prev["Close"]) / prev["Close"] * 100 if prev["Close"] else 0
    return {
        "name": _kr_name(ticker) if is_kr else (info.get("shortName") or ticker),
        "ticker": ticker, "is_kr": is_kr,
        "close": float(last["Close"]), "change": change,
        "rsi": _v("RSI"), "arrange": arrange,
        "per": info.get("trailingPE") or info.get("forwardPE"),
        "pbr": info.get("priceToBook"),
        "roe": info.get("returnOnEquity"),
        "mktcap": info.get("marketCap"),
        "sentiment": sent,
        "series": df["Close"],
    }


def show_compare_stocks():
    page_header("⚖️", "종목 비교",
                "2~4개 종목의 지표·밸류에이션과 주가 흐름을 나란히 비교합니다.")

    with st.expander("💡 이 화면 보는 법", expanded=False):
        st.markdown(
            "- 비교할 종목을 2~4개 고르면, **지표·밸류에이션 표**와 **정규화 주가 그래프**가 나옵니다.\n"
            "- 주가 그래프는 **시작일을 100으로 맞춰** 같은 출발선에서 누가 더 올랐는지 비교합니다.\n"
            "- 더 깊은 비교는 **🗣️ AI 투자 비서**에서 두 종목을 골라 물어보세요."
        )

    cnum, cday = st.columns([2, 3])
    with cnum:
        n = st.slider("비교 종목 수", 2, 4, 2, key="cmp_n")
    with cday:
        days = st.slider("비교 기간 (일)", 60, 365, 180, key="cmp_days")

    cols = st.columns(n)
    stocks = []
    for i in range(n):
        with cols[i]:
            t, k = stock_picker(f"cmp{i}", default_code=_DEFAULTS[i], label=f"종목 {i + 1}")
            if t.strip():
                stocks.append((t.strip().upper(), k))

    if len(stocks) < 2:
        st.info("비교할 종목을 2개 이상 선택하세요.")
        return

    with st.spinner("종목 데이터 수집 중..."):
        data = [d for d in (_collect(t, k, days) for t, k in stocks) if d]

    if len(data) < 2:
        st.error("데이터를 가져오지 못한 종목이 있습니다. 종목 코드를 확인하세요.")
        return

    # ── 정규화 주가 비교 차트 ───────────────────────────────────────────────────
    chip("주가 흐름 비교 (시작일 = 100)")
    palette = ["#60a5fa", "#34d399", "#f4a261", "#e879f9"]
    fig = go.Figure()
    for i, d in enumerate(data):
        s = d["series"].dropna()
        if s.empty:
            continue
        base = float(s.iloc[0]) or 1
        fig.add_trace(go.Scatter(
            x=s.index, y=(s / base * 100).round(2),
            mode="lines", name=d["name"],
            line=dict(color=palette[i % len(palette)], width=2.2),
        ))
    fig.add_hline(y=100, line_dash="dash", line_color="rgba(255,255,255,0.2)")
    fig.update_layout(
        height=420, template="plotly_dark",
        yaxis_title="지수 (시작=100)", legend=dict(orientation="h", y=1.02),
        margin=dict(t=40, b=30),
    )
    st.plotly_chart(fig, width="stretch")

    # ── 지표·밸류에이션 비교 표 ─────────────────────────────────────────────────
    chip("지표 · 밸류에이션 비교")

    def _per(v):   return f"{v:.1f}배" if isinstance(v, (int, float)) else "-"
    def _pbr(v):   return f"{v:.2f}배" if isinstance(v, (int, float)) else "-"
    def _roe(v):   return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "-"
    def _rsi(v):   return f"{v:.1f}" if isinstance(v, (int, float)) else "-"
    def _cap(v):   return fmt_market_cap(v) if isinstance(v, (int, float)) else "-"

    rows = {
        "현재가":   [f"{d['close']:,.0f}" for d in data],
        "전일대비": [f"{d['change']:+.2f}%" for d in data],
        "RSI(14)":  [_rsi(d["rsi"]) for d in data],
        "MA 배열":  [d["arrange"] for d in data],
        "PER":      [_per(d["per"]) for d in data],
        "PBR":      [_pbr(d["pbr"]) for d in data],
        "ROE":      [_roe(d["roe"]) for d in data],
        "시가총액": [_cap(d["mktcap"]) for d in data],
        "뉴스 분위기": [d["sentiment"] for d in data],
    }
    tbl = pd.DataFrame(rows, index=[f"{d['name']}\n({d['ticker']})" for d in data]).T
    st.dataframe(tbl, width="stretch")
    st.caption("※ PER·PBR·ROE·시가총액은 yfinance 기준이며 국내 종목은 일부 값이 없을 수 있습니다.")
