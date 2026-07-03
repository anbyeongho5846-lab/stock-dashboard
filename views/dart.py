"""페이지: DART 스크리너 — PER/PBR 밴드 + 저평가 스크리닝."""

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


def _get_dart_api_key() -> str | None:
    try:
        return st.secrets["dart"]["api_key"]
    except Exception:
        return None


def _fmt_per(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{v:.1f}배"


def _fmt_pbr(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{v:.2f}배"


def _color_grade(val: str) -> str:
    if "강력매수" in val: return "color:#34d399; font-weight:700"
    if "매수"    in val: return "color:#6ee7b7; font-weight:600"
    if "주의"    in val: return "color:#fbbf24; font-weight:600"
    if "매도"    in val: return "color:#f87171; font-weight:600"
    return "color:#94a3b8"


class DartCacheMissError(Exception):
    """재무 캐시가 없고 DART API에도 연결할 수 없을 때 발생."""
    pass


@st.cache_data(ttl=3600)
def cached_dart_financials(ticker: str, api_key: str, years: int):
    from dart_screener import (get_corp_code, fetch_annual_financials,
                                fetch_price_history, calc_band,
                                DartNetworkError, get_fin_from_cache)
    try:
        cc = get_corp_code(ticker, api_key)
    except DartNetworkError as e:
        raise e
    if not cc:
        return None, None, None, None

    # 캐시 먼저 확인 — 있으면 API 호출 없이 반환
    cached = get_fin_from_cache(ticker)
    if cached is not None and not cached.empty:
        price_df = fetch_price_history(ticker, years + 1)
        band_df  = calc_band(cached, price_df) if not price_df.empty else None
        return cc, cached, price_df, band_df

    # 캐시 없음 → API 호출 시도
    try:
        fin_df = fetch_annual_financials(api_key, cc, years, ticker=ticker)
    except DartNetworkError:
        raise DartCacheMissError(ticker)

    price_df = fetch_price_history(ticker, years + 1)
    band_df  = calc_band(fin_df, price_df) if not fin_df.empty and not price_df.empty else None
    return cc, fin_df, price_df, band_df


@st.cache_data(ttl=3600)
def cached_corp_name(corp_code: str, api_key: str) -> str:
    from dart_screener import _get_corp_name
    return _get_corp_name(api_key, corp_code) or corp_code


def _show_dart_network_error(detail: str = "") -> None:
    """DART 네트워크 오류 공통 안내 박스."""
    st.error(
        "**DART API 연결 실패** — Streamlit Cloud(해외 서버)에서는 "
        "`opendart.fss.or.kr`에 접속이 차단될 수 있습니다.\n\n"
        "**해결 방법:** 로컬 PC에서 아래 명령을 실행하여 "
        "`dart_corp_codes.json`을 생성한 뒤 GitHub에 커밋하세요.\n\n"
        "```\n"
        "cd stock_analyzer\n"
        "python generate_dart_cache.py\n"
        "git add dart_corp_codes.json\n"
        "git commit -m \"Add DART corp codes cache\"\n"
        "git push\n"
        "```"
    )
    if detail:
        with st.expander("상세 오류"):
            st.code(detail)


def show_dart_screener():
    page_header(
        "📊", "DART 기본적 분석 스크리너",
        "Open DART API 기반 EPS·BPS 수집 → 역사적 PER/PBR 밴드 분석 → 저평가 종목 스크리닝",
    )

    api_key = _get_dart_api_key()
    if not api_key:
        st.error(
            "DART API 키가 설정되지 않았습니다.  \n"
            "`.streamlit/secrets.toml`에 `[dart] api_key = \"발급받은키\"`를 추가하거나 "
            "Streamlit Cloud → Settings → Secrets에 등록해 주세요."
        )
        st.code("""[dart]\napi_key = "발급받은키\"""", language="toml")
        return

    # dart_screener 모듈 최초 임포트 (함수 진입 시 한 번만)
    try:
        import dart_screener as _ds
        from dart_screener import (
            search_corps, get_corp_name_map,
            fetch_price_history, calc_band,
            score_stock as _score_stock,
            plot_valuation_band as _plot_band,
            plot_screener_result as _plot_sc,
            _load_fin_cache, DartNetworkError,
        )
    except Exception as _import_err:
        st.error(
            f"**dart_screener 모듈 로드 실패**: `{type(_import_err).__name__}: {_import_err}`\n\n"
            "Streamlit Cloud 로그(Manage app)에서 상세 오류를 확인하세요."
        )
        return

    tab_single, tab_screen = st.tabs(["📈 개별 종목 밴드 분석", "🔍 저평가 스크리너"])

    # ── 탭1: 개별 종목 ─────────────────────────────────────────────────────────
    with tab_single:
        chip("종목 검색")
        sc1, sc2 = st.columns([4, 1])
        with sc1:
            search_q = st.text_input(
                "회사명 또는 종목코드 입력",
                placeholder="예: 삼성전자  /  현대차  /  005930",
                key="dart_search_q",
                label_visibility="collapsed",
            )
        with sc2:
            s_years = st.slider("기간(년)", 3, 7, 5, key="dart_single_years",
                                label_visibility="collapsed")

        # 검색 결과
        s_ticker = st.session_state.get("dart_selected_ticker", "")
        s_name   = st.session_state.get("dart_selected_name",   "")

        if search_q:
            hits = search_corps(search_q, max_results=50)
            if not hits:
                st.warning("검색 결과가 없습니다.")
            else:
                opts = []
                for h in hits:
                    badge = "✅" if h["has_cache"] else "⬜"
                    eps_str = f"  EPS:{h['latest_eps']:,.0f}" if h.get("latest_eps") else ""
                    opts.append(f"{badge} {h['corp_name']} ({h['ticker']}){eps_str}")

                picked = st.selectbox(
                    f"검색 결과 {len(hits)}개 (✅=재무데이터 있음)",
                    opts,
                    key="dart_search_sel",
                )
                if st.button("이 종목 분석", key="dart_search_go", width="content"):
                    idx = opts.index(picked)
                    st.session_state["dart_selected_ticker"] = hits[idx]["ticker"]
                    st.session_state["dart_selected_name"]   = hits[idx]["corp_name"]
                    s_ticker = hits[idx]["ticker"]
                    s_name   = hits[idx]["corp_name"]
                    st.rerun()

        if not s_ticker:
            st.info("위 검색창에서 종목을 찾아 선택하세요.  \n"
                    "예) '삼성' 입력 → 삼성전자, 삼성바이오로직스... 목록 표시")
            return

        with st.spinner(f"[{s_ticker}] DART 재무 데이터 수집 중..."):
            try:
                cc, fin_df, price_df, band_df = cached_dart_financials(
                    s_ticker.strip(), api_key, s_years
                )
            except DartCacheMissError as e:
                st.warning(
                    f"**{s_name} ({s_ticker})** 종목은 재무 캐시에 없습니다.  \n"
                    "Streamlit Cloud에서는 DART API 직접 호출이 차단됩니다.  \n\n"
                    "**로컬 PC에서 아래 명령을 실행한 뒤 커밋하면 이용 가능합니다:**\n"
                    "```\n"
                    f"python generate_dart_cache.py --fin-only --tickers {s_ticker}\n"
                    "git add dart_fin_cache.json\n"
                    f'git commit -m "Add {s_name} to cache"\n'
                    "git push\n"
                    "```"
                )
                return
            except Exception as e:
                _show_dart_network_error(str(e))
                return

        if cc is None:
            st.error("DART에서 해당 종목코드를 찾을 수 없습니다.  \n"
                     "`dart_corp_codes.json` 캐시가 없으면 로컬에서 먼저 실행해야 합니다.")
            return
        if fin_df is None or fin_df.empty:
            st.error("재무 데이터를 가져오지 못했습니다. 종목코드 또는 API 키를 확인하세요.")
            return

        name = s_name or cached_corp_name(cc, api_key)
        cur_price = float(price_df["Close"].iloc[-1]) if price_df is not None and not price_df.empty else 0

        s = _score_stock(band_df if band_df is not None else pd.DataFrame(),
                         cur_price, fin_df)

        # ── 종목 헤더 ──────────────────────────────────────────────────────────
        grade_color_map = {
            "강력매수": "#34d399", "매수": "#6ee7b7",
            "중립": "#94a3b8", "주의": "#fbbf24", "매도": "#f87171",
        }
        g_color = grade_color_map.get(s["grade"], "#94a3b8")
        st.markdown(
            f'<div style="background:#1a2035; border-radius:12px; padding:16px 20px; '
            f'margin-bottom:16px; border-left:4px solid #3b82f6;">'
            f'<div style="font-size:1.3rem; font-weight:700; color:#e2e8f0;">{name}</div>'
            f'<div style="font-size:0.82rem; color:#718096; margin-top:4px;">'
            f'<code style="background:#0e1117; padding:2px 8px; border-radius:4px;">{s_ticker}</code>'
            f'&nbsp;&nbsp;DART 코드: {cc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── 핵심 지표 ──────────────────────────────────────────────────────────
        chip("핵심 밸류에이션")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("💰 현재가",  f"{cur_price:,.0f}원" if cur_price else "N/A")
        c2.metric("📊 현재 PER", _fmt_per(s["cur_per"]))
        c3.metric("📘 현재 PBR", _fmt_pbr(s["cur_pbr"]))
        c4.metric("💵 EPS",     f"{s['eps']:,.0f}원" if s["eps"] else "N/A")
        c5.metric("🏦 BPS",     f"{s['bps']:,.0f}원" if s["bps"] else "N/A")

        # 역사적 평균 PER/PBR
        if band_df is not None and not band_df.empty:
            chip("역사적 밴드 요약")
            c6, c7, c8, c9 = st.columns(4)
            if "per_avg" in band_df.columns and band_df["per_avg"].notna().any():
                p_avg = band_df["per_avg"].dropna().mean()
                p_lo  = band_df["per_low"].dropna().mean()
                p_hi  = band_df["per_high"].dropna().mean()
                c6.metric("📉 PER 역사 평균",  f"{p_avg:.1f}배")
                c7.metric("📉 PER 역사 범위",  f"{p_lo:.1f}~{p_hi:.1f}배")
            if "pbr_avg" in band_df.columns and band_df["pbr_avg"].notna().any():
                q_avg = band_df["pbr_avg"].dropna().mean()
                q_lo  = band_df["pbr_low"].dropna().mean()
                q_hi  = band_df["pbr_high"].dropna().mean()
                c8.metric("📉 PBR 역사 평균",  f"{q_avg:.2f}배")
                c9.metric("📉 PBR 역사 범위",  f"{q_lo:.2f}~{q_hi:.2f}배")

        # ── 저평가 점수 ────────────────────────────────────────────────────────
        chip("저평가 종합 점수")
        sc1, sc2 = st.columns([1, 3])
        sc1.metric(
            f"종합 점수 ({s['grade']})",
            f"{s['score']} / 100",
        )
        if s["reasons"]:
            with sc2:
                for reason in s["reasons"]:
                    st.markdown(
                        f'<div style="font-size:0.82rem; color:#94a3b8; '
                        f'padding:2px 0;">• {reason}</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("---")

        # ── 밴드 차트 ──────────────────────────────────────────────────────────
        if price_df is not None and not price_df.empty:
            fig = _plot_band(
                s_ticker, name, price_df, fin_df,
                band_df if band_df is not None else pd.DataFrame(),
                show=False,
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("주가 데이터를 가져오지 못했습니다.")

        # ── 재무 데이터 테이블 ─────────────────────────────────────────────────
        with st.expander("📋 연간 재무 데이터 (DART)", expanded=False):
            disp = fin_df.copy()
            fmt_cols = {
                "revenue":   "매출액",
                "op_income": "영업이익",
                "net_income":"순이익",
                "eps":       "EPS(원)",
                "bps":       "BPS(원)",
            }
            disp = disp.rename(columns={"year": "연도", **fmt_cols})
            for col in ["매출액", "영업이익", "순이익"]:
                if col in disp.columns:
                    disp[col] = disp[col].apply(
                        lambda v: f"{v/1e8:,.0f}억원" if pd.notna(v) else "-"
                    )
            for col in ["EPS(원)", "BPS(원)"]:
                if col in disp.columns:
                    disp[col] = disp[col].apply(
                        lambda v: f"{v:,.0f}" if pd.notna(v) else "-"
                    )
            drop = [c for c in ["fs_div"] if c in disp.columns]
            st.dataframe(disp.drop(columns=drop).set_index("연도"),
                         width="stretch")

        if band_df is not None and not band_df.empty:
            with st.expander("📋 연간 PER/PBR 밴드 데이터", expanded=False):
                bd = band_df.copy()
                for col in ["per_high", "per_low", "per_avg",
                            "pbr_high", "pbr_low", "pbr_avg"]:
                    if col in bd.columns:
                        bd[col] = bd[col].apply(
                            lambda v: f"{v:.1f}배" if pd.notna(v) else "-"
                        )
                for col in ["p_high", "p_low", "p_avg"]:
                    if col in bd.columns:
                        bd[col] = bd[col].apply(
                            lambda v: f"{v:,.0f}" if pd.notna(v) else "-"
                        )
                st.dataframe(bd.set_index("year"), width="stretch")

    # ── 탭2: 저평가 스크리너 ───────────────────────────────────────────────────
    with tab_screen:
        fin_cache = _load_fin_cache()
        n_cached  = len(fin_cache)

        # ── 필터 설정 ──────────────────────────────────────────────────────────
        chip("스크리닝 설정")
        with st.expander("⚙️ 필터 / 검색 옵션", expanded=True):
            fc1, fc2, fc3 = st.columns([3, 2, 2])
            with fc1:
                sc_search = st.text_input(
                    "회사명 또는 종목코드 필터 (비우면 전체)",
                    placeholder="예: 현대  /  삼성  /  005930",
                    key="dart_sc_search",
                )
            with fc2:
                sc_grade = st.multiselect(
                    "의견 필터",
                    ["강력매수", "매수", "중립", "주의", "매도"],
                    default=["강력매수", "매수"],
                    key="dart_sc_grade",
                )
            with fc3:
                sc_min_score = st.slider("최소 점수", 0, 100, 50, key="dart_sc_minscore")

            run_sc = st.button(
                f"▶ 캐시 종목 스크리닝 실행 ({n_cached:,}개 종목, 즉시)",
                width="stretch", key="dart_sc_run",
            )
            st.caption(
                "💡 재무 데이터가 캐시된 종목만 스크리닝합니다.  "
                "로컬에서 `python generate_dart_cache.py --all` 실행 후 커밋하면 전체 상장사 검색 가능."
            )

        if "dart_sc_result" not in st.session_state:
            st.session_state.dart_sc_result = None

        if run_sc:
            if not fin_cache:
                st.error("재무 데이터 캐시(dart_fin_cache.json)가 없습니다.")
            else:
                # 캐시에서 바로 스크리닝 (API 호출 없음)
                with st.spinner(f"캐시 {n_cached:,}개 종목 스크리닝 중..."):
                    name_map_sc = get_corp_name_map()
                    q_lower = sc_search.strip().lower()

                    results = []
                    for tk, entry in fin_cache.items():
                        # 이름/코드 필터
                        corp_nm = entry.get("corp_name", tk)
                        if q_lower and q_lower not in corp_nm.lower() and q_lower not in tk.lower():
                            continue

                        rows = entry.get("financials", [])
                        if not rows:
                            continue
                        fin_df = pd.DataFrame(rows)
                        if fin_df.empty:
                            continue

                        try:
                            price_df = fetch_price_history(tk, 7)
                            if price_df.empty:
                                continue
                            cur_price = float(price_df["Close"].iloc[-1])
                            band_df   = calc_band(fin_df, price_df)
                            s         = _score_stock(band_df, cur_price, fin_df)

                            # 의견/점수 필터
                            if sc_grade and s["grade"] not in sc_grade:
                                continue
                            if s["score"] < sc_min_score:
                                continue

                            results.append(dict(
                                ticker=tk,
                                name=corp_nm,
                                cur_price=cur_price,
                                fin_df=fin_df,
                                price_df=price_df,
                                band_df=band_df,
                                **s,
                            ))
                        except Exception:
                            continue

                    results.sort(key=lambda x: x["score"], reverse=True)

                st.session_state.dart_sc_result = results
                if not results:
                    st.warning("조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.")

        if st.session_state.dart_sc_result:
            results = st.session_state.dart_sc_result
            if not results:
                return

            # ── 요약 메트릭 ────────────────────────────────────────────────────
            n_buy  = sum(1 for r in results if r["grade"] in ("강력매수", "매수"))
            n_sell = sum(1 for r in results if r["grade"] in ("주의", "매도"))
            n_neut = len(results) - n_buy - n_sell
            top    = results[0]

            chip("스크리닝 요약")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📋 분석 종목", f"{len(results)}개")
            c2.metric("🟢 매수 의견", f"{n_buy}개")
            c3.metric("⬜ 중립 의견", f"{n_neut}개")
            c4.metric("🔴 주의/매도",  f"{n_sell}개")

            st.markdown("---")

            # ── 버블 차트 ──────────────────────────────────────────────────────
            fig_sc = _plot_sc(results, show=False)
            st.plotly_chart(fig_sc, width="stretch")

            # ── 결과 테이블 ────────────────────────────────────────────────────
            chip("종목별 결과 (점수 순)")
            rows = []
            for r in results:
                rows.append({
                    "종목명":   r.get("name", r["ticker"]),
                    "코드":     r["ticker"],
                    "현재가":   f"{r['cur_price']:,.0f}",
                    "현재PER":  _fmt_per(r.get("cur_per")),
                    "현재PBR":  _fmt_pbr(r.get("cur_pbr")),
                    "EPS":      f"{r['eps']:,.0f}원" if r.get("eps") else "N/A",
                    "BPS":      f"{r['bps']:,.0f}원" if r.get("bps") else "N/A",
                    "점수":     f"{r['score']}",
                    "의견":     r["grade"],
                    "주요 근거": r["reasons"][0] if r.get("reasons") else "-",
                })

            sc_df = pd.DataFrame(rows)
            styled = (
                sc_df.style
                .map(_color_grade, subset=["의견"])
                .set_properties(**{"text-align": "center"})
                .hide(axis="index")
            )
            st.dataframe(styled, width="stretch")

            # ── 개별 상세 조회 (탭2 내 드릴다운) ─────────────────────────────
            st.markdown("---")
            chip("📌 개별 종목 상세 분석")
            ticker_opts = [f"{r.get('name', r['ticker'])} ({r['ticker']})"
                           for r in results]
            selected_opt = st.selectbox(
                "상세 분석할 종목 선택", ticker_opts, key="dart_drill_sel"
            )
            if selected_opt:
                idx   = ticker_opts.index(selected_opt)
                r_sel = results[idx]

                if r_sel.get("price_df") is not None and not r_sel["price_df"].empty:
                    fig_d = _plot_band(
                        r_sel["ticker"], r_sel.get("name", r_sel["ticker"]),
                        r_sel["price_df"], r_sel["fin_df"],
                        r_sel.get("band_df", pd.DataFrame()),
                        show=False,
                    )
                    st.plotly_chart(fig_d, width="stretch")
                else:
                    st.warning("주가 데이터를 가져오지 못했습니다.")

                if r_sel.get("reasons"):
                    with st.expander("📝 저평가 판단 근거", expanded=True):
                        for reason in r_sel["reasons"]:
                            st.markdown(f"• {reason}")
