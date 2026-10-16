"""페이지: 섹터/테마 — 네이버 업종·테마 현황 + 드릴다운."""

import html
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

_UP, _DOWN = "#ef4444", "#3b82f6"   # 국내 관례: 상승 빨강 / 하락 파랑


def _rank_card(title: str, rows: pd.DataFrame, accent: str) -> str:
    """강세/약세 TOP N 카드 HTML."""
    has_updn = "상승수" in rows.columns and "하락수" in rows.columns
    items = []
    for i, (_, r) in enumerate(rows.iterrows(), 1):
        v = float(r["등락률"])
        color = _UP if v > 0 else _DOWN if v < 0 else "#94a3b8"
        updn = (f'<span style="color:#64748b; font-size:0.75rem; margin-left:8px;">'
                f'▲{int(r["상승수"])} ▼{int(r["하락수"])}</span>') if has_updn else ""
        items.append(
            '<div style="display:flex; align-items:center; padding:7px 0;'
            ' border-top:1px solid rgba(255,255,255,0.06);">'
            f'<span style="width:22px; color:#64748b; font-weight:700;">{i}</span>'
            '<span style="flex:1; min-width:0; color:#e2e8f0; font-weight:600;'
            ' white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">'
            f'{html.escape(str(r["섹터명"]))}</span>'
            f'{updn}'
            f'<span style="color:{color}; font-weight:700; font-size:1.05rem;'
            f' margin-left:12px;">{v:+.2f}%</span>'
            '</div>'
        )
    return (
        f'<div style="background:#1a2035; border-radius:12px; padding:14px 18px;'
        f' border-left:4px solid {accent}; box-shadow:0 2px 8px rgba(0,0,0,0.3);">'
        f'<div style="color:#94a3b8; font-size:0.8rem; font-weight:600; margin-bottom:6px;">'
        f'{title}</div>{"".join(items)}</div>'
    )


def _clicked_name(event) -> str:
    """차트 클릭 이벤트에서 업종/테마 이름 추출 (트리맵: label / 바차트: y)."""
    if event and event.selection and event.selection.points:
        pt = event.selection.points[0]
        name = pt.get("label") or pt.get("y")
        if isinstance(name, str) and len(name) > 1:
            return name
    return ""


def show_sector():
    page_header("🗂️", "섹터 / 테마 현황",
                "네이버증권 업종별·테마별 등락률 현황을 히트맵과 바차트로 시각화합니다. "
                "업종/테마를 선택하면 소속 종목을 확인할 수 있습니다.")

    c1, c2, c3 = st.columns([2, 2, 6])
    with c1:
        type_label = st.selectbox("분류 선택", ["업종", "테마"], key="sec_type")
    with c2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 갱신", key="sec_refresh"):
            cached_sector.clear()
            cached_sector_detail.clear()

    type_code = "upjong" if type_label == "업종" else "theme"

    with st.spinner(f"{type_label} 데이터 수집 중..."):
        df = cached_sector(type_code)

    if df.empty:
        st.error("데이터를 가져오지 못했습니다.")
        return

    has_chg = "등락률" in df.columns and df["등락률"].notna().any()

    if has_chg:
        # ── 오늘의 강세·약세 TOP 3 (차트를 보지 않아도 핵심이 바로 보이게) ──
        ranked = df.dropna(subset=["등락률"]).sort_values("등락률", ascending=False)
        n_top = min(3, len(ranked) // 2) or 1
        chip(f"🏆 오늘의 강세·약세 {type_label}")
        t1, t2 = st.columns(2)
        t1.markdown(_rank_card(f"🔥 강세 TOP {n_top}", ranked.head(n_top), _UP),
                    unsafe_allow_html=True)
        t2.markdown(_rank_card(f"🧊 약세 TOP {n_top}",
                               ranked.tail(n_top).iloc[::-1], _DOWN),
                    unsafe_allow_html=True)
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        chg = df["등락률"].dropna()
        rising  = int((chg > 0).sum())
        falling = int((chg < 0).sum())
        flat    = len(df) - rising - falling
        avg_chg = float(chg.mean())

        chip("시장 요약")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"📋 전체 {type_label}", f"{len(df)}개")
        c2.metric("🔴 상승",  f"{rising}개",  f"{rising/len(df)*100:.0f}%")
        c3.metric("🔵 하락",  f"{falling}개", f"-{falling/len(df)*100:.0f}%")
        c4.metric("⬜ 보합",  f"{flat}개")
        c5.metric("📊 평균 등락률", f"{avg_chg:+.2f}%")

        if "상승수" in df.columns and "하락수" in df.columns:
            c6, c7, _, _ = st.columns(4)
            c6.metric("📈 종목 상승 합계", f"{int(df['상승수'].sum())}종목")
            c7.metric("📉 종목 하락 합계", f"{int(df['하락수'].sum())}종목")

    st.markdown("---")

    # ── 메인 차트: 히트맵 / 등락률 순위를 탭으로 분리 (각각 전체 폭 사용) ──────────
    from sector import plot_treemap, plot_bar

    chip(f"📊 {type_label}별 시세 현황")
    obj = "을" if type_label == "업종" else "를"
    st.caption(f"기준: {now_kst().strftime('%Y-%m-%d %H:%M')} (한국 시간) · "
               f"차트에서 {type_label}{obj} 클릭하면 아래 드릴다운에 자동 선택됩니다.")
    tab_map, tab_bar = st.tabs(["🗺️ 히트맵", "📊 등락률 순위"])
    with tab_map:
        ev_map = st.plotly_chart(plot_treemap(df, type_label), width="stretch",
                                 on_select="rerun", key=f"sec_tm_{type_code}")
    with tab_bar:
        n_all, top_n = int(df["등락률"].notna().sum()), 15
        show_all = n_all > top_n * 2 and st.toggle(
            f"전체 {n_all}개 보기", key=f"sec_bar_all_{type_code}")
        if n_all > top_n * 2 and not show_all:
            st.caption(f"상위 {top_n}개 · 하위 {top_n}개를 표시합니다. "
                       f"(막대에 마우스를 올리면 상세, 클릭하면 드릴다운)")
        ev_bar = st.plotly_chart(plot_bar(df, type_label, None if show_all else top_n),
                                 width="stretch", on_select="rerun",
                                 key=f"sec_bar_{type_code}")

    # 두 차트의 선택 상태가 모두 남아 있으므로, '새로 바뀐' 클릭만 반영
    valid_names = set(df["섹터명"].astype(str))
    for ev_key, ev in ((f"sec_tm_{type_code}", ev_map), (f"sec_bar_{type_code}", ev_bar)):
        clicked = _clicked_name(ev)
        if clicked in valid_names and st.session_state.get(f"{ev_key}_last") != clicked:
            st.session_state[f"{ev_key}_last"] = clicked
            st.session_state["sec_selected"] = clicked
            st.session_state["sec_drill_select"] = clicked

    # ── 전체 데이터 테이블 ────────────────────────────────────────────────────────
    with st.expander(f"📋 전체 {type_label} 데이터 ({len(df)}개)", expanded=False):
        display_cols = [c for c in ["섹터명", "등락률", "종목수", "상승수", "하락수"]
                        if c in df.columns]
        show_df = df[display_cols].copy()
        if "등락률" in show_df.columns:
            show_df = show_df.sort_values("등락률", ascending=False).reset_index(drop=True)
        fmt_df = show_df.copy()
        if "등락률" in fmt_df.columns:
            fmt_df["등락률"] = fmt_df["등락률"].apply(
                lambda v: f"{v:+.2f}%" if pd.notna(v) else "-")
        styled = fmt_df.style
        if "등락률" in fmt_df.columns:
            styled = styled.map(_color_change, subset=["등락률"])
        styled = styled.hide(axis="index")
        st.dataframe(styled, width="stretch")

    # ── 드릴다운: 소속 종목 조회 ─────────────────────────────────────────────────
    st.markdown("---")
    chip(f"🔎 {type_label} 드릴다운 — 소속 종목 조회")

    has_no = "sector_no" in df.columns and df["sector_no"].notna().any()

    if not has_no:
        st.info("섹터 번호를 가져오지 못해 드릴다운을 사용할 수 없습니다.")
    else:
        # 등락률 순으로 정렬한 섹터 목록
        sorted_sectors = (df.dropna(subset=["등락률"])
                            .sort_values("등락률", ascending=False)["섹터명"]
                            .tolist())
        options = ["— 선택 안 함 —"] + sorted_sectors

        # 업종↔테마 전환 등으로 기존 선택이 목록에 없으면 초기화
        # (차트 클릭은 위에서 sec_drill_select를 직접 설정)
        if st.session_state.get("sec_drill_select") not in options:
            pre = st.session_state.get("sec_selected", "")
            st.session_state["sec_drill_select"] = pre if pre in options else options[0]

        selected = st.selectbox(
            f"조회할 {type_label} 선택  (차트 셀을 클릭하면 자동 선택됩니다)",
            options,
            key="sec_drill_select",
        )

        if selected and selected != "— 선택 안 함 —":
            row = df[df["섹터명"] == selected]
            if row.empty or pd.isna(row["sector_no"].iloc[0]):
                st.warning("해당 섹터의 번호를 찾을 수 없습니다.")
            else:
                no = str(row["sector_no"].iloc[0]).split(".")[0]  # float → str

                with st.spinner(f"[{selected}] 소속 종목 수집 중..."):
                    detail = cached_sector_detail(type_code, no)

                if detail.empty:
                    st.warning("소속 종목 데이터를 가져오지 못했습니다.")
                else:
                    # 섹터 요약 헤더
                    chg_val = float(row["등락률"].iloc[0]) if "등락률" in row.columns else 0.0
                    n_stock = int(row["종목수"].iloc[0]) if "종목수" in row.columns else len(detail)
                    hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns(4)
                    hdr_col1.metric(f"📂 {selected}", f"{n_stock}개 종목",
                                    f"{chg_val:+.2f}%")
                    if "등락률" in detail.columns and detail["등락률"].notna().any():
                        d_chg = detail["등락률"].dropna()
                        hdr_col2.metric("🔴 상승 종목",
                                        f"{int((d_chg > 0).sum())}개")
                        hdr_col3.metric("🔵 하락 종목",
                                        f"{int((d_chg < 0).sum())}개")
                        hdr_col4.metric("📊 평균 등락률",
                                        f"{float(d_chg.mean()):+.2f}%")

                    # 소속 종목 바차트
                    if "등락률" in detail.columns and detail["등락률"].notna().any():
                        name_col = "종목명" if "종목명" in detail.columns else detail.columns[0]
                        bar_d = (detail.dropna(subset=["등락률"])
                                       .sort_values("등락률", ascending=True))

                        bar_colors = ["#e63946" if v >= 0 else "#457b9d"
                                      for v in bar_d["등락률"]]
                        bar_texts  = [f"{v:+.2f}%" for v in bar_d["등락률"]]

                        import plotly.graph_objects as _go
                        fig2 = _go.Figure()
                        fig2.add_trace(_go.Bar(
                            x=bar_d["등락률"],
                            y=bar_d[name_col].astype(str),
                            orientation="h",
                            marker_color=bar_colors,
                            text=bar_texts,
                            textposition="outside",
                            textfont=dict(size=10, color="rgba(230,230,230,0.95)"),
                            cliponaxis=False,
                            hovertemplate="<b>%{y}</b><br>등락률: %{x:+.2f}%<extra></extra>",
                        ))
                        max_abs2 = float(bar_d["등락률"].abs().max()) if len(bar_d) > 0 else 1.0
                        fig2.update_layout(
                            height=max(360, len(bar_d) * 26 + 80),
                            template="plotly_dark",
                            title=dict(
                                text=f"{selected} — 소속 종목 등락률",
                                font=dict(size=15),
                            ),
                            margin=dict(l=10, r=90, t=50, b=30),
                            xaxis=dict(
                                title="등락률 (%)",
                                range=[-(max_abs2 * 1.5), max_abs2 * 1.5],
                            ),
                            showlegend=False,
                        )
                        st.plotly_chart(fig2, width="stretch")

                    # 소속 종목 테이블
                    chip("종목 상세 테이블")
                    disp_cols = [c for c in ["종목명", "현재가", "등락률", "거래량", "시가총액"]
                                 if c in detail.columns]
                    tbl = detail[disp_cols].copy()
                    if "등락률" in tbl.columns:
                        tbl = tbl.sort_values("등락률", ascending=False).reset_index(drop=True)
                    fmt_tbl = tbl.copy()
                    if "등락률"  in fmt_tbl.columns:
                        fmt_tbl["등락률"]  = fmt_tbl["등락률"].apply(
                            lambda v: f"{v:+.2f}%" if pd.notna(v) else "-")
                    if "현재가"  in fmt_tbl.columns:
                        fmt_tbl["현재가"]  = fmt_tbl["현재가"].apply(
                            lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
                    if "거래량"  in fmt_tbl.columns:
                        fmt_tbl["거래량"]  = fmt_tbl["거래량"].apply(
                            lambda v: fmt_volume(v) if pd.notna(v) else "-")
                    if "시가총액" in fmt_tbl.columns:
                        fmt_tbl["시가총액"] = fmt_tbl["시가총액"].apply(
                            lambda v: fmt_market_cap(v * 1e8) if pd.notna(v) else "-")

                    styled2 = fmt_tbl.style
                    if "등락률" in fmt_tbl.columns:
                        styled2 = styled2.map(_color_change, subset=["등락률"])
                    styled2 = styled2.hide(axis="index")
                    st.dataframe(styled2, width="stretch")
