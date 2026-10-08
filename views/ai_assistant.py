"""페이지: AI 투자 비서 — 종목 데이터 기반 대화형 질의(Gemini)."""

import json

import pandas as pd
import streamlit as st

from common import (
    page_header, chip, detect_market, now_kst,
    fmt_market_cap, fmt_volume,
    _color_change, _color_opinion, _color_result, _color_excess, _color_pnl,
    cached_rankings, cached_sector, cached_stock, cached_fundamental,
    cached_ownership, cached_price_kr, cached_sector_detail, cached_scan,
    cached_news, _render_news,
    stock_picker, goto_stock, kr_stock_labels,
)

_MAX_Q = 25   # 세션당 질문 한도 (비용·남용 방어)


def _stock_context(ticker: str, is_kr: bool, days: int = 120) -> dict | None:
    """종목의 핵심 데이터(지표·뉴스)를 AI에 넘길 dict로."""
    df = cached_stock(ticker, is_kr, days)
    if df.empty:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    def _n(k):
        v = last.get(k)
        return round(float(v), 2) if v is not None and pd.notna(v) else None

    name = ticker
    if is_kr:
        for lab in kr_stock_labels():
            if lab.endswith(f"({ticker})"):
                name = lab.rsplit("(", 1)[0].strip()
                break

    ctx = {
        "종목명": name, "코드": ticker, "시장": "국내" if is_kr else "미국",
        "현재가": round(float(last["Close"]), 2),
        "전일대비_%": round((last["Close"] - prev["Close"]) / prev["Close"] * 100, 2)
                    if prev["Close"] else 0.0,
        "RSI14": _n("RSI"), "MA5": _n("MA5"), "MA20": _n("MA20"),
        "MA60": _n("MA60"), "MACD": _n("MACD"),
    }
    try:
        _i, _s, summ = cached_news(ticker, "", is_kr)
        if summ:
            ctx["뉴스감성"] = {"긍정": summ.get("positive"), "부정": summ.get("negative"),
                            "중립": summ.get("neutral"), "종합": summ.get("overall")}
    except Exception:
        pass
    return ctx


def _build_system(contexts: list) -> str:
    facts = json.dumps(contexts, ensure_ascii=False, indent=1)
    return (
        "당신은 한국 주식 투자 비서입니다. 사용자의 질문에 아래 '데이터'에 있는 수치만 근거로 답하세요.\n"
        "규칙:\n"
        "- 데이터에 없는 수치·목표가·사건·재무수치는 지어내지 말 것. 모르면 "
        "'제공된 데이터로는 알 수 없습니다'라고 답할 것.\n"
        "- 지지선·저항선·과열 여부 등은 데이터의 이동평균·RSI·MACD·뉴스감성에서 끌어낼 것.\n"
        "- '반드시 매수/매도'·수익 보장 같은 단정은 금지. '~로 보입니다', '~ 가능성이 있습니다', "
        "'유의가 필요합니다' 같은 신중한 표현을 쓸 것.\n"
        "- 초보자도 이해하도록 쉽게, 3~6문장으로.\n"
        "- 이것은 투자 자문이 아니라 데이터 요약·설명임.\n\n"
        f"[데이터]\n{facts}"
    )


def show_ai_assistant():
    from ai_report import ask_gemini, DISCLAIMER

    page_header("🗣️", "AI 투자 비서",
                "종목을 고르고 자유롭게 물어보세요. 앱의 실시간 데이터로 답합니다.")

    with st.expander("💡 사용법", expanded=False):
        st.markdown(
            "- 아래에서 **분석할 종목을 1~2개 고르고**, 궁금한 걸 말하듯 질문하세요.\n"
            "- 예: \"지금 기술적으로 어때?\", \"저평가야?\", \"두 종목 중 뭐가 나아?\", \"리스크는?\"\n"
            "- AI는 **현재가·이동평균·RSI·MACD·뉴스 감성** 데이터를 근거로 답합니다 (지어내지 않음).\n"
            "- 투자 조언이 아니라 데이터 요약·설명입니다."
        )

    # ── API 키 확인 ──────────────────────────────────────────────────────────
    try:
        api_key = st.secrets["gemini"]["api_key"]
    except Exception:
        api_key = ""
    if not api_key:
        st.info(
            "💡 **AI 비서는 Gemini API 키 설정 시 활성화됩니다.** "
            "`.streamlit/secrets.toml`(로컬)과 Streamlit Cloud *Settings → Secrets*에 추가하세요:\n"
            "```toml\n[gemini]\napi_key = \"발급받은_키\"\n```"
        )
        return

    # ── 종목 선택 ────────────────────────────────────────────────────────────
    chip("분석 대상 종목")
    c1, c2 = st.columns(2)
    with c1:
        t1, k1 = stock_picker("aiq1", default_code="005930", label="종목 1")
    stocks = [(t1.strip().upper(), k1)] if t1.strip() else []
    with c2:
        use2 = st.checkbox("두 번째 종목도 분석/비교", key="aiq_use2")
        if use2:
            t2, k2 = stock_picker("aiq2", default_code="000660", label="종목 2")
            if t2.strip():
                stocks.append((t2.strip().upper(), k2))

    with st.spinner("종목 데이터 수집 중..."):
        contexts = [c for c in (_stock_context(t, k) for t, k in stocks) if c]

    if not contexts:
        st.warning("종목 데이터를 불러오지 못했습니다. 종목을 확인하세요.")
        return

    # 수집된 데이터 요약 표시
    cols = st.columns(len(contexts))
    for i, ctx in enumerate(contexts):
        chg = ctx["전일대비_%"]
        rsi = ctx.get("RSI14")
        cols[i].markdown(
            f"**{ctx['종목명']}** `{ctx['코드']}`  \n"
            f"현재가 {ctx['현재가']:,.0f} ({chg:+.2f}%) · "
            f"RSI {rsi if rsi is not None else '-'}"
        )

    st.markdown("---")

    # ── 대화 ─────────────────────────────────────────────────────────────────
    if "aiq_chat" not in st.session_state:
        st.session_state.aiq_chat = []

    top1, top2 = st.columns([5, 1])
    top1.caption(f"질문 {st.session_state.get('aiq_count', 0)} / {_MAX_Q}회")
    if top2.button("🗑️ 대화 초기화", key="aiq_clear"):
        st.session_state.aiq_chat = []
        st.session_state["aiq_count"] = 0
        st.rerun()

    for m in st.session_state.aiq_chat:
        with st.chat_message(m["role"]):
            st.markdown(m["text"])

    # 추천 질문 (대화 없을 때)
    if not st.session_state.aiq_chat:
        st.caption("예시 질문:")
        examples = ["지금 기술적으로 어떤 상태야?", "저평가 구간일까?",
                    "매수 타이밍으로 괜찮아?", "지금 리스크는 뭐야?"]
        ecols = st.columns(len(examples))
        for i, e in enumerate(examples):
            if ecols[i].button(e, key=f"aiq_ex{i}", use_container_width=True):
                st.session_state["aiq_pending"] = e

    q = st.chat_input("무엇이든 물어보세요 (예: 지금 사도 될까?)")
    q = q or st.session_state.pop("aiq_pending", None)

    if q:
        if st.session_state.get("aiq_count", 0) >= _MAX_Q:
            st.warning(f"이 세션의 질문 한도({_MAX_Q}회)에 도달했습니다. 새로고침 후 이어가세요.")
        else:
            st.session_state.aiq_chat.append({"role": "user", "text": q})
            with st.chat_message("user"):
                st.markdown(q)

            system = _build_system(contexts)
            msgs = [{"role": ("model" if m["role"] == "assistant" else "user"),
                     "text": m["text"]} for m in st.session_state.aiq_chat]
            with st.chat_message("assistant"):
                with st.spinner("데이터를 분석하는 중..."):
                    ans = ask_gemini(system, msgs, api_key)
                st.markdown(ans)
            st.session_state.aiq_chat.append({"role": "assistant", "text": ans})
            st.session_state["aiq_count"] = st.session_state.get("aiq_count", 0) + 1

    st.caption("ℹ️ " + DISCLAIMER)
