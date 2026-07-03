"""페이지: 가상 투자 — 매수/매도/거래내역 (Supabase 저장)."""

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


def show_virtual_portfolio():
    from virtual_portfolio import (
        load_portfolio, save_portfolio, reset_portfolio,
        buy as vp_buy, sell as vp_sell,
        evaluate, plot_portfolio, get_current_price,
        search_kr_stocks, search_us_stocks, rebuild_kr_ticker_db,
        KR_BUY_FEE, KR_SELL_FEE, KR_SELL_TAX,
    )

    page_header("💰", "가상 투자",
                "가상 자금으로 국내·미국 주식을 매수·매도하고 포트폴리오 성과를 추적합니다.")

    # ── 포트폴리오 로드 & 평가 ─────────────────────────────────────────────────
    p  = load_portfolio()
    ev = evaluate(p)

    # ── 상단 요약 메트릭 ────────────────────────────────────────────────────────
    chip("포트폴리오 요약")
    c1, c2, c3, c4, c5 = st.columns(5)
    pnl_sign  = "+" if ev["total_pnl"] >= 0 else ""
    pnl_color = "#34d399" if ev["total_pnl"] >= 0 else "#f87171"
    c1.metric("💼 총 자산",     f"{ev['total_value']:,.0f}원")
    c2.metric("💵 현금 잔고",   f"{ev['cash']:,.0f}원")
    c3.metric("📦 주식 평가액", f"{ev['holdings_value']:,.0f}원")
    c4.metric("💹 총 손익",
              f"{pnl_sign}{ev['total_pnl']:,.0f}원",
              f"{ev['total_pnl_pct']:+.2f}%")
    c5.metric("🏦 초기 자본",   f"{ev['initial_capital']:,.0f}원")

    st.markdown("---")

    # ── 차트 (자산 구성 파이 + 종목별 수익률 바) ────────────────────────────────
    fig_pf = plot_portfolio(ev, show=False)
    st.plotly_chart(fig_pf, use_container_width=True)

    # ── 보유 종목 테이블 ────────────────────────────────────────────────────────
    if ev["rows"]:
        chip("보유 종목")
        hold_rows = []
        for r in ev["rows"]:
            hold_rows.append({
                "종목명":   r["종목명"],
                "티커":     r["티커"],
                "시장":     r["시장"],
                "수량":     f"{r['수량']:,}주",
                "평균단가": f"{r['평균단가']:,.0f}원",
                "현재가":   f"{r['현재가']:,.0f}원",
                "평가금액": f"{r['평가금액']:,.0f}원",
                "손익":     f"{r['손익']:+,.0f}원",
                "수익률":   f"{r['수익률']:+.2f}%",
            })
        hold_df = pd.DataFrame(hold_rows)
        styled_hold = (hold_df.style
                       .map(_color_pnl,    subset=["손익"])
                       .map(_color_change, subset=["수익률"])
                       .set_properties(**{"text-align": "center"})
                       .hide(axis="index"))
        st.dataframe(styled_hold, use_container_width=True)
    else:
        st.info("보유 종목이 없습니다. 아래 [🛒 매수] 탭에서 종목을 매수해 보세요.")

    st.markdown("---")

    # ── 탭: 매수 / 매도 / 거래 내역 / 설정 ────────────────────────────────────
    tab_buy, tab_sell, tab_hist, tab_cfg = st.tabs(
        ["🛒 매수", "💸 매도", "📋 거래 내역", "⚙️ 설정"]
    )

    # ── 매수 탭 ────────────────────────────────────────────────────────────────
    with tab_buy:
        # ── 종목 검색 섹션 ─────────────────────────────────────────────────────
        chip("종목 검색")
        sc1, sc2, sc3 = st.columns([4, 2, 1])
        with sc1:
            search_q = st.text_input(
                "종목명으로 검색",
                placeholder="예: 삼성전자 / 카카오 / Apple / Tesla",
                key="vp_sq",
                label_visibility="collapsed",
            )
        with sc2:
            search_mkt = st.selectbox(
                "검색 시장",
                ["국내 (KR)", "미국 (US)"],
                key="vp_sm",
                label_visibility="collapsed",
            )
        with sc3:
            st.markdown("<div style='margin-top:2px'></div>", unsafe_allow_html=True)
            do_search = st.button("🔍 검색", key="vp_do_search", use_container_width=True)

        if do_search:
            if not search_q.strip():
                st.warning("검색어를 입력하세요.")
            else:
                sm_code = "kr" if "KR" in search_mkt else "us"
                with st.spinner("검색 중..."):
                    sr = (search_kr_stocks(search_q.strip())
                          if sm_code == "kr"
                          else search_us_stocks(search_q.strip()))
                st.session_state["vp_sr"]     = sr
                st.session_state["vp_sr_mkt"] = sm_code
                if not sr:
                    st.warning("검색 결과가 없습니다. 검색어를 바꿔 보세요.")

        # 검색 결과 표시
        sr      = st.session_state.get("vp_sr", [])
        sr_mkt  = st.session_state.get("vp_sr_mkt", "kr")
        if sr:
            if sr_mkt == "kr":
                opts = [f"{r['name']}  ({r['code']})" for r in sr]
            else:
                opts = [
                    f"{r['name']}  [{r['ticker']}] — {r.get('exchange', r['type'])}"
                    for r in sr
                ]
            rc1, rc2 = st.columns([5, 1])
            with rc1:
                picked = st.selectbox("검색 결과", opts, key="vp_sr_sel",
                                      label_visibility="collapsed")
            with rc2:
                if st.button("✅ 선택", key="vp_pick", use_container_width=True):
                    idx  = opts.index(picked)
                    r    = sr[idx]
                    code = r.get("code") or r.get("ticker", "")
                    st.session_state["vp_buy_ticker"] = code
                    st.session_state["vp_buy_market"] = (
                        "국내 (KR)" if sr_mkt == "kr" else "미국 (US)"
                    )
                    st.session_state["vp_sr"] = []   # 결과 초기화
                    st.rerun()

        st.markdown("---")

        # ── 매수 주문 폼 ───────────────────────────────────────────────────────
        chip("매수 주문")
        col_a, col_b = st.columns(2)

        with col_a:
            buy_ticker = st.text_input(
                "종목 코드",
                value="005930",
                key="vp_buy_ticker",
                help="위에서 검색 후 선택하거나 직접 입력 (국내: 005930 / 미국: AAPL)",
            )
            buy_market = st.selectbox("시장", ["국내 (KR)", "미국 (US)"], key="vp_buy_market")
            buy_mkt_code = "kr" if "KR" in buy_market else "us"

        with col_b:
            if st.button("💲 현재가 조회", key="vp_buy_lookup"):
                with st.spinner("현재가 조회 중..."):
                    cur_p = get_current_price(buy_ticker.strip().upper(), buy_mkt_code)
                if cur_p:
                    st.session_state["vp_buy_price_val"] = cur_p
                    st.success(f"현재가: {cur_p:,.0f}원")
                else:
                    st.error("현재가를 가져오지 못했습니다.")

            buy_price = st.number_input(
                "매수 가격 (원)",
                min_value=1.0,
                step=100.0,
                value=float(st.session_state.get("vp_buy_price_val", 70000)),
                key="vp_buy_price",
                format="%.0f",
            )
            buy_qty = st.number_input(
                "수량 (주)", min_value=1, value=1, step=1, key="vp_buy_qty"
            )

        est_buy_amt = buy_price * buy_qty
        est_buy_fee = round(est_buy_amt * KR_BUY_FEE) if buy_mkt_code == "kr" else 0
        st.info(
            f"예상 매수금액: **{est_buy_amt:,.0f}원** + 수수료 {est_buy_fee:,.0f}원"
            f" = **{est_buy_amt + est_buy_fee:,.0f}원**  |  현금 잔고: {p['cash']:,.0f}원"
        )

        if st.button("✅ 매수 실행", key="vp_buy_exec", use_container_width=True):
            ok, msg = vp_buy(
                p, buy_ticker.strip().upper(), buy_mkt_code,
                int(buy_qty), float(buy_price),
            )
            if ok:
                save_portfolio(p)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # ── 매도 탭 ────────────────────────────────────────────────────────────────
    with tab_sell:
        chip("종목 매도")
        if not p["holdings"]:
            st.info("보유 종목이 없습니다.")
        else:
            holding_keys = list(p["holdings"].keys())
            holding_labels = [
                f"{h['name']} ({h['ticker']}/{h['market'].upper()}) — {h['quantity']:,}주"
                for h in p["holdings"].values()
            ]
            sell_choice = st.selectbox("매도할 종목", holding_labels, key="vp_sell_choice")
            sell_key    = holding_keys[holding_labels.index(sell_choice)]
            sell_h      = p["holdings"][sell_key]

            col_c, col_d = st.columns(2)
            with col_c:
                if st.button("🔍 현재가 조회", key="vp_sell_lookup"):
                    with st.spinner("현재가 조회 중..."):
                        s_cur = get_current_price(sell_h["ticker"], sell_h["market"])
                    if s_cur:
                        st.session_state["vp_sell_price_val"] = s_cur
                        st.success(f"현재가: {s_cur:,.0f}원")
                    else:
                        st.error("현재가를 가져오지 못했습니다.")

                sell_price = st.number_input(
                    "매도 가격 (원)",
                    min_value=1.0,
                    step=100.0,
                    value=float(st.session_state.get("vp_sell_price_val",
                                                     sell_h["avg_price"])),
                    key="vp_sell_price",
                    format="%.0f",
                )

            with col_d:
                sell_qty = st.number_input(
                    "수량 (주)",
                    min_value=1,
                    max_value=sell_h["quantity"],
                    value=sell_h["quantity"],
                    step=1,
                    key="vp_sell_qty",
                )
                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096; margin-top:8px;'>"
                    f"평균단가: {sell_h['avg_price']:,.0f}원 &nbsp;|&nbsp; "
                    f"보유: {sell_h['quantity']:,}주</div>",
                    unsafe_allow_html=True,
                )

            sell_mkt      = sell_h["market"]
            est_sell_fee  = (round(sell_price * sell_qty * (KR_SELL_FEE + KR_SELL_TAX))
                             if sell_mkt == "kr" else 0)
            est_net       = sell_price * sell_qty - est_sell_fee
            est_pnl       = round((sell_price - sell_h["avg_price"]) * sell_qty - est_sell_fee)
            est_pnl_color = "#34d399" if est_pnl >= 0 else "#f87171"
            est_pnl_sign  = "+" if est_pnl >= 0 else ""
            st.markdown(
                f'<div style="background:#1a2035; border-radius:8px; padding:12px 16px; margin:8px 0;">'
                f'예상 수령액: <b>{est_net:,.0f}원</b> (수수료+세금: {est_sell_fee:,.0f}원)'
                f'&nbsp;&nbsp;|&nbsp;&nbsp;'
                f'예상 손익: <span style="color:{est_pnl_color}; font-weight:700;">'
                f'{est_pnl_sign}{est_pnl:,.0f}원</span></div>',
                unsafe_allow_html=True,
            )

            if st.button("✅ 매도 실행", key="vp_sell_exec", use_container_width=True):
                ok, msg = vp_sell(
                    p, sell_h["ticker"], sell_h["market"],
                    int(sell_qty), float(sell_price),
                )
                if ok:
                    save_portfolio(p)
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # ── 거래 내역 탭 ───────────────────────────────────────────────────────────
    with tab_hist:
        chip("거래 내역")
        txs = p.get("transactions", [])
        if not txs:
            st.info("거래 내역이 없습니다.")
        else:
            def _color_action(val: str) -> str:
                if val == "BUY":  return "color:#60a5fa; font-weight:700"
                if val == "SELL": return "color:#f87171; font-weight:700"
                return ""

            tx_rows = []
            for t in txs:
                pnl_str = (f"{t['pnl']:+,.0f}원"
                           if t.get("pnl") is not None else "—")
                tx_rows.append({
                    "일시":     t["date"],
                    "구분":     t["action"],
                    "종목명":   t["name"],
                    "티커":     t["ticker"],
                    "시장":     t["market"],
                    "가격":     f"{t['price']:,.0f}원",
                    "수량":     f"{t['quantity']:,}주",
                    "거래금액": f"{t['amount']:,.0f}원",
                    "수수료":   f"{t['fee']:,.0f}원",
                    "손익":     pnl_str,
                })
            tx_df = pd.DataFrame(tx_rows)
            styled_tx = (tx_df.style
                         .map(_color_action, subset=["구분"])
                         .map(_color_pnl,    subset=["손익"])
                         .set_properties(**{"text-align": "center"})
                         .hide(axis="index"))
            st.dataframe(styled_tx, use_container_width=True)

    # ── 설정 탭 ────────────────────────────────────────────────────────────────
    with tab_cfg:
        chip("포트폴리오 정보")
        st.markdown(
            f'<div style="background:#1a2035; border-radius:10px; padding:16px 20px; margin-bottom:16px;">'
            f'<div style="color:#94a3b8; font-size:0.78rem;">생성일</div>'
            f'<div style="color:#e2e8f0; margin-bottom:10px;">{p.get("created_at", "—")}</div>'
            f'<div style="color:#94a3b8; font-size:0.78rem;">초기 자본</div>'
            f'<div style="color:#e2e8f0;">{p["initial_capital"]:,.0f}원</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        with st.expander("✏️ 평균단가 수정", expanded=False):
            if not p["holdings"]:
                st.info("보유 종목이 없습니다.")
            else:
                avg_keys   = list(p["holdings"].keys())
                avg_labels = [
                    f"{h['name']} ({h['ticker']}/{h['market'].upper()})"
                    for h in p["holdings"].values()
                ]
                avg_choice = st.selectbox(
                    "수정할 종목", avg_labels, key="vp_avg_choice"
                )
                avg_key = avg_keys[avg_labels.index(avg_choice)]
                avg_h   = p["holdings"][avg_key]

                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096; margin-bottom:6px;'>"
                    f"현재 평균단가: <b style='color:#e2e8f0;'>{avg_h['avg_price']:,.2f}원</b>"
                    f"&nbsp;|&nbsp; 보유 수량: {avg_h['quantity']:,}주</div>",
                    unsafe_allow_html=True,
                )
                new_avg = st.number_input(
                    "새 평균단가 (원)",
                    min_value=0.01,
                    value=float(avg_h["avg_price"]),
                    step=100.0,
                    format="%.2f",
                    key="vp_avg_price_input",
                )
                if st.button("✅ 평균단가 적용", key="vp_avg_apply"):
                    p["holdings"][avg_key]["avg_price"] = round(float(new_avg), 4)
                    save_portfolio(p)
                    st.success(
                        f"{avg_h['name']} 평균단가를 {new_avg:,.2f}원으로 수정했습니다."
                    )
                    st.rerun()

        from virtual_portfolio import _KR_DB_PATH
        with st.expander("🗂️ 국내 종목 DB 관리", expanded=False):
            db_exists = _KR_DB_PATH.exists()
            if db_exists:
                import os
                mtime = datetime.fromtimestamp(os.path.getmtime(_KR_DB_PATH))
                st.markdown(
                    f"<div style='font-size:0.82rem; color:#718096;'>"
                    f"마지막 갱신: {mtime.strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; "
                    f"경로: kr_tickers.json</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.warning("kr_tickers.json 파일이 없습니다. 갱신 버튼을 눌러 주세요.")

            if st.button("🔄 국내 종목 DB 갱신 (KOSPI+KOSDAQ)", key="vp_rebuild_db",
                         use_container_width=True):
                with st.spinner("KOSPI + KOSDAQ 종목 목록 수집 중... (20~30초 소요)"):
                    ok, msg = rebuild_kr_ticker_db()
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        with st.expander("⚠️ 포트폴리오 초기화 (모든 데이터 삭제)", expanded=False):
            new_capital = st.number_input(
                "새 초기 자본 (원)",
                min_value=100_000,
                value=10_000_000,
                step=1_000_000,
                format="%d",
                key="vp_reset_capital",
            )
            st.warning("초기화하면 모든 보유 종목과 거래 내역이 삭제됩니다.")
            confirm_reset = st.checkbox("정말 초기화하겠습니다", key="vp_reset_confirm")
            if st.button("🔄 포트폴리오 초기화", key="vp_reset_exec",
                         disabled=not confirm_reset):
                reset_portfolio(float(new_capital))
                st.success(f"포트폴리오가 {new_capital:,.0f}원으로 초기화되었습니다.")
                st.rerun()
