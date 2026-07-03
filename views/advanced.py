"""페이지: 심화 분석 — 시장 국면/스마트 머니/대체 데이터."""

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


@st.cache_data(ttl=3600)
def _cached_adv_price(ticker: str, days: int, is_kr: bool) -> pd.DataFrame:
    """심화 분석용 주가 데이터 캐시."""
    from datetime import datetime, timedelta
    from analyzer import fetch_kr, fetch_us, add_indicators
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    raw = fetch_kr(ticker, start, end) if is_kr else fetch_us(ticker, start, end)
    if raw.empty:
        return pd.DataFrame()
    return add_indicators(raw)


@st.cache_data(ttl=600)
def _cached_investor_flow(ticker: str, days: int) -> pd.DataFrame:
    from smart_money import fetch_investor_flow
    return fetch_investor_flow(ticker, days)


@st.cache_data(ttl=3600)
def _cached_naver_trend(
    keywords_key: str,
    client_id: str,
    client_secret: str,
    start_date: str,
    time_unit: str,
) -> pd.DataFrame:
    from alt_data import fetch_naver_trend
    keywords = [k.strip() for k in keywords_key.split("|") if k.strip()]
    return fetch_naver_trend(keywords, client_id, client_secret,
                             start_date=start_date, time_unit=time_unit)


def show_advanced_analysis():
    page_header(
        "🔬", "심화 분석",
        "시장 국면 판별기 · 스마트 머니 + 매물대 · 대체 데이터(검색 트렌드/수출)",
    )

    # ── 공통 입력 ──────────────────────────────────────────────────────────────
    chip("종목 선택")
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        adv_ticker = st.text_input(
            "종목코드 (6자리: 국내, 영문: 미국)",
            value="005930", key="adv_ticker",
            placeholder="예: 005930 (삼성전자), AAPL",
        )
    with c2:
        adv_days = st.selectbox("분석 기간", [90, 120, 180, 365], index=1, key="adv_days")
    with c3:
        is_kr = detect_market(adv_ticker)
        st.markdown(
            f'<div style="margin-top:28px; font-size:0.82rem; color:#94a3b8;">'
            f'{"🇰🇷 국내" if is_kr else "🇺🇸 미국"}</div>',
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3 = st.tabs([
        "🎯 시장 국면 판별기",
        "💰 스마트 머니 + 매물대",
        "📡 대체 데이터",
    ])

    # ── 탭1: 시장 국면 판별기 ────────────────────────────────────────────────
    with tab1:
        chip("시장 국면 (Market Regime Filter)")
        st.caption(
            "ADX(평균방향성지수) + 이동평균 정배열/역배열로 현재 시장이 "
            "**추세 구간**인지 **박스권**인지 진단합니다. "
            "국면에 맞지 않는 지표를 사용하면 신호가 역효과를 냅니다."
        )

        run_regime = st.button("▶ 국면 분석 실행", key="run_regime", use_container_width=True)
        if run_regime or st.session_state.get("regime_result"):
            if run_regime:
                with st.spinner("주가 데이터 로딩 및 ADX 계산 중..."):
                    df_adv = _cached_adv_price(adv_ticker, adv_days, is_kr)
                    if df_adv.empty:
                        st.error("주가 데이터를 가져오지 못했습니다. 종목코드를 확인하세요.")
                        st.stop()
                    from regime import detect_regime, plot_regime
                    result = detect_regime(df_adv)
                    st.session_state["regime_result"] = result
                    st.session_state["regime_df"]     = df_adv
            else:
                result = st.session_state["regime_result"]
                df_adv = st.session_state.get("regime_df", pd.DataFrame())

            if result.get("regime") == "unknown":
                st.warning("데이터가 부족합니다. 더 긴 기간을 선택하세요.")
                st.stop()

            meta = result["meta"]

            # ── 국면 배지 ──────────────────────────────────────────────────────
            st.markdown(f"""
            <div style="
                background: {meta['bg']};
                border: 1px solid {meta['color']}55;
                border-left: 4px solid {meta['color']};
                border-radius: 10px;
                padding: 16px 20px;
                margin: 12px 0;
            ">
                <div style="font-size:1.25rem; font-weight:700; color:{meta['color']};">
                    {meta['label']}
                </div>
                <div style="font-size:0.85rem; color:#cbd5e1; margin-top:6px; white-space:pre-line;">
                    {meta['desc']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── 지표 카드 ──────────────────────────────────────────────────────
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("ADX", f"{result['adx']:.1f}",
                       delta="강한 추세" if result['adx'] >= 40
                             else ("추세" if result['adx'] >= 25 else "박스권"))
            mc2.metric("+DI", f"{result['plus_di']:.1f}")
            mc3.metric("−DI", f"{result['minus_di']:.1f}")
            ma_label = {"bullish": "🟢 정배열", "bearish": "🔴 역배열", "mixed": "⬜ 혼합"}
            mc4.metric("MA 정배열", ma_label.get(result["ma_align"], "—"))

            # ── 차트 ───────────────────────────────────────────────────────────
            if not df_adv.empty:
                from regime import plot_regime
                fig_r = plot_regime(df_adv, result,
                                    title=f"{adv_ticker} ({adv_days}일)",
                                    show=False)
                st.plotly_chart(fig_r, use_container_width=True)

            # ── 추천 지표 / 피해야 할 지표 ─────────────────────────────────────
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### ✅ 지금 사용할 지표")
                for s in meta["active"]:
                    st.markdown(f"- {s}")
            with col_b:
                st.markdown("#### ❌ 지금 피해야 할 지표")
                for s in meta["avoid"]:
                    st.markdown(f"- {s}")

            # ── 박스권 오실레이터 신호 (국면 따라 자동 활성/비활성) ─────────────
            st.markdown("---")
            chip("📐 볼린저밴드 + 스토캐스틱 (박스권 역추세 전략)")

            if not df_adv.empty:
                from regime import oscillator_signals, plot_oscillators
                osc = oscillator_signals(df_adv, result)

                if osc["active"]:
                    # 박스권 → 신호 활성화
                    st.success(f"✅ **신호 활성화** — {osc['reason']}")
                else:
                    # 추세 국면 → 비활성화 (회색 안내)
                    st.warning(f"🚫 **신호 비활성화** — {osc['reason']}")

                # 현재 지표 상태 카드
                bb_ = osc["bb"]; st_ = osc["stoch"]
                oc1, oc2, oc3, oc4 = st.columns(4)
                oc1.metric("볼린저 %B", f"{bb_.get('pct_b', '—')}",
                           delta=bb_.get("position", ""))
                oc2.metric("밴드폭", f"{bb_.get('width', '—')}",
                           delta="🔸 수축(전환 임박)" if osc["squeeze"] else None)
                oc3.metric("스토캐스틱 %K", f"{st_.get('k', '—')}",
                           delta=st_.get("zone", ""))
                oc4.metric("%K-%D 크로스", st_.get("cross", "—"))

                # 신호 출력 — 박스권일 때만 강조, 추세면 흐리게
                if osc["active"]:
                    combined = osc.get("combined")
                    if combined:
                        if combined["type"] == "buy":
                            st.success(combined["msg"])
                        else:
                            st.error(combined["msg"])

                    if osc["signals"]:
                        for sig in osc["signals"]:
                            icon = "🟢" if sig["type"] == "buy" else "🔴"
                            st.markdown(
                                f"{icon} **[{sig['src']}]** {sig['msg']}"
                            )
                    elif not combined:
                        st.info("현재 역추세 진입 신호 없음 — 밴드 중앙 부근입니다.")

                    if osc["squeeze"]:
                        st.caption(
                            "🔸 **밴드폭 수축 감지**: 변동성이 줄어들고 있습니다. "
                            "곧 박스권을 벗어나 추세가 시작될 수 있으니 역추세 매매에 주의하세요."
                        )
                else:
                    st.caption(
                        "ℹ️ 추세 국면에서는 볼린저·스토캐스틱 역추세 신호가 "
                        "잦은 가짜 신호(whipsaw)를 내므로 자동으로 끕니다. "
                        "아래 차트는 참고용으로만 확인하세요."
                    )

                # 차트
                fig_osc = plot_oscillators(
                    df_adv, title=f"{adv_ticker} ({adv_days}일)", show=False
                )
                st.plotly_chart(fig_osc, use_container_width=True)

    # ── 탭2: 스마트 머니 + 매물대 ───────────────────────────────────────────
    with tab2:
        chip("스마트 머니 + 매물대 (Volume Profile)")
        st.caption(
            "가격대별 거래량 분포(Volume Profile)로 **핵심 지지·저항선**을 찾고, "
            "외국인·기관의 순매수 동향으로 **스마트 머니 흐름**을 추적합니다."
        )

        col_vp1, col_vp2 = st.columns([2, 1])
        with col_vp1:
            vp_bins = st.slider("Volume Profile 가격 구간 수", 20, 60, 40, key="vp_bins")
        with col_vp2:
            investor_days = st.selectbox("투자자 동향 기간", [20, 30, 60], index=1, key="inv_days")

        run_sm = st.button("▶ 스마트 머니 분석 실행", key="run_sm", use_container_width=True)
        if run_sm or st.session_state.get("sm_result"):
            if run_sm:
                with st.spinner("데이터 로딩 중..."):
                    df_sm = _cached_adv_price(adv_ticker, adv_days, is_kr)
                    if df_sm.empty:
                        st.error("주가 데이터를 가져오지 못했습니다.")
                        st.stop()
                    from smart_money import (
                        calc_volume_profile, find_key_levels,
                        detect_breakout, smart_money_score,
                        fetch_investor_flow, plot_smart_money,
                    )
                    vp          = calc_volume_profile(df_sm, bins=vp_bins)
                    cur_price   = float(df_sm["Close"].iloc[-1])
                    key_lvls    = find_key_levels(vp, cur_price)
                    breakout    = detect_breakout(df_sm, key_lvls)
                    investor_df = pd.DataFrame()
                    if is_kr:
                        investor_df = _cached_investor_flow(adv_ticker, investor_days)
                    sm_score = smart_money_score(investor_df)

                    st.session_state["sm_result"] = {
                        "df": df_sm, "vp": vp,
                        "key_lvls": key_lvls, "breakout": breakout,
                        "investor_df": investor_df, "sm_score": sm_score,
                        "cur_price": cur_price,
                    }
            else:
                d = st.session_state["sm_result"]
                df_sm = d["df"]; vp = d["vp"]; key_lvls = d["key_lvls"]
                breakout = d["breakout"]; investor_df = d["investor_df"]
                sm_score = d["sm_score"]; cur_price = d["cur_price"]

            from smart_money import plot_smart_money

            # ── 스마트 머니 점수 ────────────────────────────────────────────────
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("현재가", f"{cur_price:,.0f}원")
            poc = key_lvls.get("poc")
            sm2.metric("POC (최다 거래가)", f"{poc:,.0f}원" if poc else "—")
            vol_ratio = breakout.get("vol_ratio", 1.0)
            sm3.metric("거래량 비율", f"{vol_ratio:.2f}x",
                       delta="급증" if vol_ratio >= 2 else ("증가" if vol_ratio >= 1.5 else None))
            score = sm_score.get("score")
            sm4.metric(
                "스마트 머니 점수",
                f"{score}/100" if score is not None else "N/A (로컬 전용)",
                delta=sm_score.get("label", ""),
            )

            # ── 돌파 신호 ────────────────────────────────────────────────────────
            sigs = breakout.get("signals", [])
            if sigs:
                for sig in sigs:
                    st.success(
                        f"**{sig['type']}** — 매물대 {sig['level']:,.0f}원 / "
                        f"거래량 {sig['vol_ratio']}x (강도: {sig['strength']})"
                    )
            else:
                st.info("현재 매물대 돌파 신호 없음")

            if sm_score.get("detail"):
                st.caption(f"💡 {sm_score['detail']}")

            # ── 주요 가격대 테이블 ──────────────────────────────────────────────
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.markdown("**🔴 저항선 (상위 매물대)**")
                res_rows = [{"가격": f"{p:,.0f}원"} for p in key_lvls.get("resistance", [])[:5]]
                if res_rows:
                    st.dataframe(pd.DataFrame(res_rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("(없음)")
            with col_t2:
                st.markdown("**🟢 지지선 (하위 매물대)**")
                sup_rows = [{"가격": f"{p:,.0f}원"} for p in key_lvls.get("support", [])[:5]]
                if sup_rows:
                    st.dataframe(pd.DataFrame(sup_rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("(없음)")

            # ── 차트 ─────────────────────────────────────────────────────────────
            fig_sm = plot_smart_money(
                df_sm, vp, investor_df, key_lvls,
                title=f"{adv_ticker} ({adv_days}일)", show=False,
            )
            st.plotly_chart(fig_sm, use_container_width=True)

            if not is_kr:
                st.info("ℹ️ 투자자별 순매수 데이터는 국내 종목(pykrx)만 지원합니다.")
            elif investor_df.empty:
                st.warning(
                    "⚠️ 투자자별 순매수 데이터를 가져오지 못했습니다.  \n"
                    "Streamlit Cloud에서는 pykrx가 차단될 수 있습니다.  \n"
                    "로컬 환경에서 실행하면 외국인·기관·개인 순매수 차트를 볼 수 있습니다."
                )

    # ── 탭3: 대체 데이터 ─────────────────────────────────────────────────────
    with tab3:
        chip("대체 데이터 (Alternative Data)")
        st.caption(
            "재무제표보다 **3개월 선행**하는 신호를 포착합니다.  \n"
            "특정 제품의 검색량이 폭증하면 → 어닝 서프라이즈 징조.  \n"
            "수출 데이터가 늘면 → 관련 수혜주 선반영."
        )

        alt_tab1, alt_tab2 = st.tabs(["🔍 네이버 검색 트렌드", "🚢 수출 데이터 분석"])

        # ── 검색 트렌드 ─────────────────────────────────────────────────────────
        with alt_tab1:
            # Naver API 키 확인
            try:
                naver_id     = st.secrets["naver"]["client_id"]
                naver_secret = st.secrets["naver"]["client_secret"]
                has_naver    = bool(naver_id and naver_secret)
            except Exception:
                has_naver    = False
                naver_id     = ""
                naver_secret = ""

            if not has_naver:
                st.warning(
                    "**네이버 API 키 미설정** — 검색 트렌드를 사용하려면 아래 절차를 따르세요.\n\n"
                    "1. [네이버 개발자센터](https://developers.naver.com/) 접속 → 애플리케이션 등록  \n"
                    "2. **데이터랩(검색어 트렌드)** API 사용 신청  \n"
                    "3. Streamlit Cloud `Settings → Secrets`에 추가:  \n"
                    "```toml\n[naver]\nclient_id = \"YOUR_CLIENT_ID\"\nclient_secret = \"YOUR_CLIENT_SECRET\"\n```  \n"
                    "4. 로컬 `.streamlit/secrets.toml`에도 동일하게 추가"
                )
                st.info(
                    "💡 **로컬 테스트**: 위 설정 후 아래 화면이 바로 활성화됩니다.  \n"
                    "클라우드에서도 Naver API는 **해외 서버에서 접근 가능**합니다."
                )

            # 키워드 입력
            kw_col1, kw_col2, kw_col3 = st.columns([3, 1, 1])
            with kw_col1:
                default_kw = ""
                keywords_raw = st.text_input(
                    "검색 키워드 (쉼표로 구분, 최대 5개)",
                    value=default_kw,
                    placeholder="예: 갤럭시, 아이폰, 삼성전자",
                    key="alt_keywords",
                    disabled=not has_naver,
                )
            with kw_col2:
                trend_period = st.selectbox(
                    "기간", ["1년", "6개월", "3개월"], index=0,
                    key="trend_period", disabled=not has_naver,
                )
            with kw_col3:
                trend_unit = st.selectbox(
                    "집계 단위", ["week", "month"], index=0,
                    key="trend_unit", disabled=not has_naver,
                )

            if has_naver:
                run_trend = st.button("▶ 트렌드 조회", key="run_trend", use_container_width=True)
                if run_trend and keywords_raw.strip():
                    period_map = {"1년": 365, "6개월": 180, "3개월": 90}
                    start_dt   = (datetime.today() - timedelta(
                        days=period_map.get(trend_period, 365)
                    )).strftime("%Y-%m-%d")

                    keywords_list = [k.strip() for k in keywords_raw.split(",") if k.strip()]
                    kw_key = "|".join(keywords_list)

                    with st.spinner("네이버 데이터랩 조회 중..."):
                        try:
                            trend_df = _cached_naver_trend(
                                kw_key, naver_id, naver_secret,
                                start_dt, trend_unit,
                            )
                        except Exception as e:
                            st.error(f"API 오류: {e}")
                            trend_df = pd.DataFrame()

                    if trend_df.empty:
                        st.warning("데이터가 없습니다. 키워드를 확인하세요.")
                    else:
                        st.session_state["trend_df"]     = trend_df
                        st.session_state["trend_ticker"] = adv_ticker
                        st.session_state["trend_days"]   = adv_days

            if "trend_df" in st.session_state and not st.session_state["trend_df"].empty:
                trend_df = st.session_state["trend_df"]
                t_ticker = st.session_state.get("trend_ticker", adv_ticker)
                t_days   = st.session_state.get("trend_days", adv_days)

                # 주가 데이터
                price_for_trend = _cached_adv_price(t_ticker, t_days, detect_market(t_ticker))

                from alt_data import plot_trend_vs_price, calc_lead_lag, plot_lead_lag
                fig_trend = plot_trend_vs_price(
                    trend_df, price_for_trend,
                    ticker=t_ticker,
                    title=f"검색 트렌드 vs {t_ticker} 주가",
                    show=False,
                )
                st.plotly_chart(fig_trend, use_container_width=True)

                # 리드-래그 분석
                with st.expander("📊 리드-래그 상관 분석 (검색량이 주가보다 얼마나 선행?)", expanded=False):
                    st.caption(
                        "lag < 0 : 검색량 증가가 주가 상승보다 **N주 앞서 발생** (선행 지표)  \n"
                        "lag > 0 : 주가 상승 후 검색량 증가 (후행)  \n"
                        "상관계수 0.3 이상 = 유의미한 관계"
                    )
                    ll_df = calc_lead_lag(trend_df, price_for_trend)
                    if not ll_df.empty:
                        fig_ll = plot_lead_lag(ll_df, show=False)
                        st.plotly_chart(fig_ll, use_container_width=True)
                    else:
                        st.info("리드-래그 분석을 위한 데이터가 부족합니다.")

                # 최고 선행 구간 표시
                if not price_for_trend.empty:
                    from alt_data import calc_lead_lag
                    ll_df2 = calc_lead_lag(trend_df, price_for_trend)
                    if not ll_df2.empty:
                        best_rows = []
                        for col in ll_df2.columns:
                            valid = ll_df2[col].dropna()
                            if valid.empty:
                                continue
                            best_lag  = int(valid.idxmin())   # 가장 강한 상관 lag
                            best_corr = float(valid.min())
                            # 선행(음수 lag, 양의 상관) 찾기
                            neg_lags  = valid[valid.index < 0]
                            if not neg_lags.empty:
                                best_lead_lag  = int(neg_lags.idxmax())
                                best_lead_corr = float(neg_lags.max())
                                if best_lead_corr > 0.2:
                                    best_rows.append({
                                        "키워드":     col,
                                        "최적 선행":  f"{abs(best_lead_lag)}주 전",
                                        "상관계수":   f"{best_lead_corr:.2f}",
                                        "해석":       "🟢 선행 지표" if best_lead_corr > 0.3 else "⬜ 약한 선행",
                                    })
                        if best_rows:
                            chip("검색 트렌드 선행성 요약")
                            st.dataframe(
                                pd.DataFrame(best_rows),
                                use_container_width=True,
                                hide_index=True,
                            )

        # ── 수출 데이터 ──────────────────────────────────────────────────────────
        with alt_tab2:
            from alt_data import EXPORT_SECTORS, _CUSTOMS_STAT_URL, _KITA_STAT_URL

            st.markdown("""
**관세청은 매월 1일·11일·21일에 10일 단위 수출 현황을 발표**합니다.
이를 분석하면 관련 수혜주의 실적을 실시간으로 역산할 수 있습니다.

> 반도체 수출액 증가 → 삼성전자·SK하이닉스 실적 선반영
> 자동차 수출 증가 → 현대차·기아 주가 선행
> 변압기 수출 증가 → 현대일렉트릭·효성중공업 수혜
""")

            sel_sector = st.selectbox(
                "섹터 선택", list(EXPORT_SECTORS.keys()), key="export_sector"
            )
            sector_info = EXPORT_SECTORS[sel_sector]

            # 섹터 정보 카드
            st.markdown(f"""
<div style="
    background:#1a2035; border:1px solid rgba(255,255,255,0.08);
    border-radius:10px; padding:16px 20px; margin:12px 0;
">
    <div style="color:#94a3b8; font-size:0.78rem;">HS코드</div>
    <div style="color:#e2e8f0; margin-bottom:10px;">{', '.join(sector_info['hs'])}</div>
    <div style="color:#94a3b8; font-size:0.78rem;">관련 종목/키워드</div>
    <div style="color:#60a5fa;">{' · '.join(sector_info['keywords'])}</div>
</div>
""", unsafe_allow_html=True)

            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                st.markdown("#### 📊 공식 데이터 소스")
                st.markdown(f"""
- **관세청 수출입 무역통계**: [customs.go.kr]({_CUSTOMS_STAT_URL})
- **무역협회 KITA 통계**: [stat.kita.net]({_KITA_STAT_URL})
- **관세청 Open API**: [unipass.customs.go.kr](https://unipass.customs.go.kr/ets/)

> API 키 발급 후 `secrets.toml`에 `[customs] api_key` 추가하면 자동 연동됩니다.
""")
            with col_ex2:
                st.markdown("#### 📅 발표 일정")
                st.markdown("""
| 날짜 | 내용 |
|------|------|
| 매월 1일 | 전월 확정 수출 통계 |
| 매월 11일 | 이달 1~10일 잠정 수출 |
| 매월 21일 | 이달 1~20일 잠정 수출 |

**활용법**: 수출 YoY 증가율 ≥ 20% 이상인 섹터의 대표 종목에 주목하세요.
""")

            # 네이버 데이터랩 연결 (키 있으면 수출 관련 키워드 트렌드 표시)
            if has_naver:
                st.markdown("---")
                st.markdown(f"**🔍 '{sel_sector}' 관련 검색 트렌드** (네이버 데이터랩)")
                export_kw = sector_info["keywords"]
                kw_key_ex = "|".join(export_kw)
                start_ex  = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
                try:
                    trend_ex = _cached_naver_trend(
                        kw_key_ex, naver_id, naver_secret, start_ex, "month"
                    )
                    if not trend_ex.empty:
                        price_for_ex = _cached_adv_price(adv_ticker, 365, is_kr)
                        from alt_data import plot_trend_vs_price
                        fig_ex = plot_trend_vs_price(
                            trend_ex, price_for_ex,
                            ticker=adv_ticker,
                            title=f"{sel_sector} 관련 검색 트렌드 vs {adv_ticker}",
                            show=False,
                        )
                        st.plotly_chart(fig_ex, use_container_width=True)
                except Exception as e:
                    st.caption(f"트렌드 로딩 실패: {e}")
            else:
                st.info(
                    "💡 네이버 API 키를 설정하면 '검색 트렌드' 탭에서 수출 섹터 키워드 트렌드를 "
                    "자동으로 연결해 보여줍니다."
                )
