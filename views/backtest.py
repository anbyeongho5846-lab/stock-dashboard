"""페이지: 백테스팅 — MA 크로스 전략 시뮬레이션."""

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


def show_backtest():
    page_header("🔄", "백테스팅",
                "이동평균 골든크로스/데드크로스 전략의 과거 성과를 시뮬레이션합니다.")

    with st.expander("⚙️ 백테스팅 설정", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker  = st.text_input("종목 코드", value="005930", key="bt_ticker")
            is_kr   = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="bt_kr")
        with c2:
            short   = st.number_input("단기 MA", min_value=2,  max_value=50,   value=5,   key="bt_short")
            long_   = st.number_input("장기 MA", min_value=10, max_value=200,  value=20,  key="bt_long")
        with c3:
            days    = st.number_input("조회 기간 (일)", min_value=90,  max_value=1825, value=365, key="bt_days")
            capital = st.number_input("초기 자본 (원)", min_value=1_000_000,
                                      value=10_000_000, step=1_000_000, key="bt_capital",
                                      format="%d")
        run_bt = st.button("▶ 백테스팅 실행", use_container_width=True, key="bt_run")

    if "bt_result" not in st.session_state:
        st.session_state.bt_result = None

    if run_bt:
        if int(short) >= int(long_):
            st.error("단기 MA는 장기 MA보다 작아야 합니다.")
            return
        with st.spinner("백테스팅 실행 중..."):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from backtester import run_backtest, plot_backtest
            bt_df, trades, metrics = run_backtest(df, int(short), int(long_), float(capital))
            title = f"{ticker.upper()} ({'KRX' if is_kr else 'US'})  MA{short}/MA{long_}"
            fig = plot_backtest(bt_df, trades, title, int(short), int(long_), show=False)
            st.session_state.bt_result = (trades, metrics, fig)

    if st.session_state.bt_result:
        trades, m, fig = st.session_state.bt_result
        excess = m["total_return"] - m["bh_return"]

        chip("성과 요약")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("📊 전략 수익률",   f"{m['total_return']:+.1f}%",
                  f"B&H 대비 {excess:+.1f}%")
        c2.metric("📈 Buy & Hold",    f"{m['bh_return']:+.1f}%")
        c3.metric("🎯 승률",          f"{m['win_rate']:.1f}%")
        c4.metric("⚡ 샤프 지수",     f"{m['sharpe']:.2f}")
        c5.metric("📉 최대낙폭(MDD)", f"{m['mdd']:.1f}%")
        c6.metric("🔁 총 거래 수",    f"{m['n_trades']}회")

        st.markdown("---")
        st.plotly_chart(fig, use_container_width=True)

        if trades:
            chip("거래 내역")
            rows = []
            for t in trades:
                rows.append({
                    "진입일":  str(t["entry_date"])[:10],
                    "청산일":  str(t["exit_date"])[:10],
                    "진입가":  f"{t['entry_price']:,.0f}",
                    "청산가":  f"{t['exit_price']:,.0f}",
                    "수익률":  f"{t['pnl_pct']:+.2f}%",
                    "결과":    "✅ WIN" if t["won"] else "❌ LOSS",
                    "미청산":  "⚠️" if t.get("open") else "",
                })
            trade_df = pd.DataFrame(rows)
            styled = (trade_df.style
                      .map(_color_result, subset=["결과"])
                      .map(_color_change, subset=["수익률"])
                      .set_properties(**{"text-align": "center"})
                      .hide(axis="index"))
            st.dataframe(styled, use_container_width=True)
