"""페이지: 종목 스캐너 — 감시 목록 일괄 신호 분석."""

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


_DEFAULT_WATCHLIST = """\
005930,kr   # 삼성전자
000660,kr   # SK하이닉스
035420,kr   # NAVER
035720,kr   # 카카오
207940,kr   # 삼성바이오로직스
AAPL,us
MSFT,us
NVDA,us
TSLA,us
AMZN,us"""


def show_scanner():
    page_header("📡", "종목 스캐너",
                "감시 목록의 종목을 일괄 분석하여 매수·매도 신호와 기술적 점수를 제공합니다.")

    with st.expander("📋 감시 목록 설정", expanded=True):
        watchlist_str = st.text_area(
            "종목 목록  (형식: 종목코드,시장  # 설명)",
            value=_DEFAULT_WATCHLIST,
            height=200,
            key="scn_watchlist",
            help="국내는 kr, 미국은 us. 줄 단위 입력.",
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            days = st.slider("데이터 기간 (일)", 60, 365, 120, key="scn_days")
        with c2:
            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
            run_scn = st.button("▶ 스캔 실행", width="stretch", key="scn_run")

    if "scn_result" not in st.session_state:
        st.session_state.scn_result = None

    if run_scn:
        n = sum(1 for l in watchlist_str.splitlines() if l.split("#")[0].strip())
        with st.spinner(f"{n}개 종목 스캔 중... (30초~1분 소요)"):
            results = cached_scan(watchlist_str, int(days))
        st.session_state.scn_result = results
        if not results:
            st.warning("분석 결과가 없습니다. 종목 코드와 인터넷 연결을 확인하세요.")

    if st.session_state.scn_result:
        results = st.session_state.scn_result
        if not results:
            return

        # 요약 통계
        total = len(results)
        n_buy  = sum(1 for r in results if "매수" in r.get("opinion", ""))
        n_sell = sum(1 for r in results if "매도" in r.get("opinion", ""))
        n_neut = total - n_buy - n_sell
        avg_score = sum(r.get("score", 0) for r in results) / total if total else 0

        chip("스캔 요약")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 종목 수",    f"{total}개")
        c2.metric("🟢 매수 신호", f"{n_buy}개",  f"{n_buy/total*100:.0f}%")
        c3.metric("🔴 매도 신호", f"{n_sell}개", f"{n_sell/total*100:.0f}%")
        c4.metric("⭐ 평균 점수", f"{avg_score:.1f}")

        st.markdown("---")

        from scanner import plot_dashboard as _plot_scn
        fig = _plot_scn(results, show=False)
        st.plotly_chart(fig, width="stretch")

        chip("종목별 상세")
        rows = []
        for r in results:
            rows.append({
                "종목":      r["ticker"],
                "시장":      r["market"].upper(),
                "현재가":    f"{r['close']:,.0f}",
                "등락":      f"{r['change_pct']:+.1f}%",
                "RSI":       f"{r['rsi']:.0f}",
                "MA":        "🌟 골든" if r["ma_golden"] else "💀 데드",
                "MACD":      "▲ UP" if r["macd_up"] else "▼ DN",
                "점수":      f"{r['score']:.1f}",
                "의견":      r["opinion"],
                "매수 신호": ", ".join(r["buys"]) if r["buys"] else "-",
            })
        scan_df = pd.DataFrame(rows)
        styled = (scan_df.style
                  .map(_color_opinion, subset=["의견"])
                  .map(_color_change,  subset=["등락"])
                  .set_properties(**{"text-align": "center"})
                  .hide(axis="index"))
        st.dataframe(styled, width="stretch")

        # ── 종목 분석 페이지로 이동 ──────────────────────────────────────────
        gc1, gc2 = st.columns([3, 1])
        with gc1:
            goto_sel = st.selectbox("차트로 자세히 볼 종목",
                                    [r["ticker"] for r in results], key="scn_goto")
        with gc2:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("📈 종목 분석 열기", key="scn_goto_btn", width="stretch"):
                goto_stock(goto_sel)
