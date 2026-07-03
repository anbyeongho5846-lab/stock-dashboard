"""페이지: 시장 감성 — 뉴스 기반 공포/탐욕 지수."""

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


def show_sentiment():
    from sentiment import fetch_market_news, analyze_sentiment, score_label, sentiment_gauge

    page_header("🧠", "시장 감성 분석",
                "네이버 금융 뉴스를 분석해 현재 시장 심리를 0(극도의 공포)~100(극도의 탐욕)으로 수치화합니다.")

    refresh_col, _ = st.columns([1, 6])
    with refresh_col:
        if st.button("🔄 지금 새로 분석"):
            st.cache_data.clear()
            st.rerun()

    st.caption("결과는 6시간 캐시됩니다 (오전·오후 각 1회 자동 갱신).")

    with st.spinner("뉴스 헤드라인 수집 및 감성 분석 중..."):
        headlines = fetch_market_news()
        score, fear_hits, greed_hits, colored = analyze_sentiment(headlines)
        label, color = score_label(score)

    gauge_col, info_col = st.columns([1, 1])

    with gauge_col:
        st.plotly_chart(sentiment_gauge(score), width="stretch")

    with info_col:
        st.markdown("#### 점수 해석 가이드")
        import pandas as pd
        guide_data = {
            "구간":        ["0 – 20",       "21 – 40",    "41 – 60", "61 – 80",    "81 – 100"],
            "심리":        ["극도의 공포",   "공포",       "중립",    "탐욕",       "극도의 탐욕"],
            "투자 시사점": [
                "역발상 매수 고려 (바닥 근접 가능성)",
                "저가 분할매수 검토",
                "중립 — 종목별 판단 필요",
                "과열 주의, 매수 신중",
                "버블 경계, 매도 타이밍 검토",
            ],
        }
        st.dataframe(pd.DataFrame(guide_data).set_index("구간"), width="stretch")

        st.markdown("#### 현재 감지 키워드")
        kw1, kw2 = st.columns(2)
        with kw1:
            st.markdown("**🔵 공포 키워드**")
            st.write(", ".join(fear_hits) if fear_hits else "없음")
        with kw2:
            st.markdown("**🔴 탐욕 키워드**")
            st.write(", ".join(greed_hits) if greed_hits else "없음")

    st.divider()
    st.markdown("#### 📰 분석 대상 뉴스 헤드라인 (최근 20건)")
    st.caption("🔵 공포성  🔴 탐욕성  ⚪ 중립")

    if not colored:
        st.warning("뉴스를 가져오지 못했습니다. 잠시 후 다시 시도하세요.")
    else:
        for icon, title in colored:
            st.markdown(f"{icon} {title}")

    st.divider()
    st.caption(f"수집된 헤드라인 수: {len(headlines)}건 | 출처: 네이버 금융 뉴스")
