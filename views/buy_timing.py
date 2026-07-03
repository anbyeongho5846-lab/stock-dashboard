"""페이지: 매수 타이밍 — 신호 스캔 + 매수 계획 + 이메일 알림."""

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


def show_signal_monitor():
    import smtplib, ssl
    from email.mime.text import MIMEText
    from datetime import datetime, timedelta
    from pathlib import Path
    from analyzer import fetch_kr, fetch_us, add_indicators
    from scanner import load_watchlist, analyze, DEFAULT_WATCHLIST

    page_header("📌", "매수 타이밍 스캐너",
                "관심 종목의 RSI·MACD·이동평균을 매일 자동 분석해 최적 진입 타이밍을 알려줍니다.")

    # ── 감시 목록 관리 ────────────────────────────────────────────────────────
    if "signal_watchlist" not in st.session_state:
        default = load_watchlist(DEFAULT_WATCHLIST) if DEFAULT_WATCHLIST.exists() else []
        st.session_state.signal_watchlist = default

    with st.expander("📋 감시 종목 관리", expanded=False):
        add_c1, add_c2, add_c3 = st.columns([2, 2, 1])
        with add_c1:
            new_ticker = st.text_input("종목코드 / 티커", placeholder="005930 또는 AAPL", key="sm_ticker")
        with add_c2:
            new_market = st.radio("시장", ["kr", "us"], horizontal=True, key="sm_market")
        with add_c3:
            st.write("")
            st.write("")
            if st.button("➕ 추가", key="sm_add"):
                t = new_ticker.strip().upper()
                if t and (t, new_market) not in st.session_state.signal_watchlist:
                    st.session_state.signal_watchlist.append((t, new_market))
                    st.success(f"{t} 추가됨")
                    st.rerun()

        if st.session_state.signal_watchlist:
            labels = [f"{t} ({m.upper()})" for t, m in st.session_state.signal_watchlist]
            del_sel = st.selectbox("삭제할 종목", labels, key="sm_del")
            if st.button("🗑️ 삭제", key="sm_del_btn"):
                idx = labels.index(del_sel)
                st.session_state.signal_watchlist.pop(idx)
                st.rerun()

        st.info(f"현재 {len(st.session_state.signal_watchlist)}개 종목 감시 중")

    # ── 스캔 실행 ─────────────────────────────────────────────────────────────
    @st.cache_data(ttl=3600)
    def _scan_all(watchlist_key: str, watchlist: list) -> list:
        end   = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=150)).strftime("%Y-%m-%d")
        results = []
        for ticker, market in watchlist:
            try:
                df = fetch_kr(ticker, start, end) if market == "kr" else fetch_us(ticker, start, end)
                if df.empty:
                    continue
                df  = add_indicators(df)
                row = analyze(df, ticker, market)
                if row:
                    results.append(row)
            except Exception:
                pass
        return sorted(results, key=lambda x: x["score"], reverse=True)

    watchlist = st.session_state.signal_watchlist
    scan_col, _ = st.columns([1, 5])
    with scan_col:
        if st.button("🔍 신호 스캔 실행", type="primary", key="sm_scan"):
            st.cache_data.clear()

    if not watchlist:
        st.warning("감시 종목을 추가하세요.")
        return

    with st.spinner(f"{len(watchlist)}개 종목 분석 중... (첫 실행은 30초 내외 소요)"):
        cache_key = ",".join(f"{t}_{m}" for t, m in watchlist)
        results = _scan_all(cache_key, watchlist)

    if not results:
        st.error("데이터를 가져올 수 없습니다.")
        return

    # ── BUY 신호 강조 카드 ────────────────────────────────────────────────────
    buy_results = [r for r in results if r["opinion"] in ("강매수", "매수")]

    if buy_results:
        st.markdown(f"### 🚨 매수 신호 발생 — {len(buy_results)}개 종목")
        for r in buy_results:
            color = "#1a6b3a" if r["opinion"] == "강매수" else "#2dc653"
            signals_str = " · ".join(r["buys"])
            currency = "원" if r["market"] == "KR" else "$"
            st.markdown(f"""
<div style="background:{color}22;border-left:4px solid {color};
            border-radius:8px;padding:14px 18px;margin-bottom:10px;">
  <b style="font-size:1.1rem;">{r['ticker']} ({r['market']})</b>
  &nbsp;&nbsp;<span style="color:{color};font-weight:700;">{r['opinion']}</span>
  &nbsp;|&nbsp; 현재가: <b>{r['close']:,.0f}{currency}</b>
  &nbsp;|&nbsp; RSI: <b>{r['rsi']:.1f}</b>
  &nbsp;|&nbsp; 신호: {signals_str}
</div>
""", unsafe_allow_html=True)
    else:
        st.info("현재 매수 신호가 발생한 종목이 없습니다.")

    # ── 전체 스캔 결과 테이블 ─────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 전체 종목 신호 현황")

    opinion_color = {"강매수": "🟢", "매수": "🟩", "중립": "⚪", "매도": "🟥", "강매도": "🔴"}
    rows = []
    for r in results:
        currency = "원" if r["market"] == "KR" else "$"
        rows.append({
            "종목":     r["ticker"],
            "시장":     r["market"],
            "현재가":   f"{r['close']:,.0f}{currency}",
            "등락":     f"{r['change_pct']:+.1f}%",
            "RSI":      f"{r['rsi']:.1f}",
            "MA배열":   "골든" if r["ma_golden"] else "데드",
            "MACD":     "▲" if r["macd_up"] else "▼",
            "매수신호": ", ".join(r["buys"]) if r["buys"] else "-",
            "의견":     f"{opinion_color.get(r['opinion'], '')} {r['opinion']}",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ── 종목 분석 페이지로 이동 ───────────────────────────────────────────────
    gc1, gc2 = st.columns([3, 1])
    with gc1:
        goto_sel = st.selectbox("차트로 자세히 볼 종목",
                                [r["ticker"] for r in results], key="sm_goto")
    with gc2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("📈 종목 분석 열기", key="sm_goto_btn", width="stretch"):
            goto_stock(goto_sel)

    # ── 매수 계획 계산기 ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 💰 매수 계획 계산기")
    st.caption("예산 대비 몇 주를 살 수 있는지, 지지선(MA20) 기준 진입가를 제안합니다.")

    plan_ticker = st.selectbox(
        "종목 선택",
        [r["ticker"] for r in results],
        key="plan_ticker"
    )
    plan_r = next(r for r in results if r["ticker"] == plan_ticker)
    currency = "원" if plan_r["market"] == "KR" else "$"

    p1, p2, p3 = st.columns(3)
    budget = p1.number_input(f"투자 예산 ({currency})", min_value=0, value=1_000_000 if plan_r["market"] == "KR" else 1000, step=100_000 if plan_r["market"] == "KR" else 100, key="plan_budget")
    entry_price = p2.number_input(f"진입가 ({currency})", min_value=0.0, value=float(plan_r["ma20"]), format="%.2f", key="plan_entry")
    risk_pct = p3.slider("리스크 한도 (%)", 1, 20, 5, key="plan_risk")

    if entry_price > 0:
        shares = int(budget / entry_price)
        total_cost = shares * entry_price
        stop_loss = entry_price * (1 - risk_pct / 100)
        max_loss = shares * (entry_price - stop_loss)

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("매수 가능 주수", f"{shares:,}주")
        r2.metric("실제 투입금액", f"{total_cost:,.0f}{currency}")
        r3.metric(f"손절가 (-{risk_pct}%)", f"{stop_loss:,.0f}{currency}")
        r4.metric("최대 손실액", f"{max_loss:,.0f}{currency}")

        st.caption(
            f"💡 진입가 기본값은 MA20 지지선({plan_r['ma20']:,.0f}{currency})입니다. "
            f"현재가({plan_r['close']:,.0f}{currency})와 비교해 조정하세요."
        )

    # ── 이메일 알림 ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 📧 이메일 신호 발송")
    st.caption("매수 신호 종목 요약을 이메일로 받을 수 있습니다. Gmail 앱 비밀번호가 필요합니다.")

    with st.expander("이메일 설정", expanded=False):
        e1, e2 = st.columns(2)
        sender_email = e1.text_input("발신 Gmail 주소", key="email_from")
        sender_pw    = e2.text_input("Gmail 앱 비밀번호", type="password", key="email_pw")
        recv_email   = st.text_input("수신 이메일", key="email_to")

        # Streamlit secrets 우선 사용
        try:
            sender_email = sender_email or st.secrets["email"]["sender"]
            sender_pw    = sender_pw    or st.secrets["email"]["app_password"]
            recv_email   = recv_email   or st.secrets["email"]["receiver"]
        except Exception:
            pass

        if st.button("📨 매수 신호 이메일 발송", key="email_send"):
            if not buy_results:
                st.warning("현재 매수 신호 종목이 없습니다.")
            elif not (sender_email and sender_pw and recv_email):
                st.error("이메일 주소와 앱 비밀번호를 입력하세요.")
            else:
                body_lines = [f"[{datetime.today().strftime('%Y-%m-%d %H:%M')}] 매수 신호 종목\n"]
                for r in buy_results:
                    cur = "원" if r["market"] == "KR" else "$"
                    body_lines.append(
                        f"▶ {r['ticker']} ({r['market']})  {r['opinion']}\n"
                        f"   현재가: {r['close']:,.0f}{cur}  RSI: {r['rsi']:.1f}\n"
                        f"   신호: {', '.join(r['buys'])}\n"
                    )
                body = "\n".join(body_lines)
                try:
                    msg = MIMEText(body, "plain", "utf-8")
                    msg["Subject"] = f"📌 매수 신호 알림 ({len(buy_results)}개 종목)"
                    msg["From"]    = sender_email
                    msg["To"]      = recv_email
                    ctx = ssl.create_default_context()
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
                        s.login(sender_email, sender_pw)
                        s.sendmail(sender_email, recv_email, msg.as_string())
                    st.success(f"✅ {recv_email} 으로 발송 완료!")
                except Exception as e:
                    st.error(f"발송 실패: {e}")

    st.caption(f"마지막 스캔: {datetime.today().strftime('%Y-%m-%d %H:%M')} | 캐시 1시간")
