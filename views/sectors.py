"""페이지: 섹터/테마 — 네이버 업종·테마 현황 + 드릴다운."""

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

    # ── 메인 차트 (클릭 이벤트 캡처) ────────────────────────────────────────────
    from sector import plot as _plot_sector
    fig = _plot_sector(df, type_label, show=False)

    chart_event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        key=f"sec_chart_{type_code}",
    )

    # 클릭한 섹터 이름 추출 (트리맵: label / 바차트: y)
    if chart_event and chart_event.selection and chart_event.selection.points:
        pt = chart_event.selection.points[0]
        clicked = pt.get("label") or pt.get("y")
        if clicked and isinstance(clicked, str) and len(clicked) > 1:
            st.session_state["sec_selected"] = clicked

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
        st.dataframe(styled, use_container_width=True)

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

        # 클릭으로 설정된 섹터를 기본 선택으로
        default_idx = 0
        pre = st.session_state.get("sec_selected", "")
        if pre in options:
            default_idx = options.index(pre)

        selected = st.selectbox(
            f"조회할 {type_label} 선택  (차트 셀을 클릭하면 자동 선택됩니다)",
            options,
            index=default_idx,
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
                        st.plotly_chart(fig2, use_container_width=True)

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
                    st.dataframe(styled2, use_container_width=True)
