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


def _try_sym(sym: str):
    """한 심볼에서 배당/실적 조각을 독립적으로 수집. (성공여부, info, 연간배당, 실적일, 배당락일)."""
    import yfinance as yf
    tk = yf.Ticker(sym)
    info, annual, earn, exdiv, got = {}, {}, None, None, False
    # ① info (quoteSummary — 해외 서버에서 자주 rate-limit됨)
    try:
        info = tk.info or {}
        if len(info) > 5:
            got = True
    except Exception:
        info = {}
    # ② 배당 이력 (chart 엔드포인트 — 클라우드에서도 대체로 동작)
    try:
        d = tk.dividends
        if d is not None and len(d):
            for idx, v in d.items():
                annual[idx.year] = annual.get(idx.year, 0.0) + float(v)
            got = True
    except Exception:
        pass
    # ③ 일정 (calendar — quoteSummary)
    try:
        cal = tk.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                earn = str(ed[0] if isinstance(ed, list) else ed)[:10]; got = True
            xd = cal.get("Ex-Dividend Date")
            if xd:
                exdiv = str(xd)[:10]
    except Exception:
        pass
    return got, info, annual, earn, exdiv


@st.cache_data(ttl=3600, show_spinner=False)
def _div_earn(ticker: str, is_kr: bool):
    """yfinance 배당·실적 정보(항목별 독립·재시도·보완). 전부 실패 시 None."""
    import time
    syms = [f"{ticker}.KS", f"{ticker}.KQ"] if is_kr else [ticker]

    for attempt in range(2):
        for sym in syms:
            try:
                got, info, annual, earn, exdiv = _try_sym(sym)
            except Exception:
                got, info, annual, earn, exdiv = False, {}, {}, None, None

            if is_kr and not got and sym != syms[-1]:
                continue   # 접미사(.KS/.KQ) 틀림 → 다음 시도

            if got:
                price = (info.get("currentPrice") or info.get("regularMarketPrice")
                         or info.get("previousClose"))
                # 가격이 없으면 앱 자체 소스(클라우드에서 동작)로 보완
                if not price:
                    try:
                        df = cached_stock(ticker, is_kr, 10)
                        if not df.empty:
                            price = float(df["Close"].iloc[-1])
                    except Exception:
                        pass
                # info(quoteSummary)가 막혀도 '완전한 최근 연도' 배당 이력으로 보완
                base_div = None
                if annual:
                    import datetime as _dt
                    cur_y = _dt.date.today().year
                    full_years = [yy for yy in sorted(annual) if yy < cur_y]
                    base_y = full_years[-1] if full_years else max(annual)
                    base_div = annual.get(base_y) or None

                dy = info.get("dividendYield")
                if dy is None and base_div and price:
                    dy = round(base_div / price * 100, 2)

                rate = info.get("dividendRate")
                if rate is None and base_div:
                    rate = round(base_div, 2)

                return {
                    "symbol": sym, "price": price,
                    "yield": dy, "rate": rate,
                    "payout": info.get("payoutRatio"),
                    "five": info.get("fiveYearAvgDividendYield"),
                    "annual": dict(sorted(annual.items())),
                    "earnings_date": earn, "exdiv_date": exdiv,
                }
        time.sleep(2)   # rate-limit 완화 후 재시도
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
        st.warning(
            "배당·실적 데이터를 가져오지 못했습니다.  \n"
            "Yahoo Finance가 해외(클라우드) 서버에서 일시적으로 요청을 제한할 때 발생할 수 있습니다. "
            "**잠시 후 다시 시도**하거나, 종목 코드가 맞는지 확인해 주세요."
        )
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
