"""페이지: 배당 · 실적 일정 — 종목의 배당 정보와 다가오는 실적 발표일(yfinance)."""

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


@st.cache_data(ttl=3600, show_spinner=False)
def _div_earn(ticker: str, is_kr: bool):
    """yfinance에서 배당·실적 정보 수집. 실패 시 None."""
    import yfinance as yf
    syms = [f"{ticker}.KS", f"{ticker}.KQ"] if is_kr else [ticker]
    for sym in syms:
        try:
            tk = yf.Ticker(sym)
            info = tk.info or {}
            price = (info.get("currentPrice") or info.get("regularMarketPrice")
                     or info.get("previousClose"))
            if is_kr and not price and sym != syms[-1]:
                continue   # 잘못된 접미사 → 다음 시도

            annual = {}
            try:
                d = tk.dividends
                if d is not None and len(d):
                    for idx, v in d.items():
                        annual[idx.year] = annual.get(idx.year, 0.0) + float(v)
            except Exception:
                pass

            earn = exdiv = None
            try:
                cal = tk.calendar
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed:
                        earn = str(ed[0] if isinstance(ed, list) else ed)[:10]
                    xd = cal.get("Ex-Dividend Date")
                    if xd:
                        exdiv = str(xd)[:10]
            except Exception:
                pass

            return {
                "symbol": sym, "price": price,
                "yield": info.get("dividendYield"),
                "rate": info.get("dividendRate"),
                "payout": info.get("payoutRatio"),
                "five": info.get("fiveYearAvgDividendYield"),
                "annual": dict(sorted(annual.items())),
                "earnings_date": earn, "exdiv_date": exdiv,
            }
        except Exception:
            continue
    return None


def show_dividend_calendar():
    page_header("💵", "배당 · 실적 일정",
                "종목의 배당 정보(수익률·이력)와 다가오는 실적 발표일을 확인합니다.")

    with st.expander("💡 용어 쉽게 이해하기", expanded=False):
        st.markdown(
            "- **배당수익률**: 주가 대비 1년 배당금 비율. 예금 이자처럼 '주식이 주는 이자'로 보면 됩니다.\n"
            "- **배당성향**: 회사가 번 이익 중 배당으로 나눠준 비율. 너무 높으면 무리한 배당일 수 있습니다.\n"
            "- **배당락일**: 이 날 이전까지 보유해야 다음 배당을 받습니다.\n"
            "- **실적 발표일**: 분기 성적표가 나오는 날. 주가가 크게 움직일 수 있어 미리 알아두면 좋습니다."
        )

    ticker, is_kr = stock_picker("div", default_code="005930")
    if not ticker.strip():
        st.info("종목을 선택하세요.")
        return

    with st.spinner("배당·실적 정보 수집 중..."):
        data = _div_earn(ticker.strip().upper(), is_kr)

    if not data:
        st.error("데이터를 가져오지 못했습니다. 종목 코드를 확인하세요.")
        return

    cur = "원" if is_kr else "$"
    name = ticker.strip().upper()
    if is_kr:
        for lab in kr_stock_labels():
            if lab.endswith(f"({name})"):
                name = lab.rsplit("(", 1)[0].strip()
                break
    st.markdown(f"**{name}** `{data['symbol']}`")

    # ── 배당 지표 ────────────────────────────────────────────────────────────
    chip("배당 지표")
    c1, c2, c3, c4 = st.columns(4)
    y = data["yield"]
    c1.metric("💰 배당수익률", f"{y:.2f}%" if isinstance(y, (int, float)) else "무배당")
    r = data["rate"]
    c2.metric("📈 주당 배당금", f"{r:,.0f}{cur}" if isinstance(r, (int, float)) else "-")
    po = data["payout"]
    c3.metric("📊 배당성향", f"{po * 100:.1f}%" if isinstance(po, (int, float)) else "-")
    fv = data["five"]
    c4.metric("📅 5년 평균 수익률", f"{fv:.2f}%" if isinstance(fv, (int, float)) else "-")

    # ── 일정 ─────────────────────────────────────────────────────────────────
    chip("다가오는 일정")
    d1, d2 = st.columns(2)
    d1.metric("🗓️ 다음 실적 발표일", data["earnings_date"] or "미정")
    d2.metric("🔖 배당락일", data["exdiv_date"] or "-")

    # ── 연간 배당 이력 ──────────────────────────────────────────────────────────
    chip("연간 배당금 추이")
    annual = {k: v for k, v in data["annual"].items() if k >= (now_kst().year - 10)}
    if not annual:
        st.info("배당 지급 이력이 없습니다. (무배당 종목이거나 데이터가 없습니다)")
    else:
        years = list(annual.keys())
        vals = [round(annual[y], 2) for y in years]
        fig = go.Figure(go.Bar(
            x=[str(y) for y in years], y=vals, marker_color="#60a5fa",
            text=[f"{v:,.0f}{cur}" for v in vals], textposition="outside",
            hovertemplate="%{x}년<br>주당 %{y:,.0f}" + cur + "<extra></extra>",
        ))
        fig.update_layout(
            height=360, template="plotly_dark",
            title=dict(text="연도별 주당 배당금", font=dict(size=15)),
            yaxis_title=f"주당 배당금({cur})", margin=dict(t=50, b=30),
        )
        st.plotly_chart(fig, width="stretch")

    st.caption("※ 배당·실적 데이터는 yfinance 기준이며, 국내 종목은 일부 정보가 없거나 지연될 수 있습니다.")
