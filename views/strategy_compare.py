"""페이지: 전략 비교 — MA/RSI/MACD 성과 비교."""

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


def show_compare():
    page_header("⚖️", "전략 비교",
                "MA 골든크로스 · RSI 역추세 · MACD 세 가지 전략의 성과를 나란히 비교합니다.")

    with st.expander("⚙️ 설정", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ticker  = st.text_input("종목 코드", value="AAPL", key="cmp_ticker")
            is_kr   = st.checkbox("국내 (KRX)", value=detect_market(ticker), key="cmp_kr")
        with c2:
            days    = st.slider("기간 (일)", 90, 730, 365, key="cmp_days")
            capital = st.number_input("초기 자본", 1_000_000,
                                      value=10_000_000, step=1_000_000, key="cmp_capital",
                                      format="%d")
        with c3:
            st.markdown("**MA 설정**")
            short    = st.number_input("단기 MA", 2,  50,  5,  key="cmp_short")
            long_    = st.number_input("장기 MA", 10, 200, 20, key="cmp_long")
        with c4:
            st.markdown("**RSI 설정**")
            rsi_buy  = st.number_input("매수 기준", 10, 50, 30, key="cmp_rsi_buy")
            rsi_sell = st.number_input("매도 기준", 50, 90, 70, key="cmp_rsi_sell")
        run_cmp = st.button("▶ 비교 실행", width="stretch", key="cmp_run")

    if "cmp_result" not in st.session_state:
        st.session_state.cmp_result = None

    if run_cmp:
        with st.spinner("세 가지 전략 비교 중..."):
            df = cached_stock(ticker.strip().upper(), is_kr, int(days))
            if df.empty:
                st.error("데이터를 가져오지 못했습니다.")
                return
            from analyzer import add_indicators
            from backtester import run_backtest
            from compare import backtest_rsi, backtest_macd, plot_comparison

            df = add_indicators(df)
            df_ma,   _, m_ma   = run_backtest(df.copy(), int(short), int(long_),   float(capital))
            df_rsi,  _, m_rsi  = backtest_rsi(df.copy(), int(rsi_buy), int(rsi_sell), float(capital))
            df_macd, _, m_macd = backtest_macd(df.copy(), float(capital))

            strategies = {
                "MA":   {"df": df_ma,   "metrics": m_ma},
                "RSI":  {"df": df_rsi,  "metrics": m_rsi},
                "MACD": {"df": df_macd, "metrics": m_macd},
            }
            title = f"{ticker.upper()} ({'KRX' if is_kr else 'US'})"
            fig = plot_comparison(strategies, title, show=False)
            st.session_state.cmp_result = (strategies, fig)

    if st.session_state.cmp_result:
        strategies, fig = st.session_state.cmp_result
        bh = list(strategies.values())[0]["metrics"]["bh_return"]

        chip("전략 성과 비교")
        rows = []
        for name, data in strategies.items():
            m = data["metrics"]
            rows.append({
                "전략":     name,
                "수익률":   f"{m['total_return']:+.1f}%",
                "B&H 대비": f"{m['total_return']-bh:+.1f}%",
                "승률":     f"{m['win_rate']:.0f}%",
                "샤프":     f"{m['sharpe']:.2f}",
                "MDD":      f"{m['mdd']:.1f}%",
                "거래수":   f"{m['n_trades']}회",
            })
        tbl = pd.DataFrame(rows).set_index("전략")
        styled = (tbl.style
                  .map(_color_change, subset=["수익률", "B&H 대비"])
                  .set_properties(**{"text-align": "center"}))
        st.dataframe(styled, width="stretch")

        col1, _ = st.columns([1, 3])
        col1.metric("📊 Buy & Hold 기준선", f"{bh:+.1f}%")

        st.markdown("---")
        st.plotly_chart(fig, width="stretch")
