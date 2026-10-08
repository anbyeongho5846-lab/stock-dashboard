"""페이지: 종목 분석 — 캔들차트 + 기술지표 + 뉴스."""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from common import (
    page_header, chip, detect_market, now_kst,
    fmt_market_cap, fmt_volume,
    _color_change, _color_opinion, _color_result, _color_excess, _color_pnl,
    cached_rankings, cached_sector, cached_stock, cached_fundamental,
    cached_ownership, cached_price_kr, cached_sector_detail, cached_scan,
    cached_news, _render_news,
    stock_picker, goto_stock,
)


def show_analyzer():
    page_header("📈", "종목 분석",
                "캔들차트와 이동평균선(MA5·20·60·120), RSI, MACD, 볼린저밴드, 거래량을 한눈에 확인합니다.")

    with st.expander("💡 이 화면 보는 법 (지표 설명)", expanded=False):
        st.markdown(
            "- **이동평균선(MA)**: 최근 N일 평균 가격. 단기선(MA5)이 장기선(MA20·60) 위에 있으면 상승 흐름(정배열)입니다.\n"
            "- **RSI**: 0~100 수치. 70 이상이면 과열(과매수), 30 이하면 침체(과매도) 신호로 봅니다.\n"
            "- **MACD**: 양수(+)면 상승 탄력, 음수(−)면 하락 탄력을 뜻합니다.\n"
            "- 아래 **🤖 AI 리포트**를 누르면 이 지표들과 뉴스를 종합해 쉽게 요약해 줍니다."
        )

    col1, col2 = st.columns([5, 5])
    with col1:
        ticker, is_kr = stock_picker("anal", default_code="005930")
    with col2:
        days = st.slider("조회 기간 (일)", 30, 730, 180, key="anal_days")

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
    st.plotly_chart(fig, width="stretch")

    # 최근 5일 가격 테이블
    with st.expander("📋 최근 거래 데이터 (5일)", expanded=False):
        tail5 = df.tail(5).copy()
        disp = tail5[["Open", "High", "Low", "Close", "Volume"]].copy()
        disp.index = disp.index.strftime("%Y-%m-%d")
        disp.columns = ["시가", "고가", "저가", "종가", "거래량"]
        for col in ["시가", "고가", "저가", "종가"]:
            disp[col] = disp[col].apply(lambda v: f"{v:,.0f}")
        disp["거래량"] = disp["거래량"].apply(fmt_volume)
        st.dataframe(disp, width="stretch")

    # ── AI 종합 리포트 ─────────────────────────────────────────────────────────
    st.markdown("---")
    chip("🤖 AI 종합 리포트")
    _render_ai_report(ticker.strip().upper(), is_kr, int(days))

    # ── 뉴스 피드 ──────────────────────────────────────────────────────────────
    st.markdown("---")
    chip("📰 관련 뉴스 & 감성 분석")
    _render_news(ticker.strip().upper(), corp_name="", is_kr=is_kr)


# ── AI 리포트 ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)   # 종목별 6시간 캐시 (비용 최소화)
def cached_ai_report(ticker: str, is_kr: bool, days: int) -> str:
    """차트 지표 + 뉴스 감성을 모아 Gemini로 리포트 생성. 키 없으면 빈 문자열."""
    try:
        api_key = st.secrets["gemini"]["api_key"]
    except Exception:
        return ""
    if not api_key:
        return ""

    df = cached_stock(ticker, is_kr, days)
    if df.empty:
        return ""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    def _num(key):
        v = last.get(key)
        return round(float(v), 2) if v is not None and pd.notna(v) else None

    change = (round((last["Close"] - prev["Close"]) / prev["Close"] * 100, 2)
              if prev["Close"] else 0.0)

    data = {
        "현재가": round(float(last["Close"]), 2),
        "전일대비_%": change,
        "RSI14": _num("RSI"),
        "MA5": _num("MA5"), "MA20": _num("MA20"), "MA60": _num("MA60"),
        "MACD": _num("MACD"),
        "조회_거래일수": int(len(df)),
    }

    # 뉴스 감성 (있으면 추가)
    try:
        _items, _src, summ = cached_news(ticker, "", is_kr)
        if summ:
            data["뉴스감성"] = {
                "긍정": summ.get("positive"), "부정": summ.get("negative"),
                "중립": summ.get("neutral"), "종합": summ.get("overall"),
            }
    except Exception:
        pass

    # 국내 종목명 (kr_tickers에서 조회)
    name = ticker
    if is_kr:
        try:
            from common import kr_stock_labels
            for lab in kr_stock_labels():
                if lab.endswith(f"({ticker})"):
                    name = lab.rsplit("(", 1)[0].strip()
                    break
        except Exception:
            pass

    from ai_report import generate_stock_report
    return generate_stock_report(ticker, name, data, api_key)


def _render_ai_report(ticker: str, is_kr: bool, days: int) -> None:
    from ai_report import DISCLAIMER

    try:
        has_key = bool(st.secrets["gemini"]["api_key"])
    except Exception:
        has_key = False

    if not has_key:
        st.info(
            "💡 **AI 리포트는 선택 기능입니다.** Gemini API 키를 설정하면 차트·지표·뉴스를 "
            "종합한 요약 리포트를 생성합니다.  \n"
            "`.streamlit/secrets.toml`(로컬)과 Streamlit Cloud의 *Settings → Secrets* 에 "
            "아래를 추가하세요:\n"
            "```toml\n[gemini]\napi_key = \"발급받은_키\"\n```"
        )
        return

    if st.button("🤖 AI 리포트 생성", key="ai_report_btn"):
        st.session_state["ai_report_for"] = ticker

    if st.session_state.get("ai_report_for") == ticker:
        with st.spinner("AI가 지표와 뉴스를 분석하고 있습니다..."):
            report = cached_ai_report(ticker, is_kr, days)
        if report:
            with st.container(border=True):
                st.markdown(report)
            st.caption("ℹ️ " + DISCLAIMER)
        else:
            st.warning("리포트를 생성하지 못했습니다. 종목 데이터 또는 API 키를 확인하세요.")
    else:
        st.caption("버튼을 누르면 현재 종목의 AI 리포트를 생성합니다. (종목별 6시간 캐시)")
