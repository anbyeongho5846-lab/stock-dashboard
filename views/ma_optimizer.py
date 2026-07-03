"""페이지: MA 최적화 — 이동평균 조합 브루트포스 탐색."""

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


def show_optimizer():
    page_header("🔍", "MA 파라미터 최적화",
                "다양한 단기·장기 이동평균 조합을 브루트포스로 탐색하여 최적 파라미터를 찾습니다.")

    with st.expander("⚙️ 설정", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ticker = st.text_input("종목 코드", value="005930", key="opt_ticker")
            is_kr  = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="opt_kr")
        with c2:
            days    = st.number_input("기간 (일)", 90, 1825, 365, key="opt_days")
            capital = st.number_input("초기 자본", 1_000_000, 100_000_000,
                                      10_000_000, step=1_000_000, key="opt_capital",
                                      format="%d")
        with c3:
            shorts_str = st.text_input("단기 MA 후보 (공백 구분)", "3 5 10 15 20", key="opt_shorts")
        with c4:
            longs_str  = st.text_input("장기 MA 후보 (공백 구분)", "20 30 60 120", key="opt_longs")
        run_opt = st.button("▶ 최적화 실행", width="stretch", key="opt_run")

    if "opt_result" not in st.session_state:
        st.session_state.opt_result = None

    if run_opt:
        try:
            shorts = [int(x) for x in shorts_str.split()]
            longs  = [int(x) for x in longs_str.split()]
        except ValueError:
            st.error("MA 기간은 숫자만 입력하세요 (예: 3 5 10 20).")
            return
        n_pairs = sum(1 for s in shorts for l in longs if s < l)
        with st.spinner(f"총 {n_pairs}개 조합 탐색 중... (수십 초 소요)"):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from optimizer import optimize, plot_results as _plot_opt
            results = optimize(df, shorts, longs, float(capital))
            fig = _plot_opt(results, ticker.strip().upper(), show=False)
            st.session_state.opt_result = (results, fig)

    if st.session_state.opt_result:
        results, fig = st.session_state.opt_result
        bh   = results["bh_return"].iloc[0]
        beat = int((results["excess"] > 0).sum())

        chip("최적화 결과")
        c1, c2, c3 = st.columns(3)
        c1.metric("📊 Buy & Hold",       f"{bh:+.1f}%")
        c2.metric("🏆 B&H 초과 달성 조합", f"{beat} / {len(results)}")
        c3.metric("🥇 최고 수익 조합",
                  results.iloc[0]["label"],
                  f"{results.iloc[0]['total_return']:+.1f}%")

        st.plotly_chart(fig, width="stretch")

        chip("전체 조합 결과")
        show_df = results[["label", "total_return", "excess",
                            "win_rate", "sharpe", "mdd", "n_trades"]].copy()
        show_df.columns = ["조합", "수익률(%)", "초과(%)", "승률(%)", "샤프", "MDD(%)", "거래수"]
        show_df["수익률(%)"] = show_df["수익률(%)"].apply(lambda v: f"{v:+.1f}%")
        show_df["초과(%)"]   = show_df["초과(%)"].apply(lambda v: f"{v:+.1f}%")
        show_df["MDD(%)"]    = show_df["MDD(%)"].apply(lambda v: f"{v:.1f}%")
        styled = (show_df.style
                  .map(_color_excess,  subset=["수익률(%)", "초과(%)"])
                  .set_properties(**{"text-align": "center"})
                  .hide(axis="index"))
        st.dataframe(styled, width="stretch")
