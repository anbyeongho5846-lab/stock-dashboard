import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from pykrx import stock

# ── 페이지 설정 ──────────────────────────────────────
st.set_page_config(
    page_title="주식 분석 대시보드",
    page_icon="📈",
    layout="wide"
)

st.title("📈 주식 분석 대시보드")

# ── 사이드바 ─────────────────────────────────────────
st.sidebar.header("종목 설정")

market = st.sidebar.radio("시장 선택", ["미국", "국내"])

if market == "미국":
    ticker = st.sidebar.text_input("티커 입력", value="AAPL").upper()
else:
    ticker = st.sidebar.text_input("종목코드 입력", value="005930")

period = st.sidebar.selectbox("기간 선택", ["3개월", "6개월", "1년", "2년"])

indicators = st.sidebar.multiselect(
    "지표 선택",
    ["MA5", "MA20", "MA60", "RSI", "MACD"],
    default=["MA5", "MA20", "RSI"]
)

show_signals = st.sidebar.checkbox("매매 신호 표시", value=True)

# ── 기간 변환 ────────────────────────────────────────
period_map = {
    "3개월": ("3mo", 90),
    "6개월": ("6mo", 180),
    "1년":   ("1y",  365),
    "2년":   ("2y",  730),
}
yf_period, days = period_map[period]

# ── 데이터 수집 함수 ─────────────────────────────────
@st.cache_data(ttl=3600)
def get_us_data(ticker, period):
    return yf.download(ticker, period=period, progress=False)

@st.cache_data(ttl=3600)
def get_us_52w(ticker):
    return yf.download(ticker, period="1y", progress=False)

@st.cache_data(ttl=3600)
def get_kr_data(ticker, days):
    from datetime import datetime, timedelta
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    df    = stock.get_market_ohlcv(start, end, ticker)
    df.columns = ["Open", "High", "Low", "Close", "Volume", "Change"]
    return df

@st.cache_data(ttl=3600)
def get_kr_52w(ticker):
    from datetime import datetime, timedelta
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=365)).strftime("%Y%m%d")
    df    = stock.get_market_ohlcv(start, end, ticker)
    df.columns = ["Open", "High", "Low", "Close", "Volume", "Change"]
    return df

@st.cache_data(ttl=3600)
def get_us_financials(ticker):
    t    = yf.Ticker(ticker)
    info = t.info
    return {
        "PER":        info.get("trailingPE"),
        "PBR":        info.get("priceToBook"),
        "ROE":        info.get("returnOnEquity"),
        "ROA":        info.get("returnOnAssets"),
        "매출액":     info.get("totalRevenue"),
        "순이익":     info.get("netIncomeToCommon"),
        "부채비율":   info.get("debtToEquity"),
        "시가총액":   info.get("marketCap"),
        "배당수익률": info.get("dividendYield"),
        "EPS":        info.get("trailingEps"),
    }

@st.cache_data(ttl=3600)
def get_us_income(ticker):
    t  = yf.Ticker(ticker)
    try:
        df = t.financials
        if df is not None and not df.empty:
            df.columns = [str(c)[:4] for c in df.columns]
        return df
    except:
        return None

@st.cache_data(ttl=3600)
def get_kr_financials(ticker):
    try:
        t    = yf.Ticker(f"{ticker}.KS")
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            t    = yf.Ticker(f"{ticker}.KQ")
            info = t.info
        return info
    except:
        return None

@st.cache_data(ttl=3600)
def get_kr_income(ticker):
    try:
        t  = yf.Ticker(f"{ticker}.KS")
        df = t.financials
        if df is None or df.empty:
            t  = yf.Ticker(f"{ticker}.KQ")
            df = t.financials
        if df is not None and not df.empty:
            df.columns = [str(c)[:4] for c in df.columns]
        return df
    except:
        return None

# ── 지표 계산 함수 ───────────────────────────────────
def calc_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    return (100 - (100 / (1 + rs))).round(2)

def calc_macd(series):
    ema12  = series.ewm(span=12).mean()
    ema26  = series.ewm(span=26).mean()
    macd   = (ema12 - ema26).round(2)
    signal = macd.ewm(span=9).mean().round(2)
    hist   = (macd - signal).round(2)
    return macd, signal, hist

def calc_signals(close, ma5, ma20, rsi):
    golden   = (ma5 > ma20) & (ma5.shift(1) <= ma20.shift(1))
    dead     = (ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))
    rsi_buy  = (rsi < 30)   & (rsi.shift(1) >= 30)
    rsi_sell = (rsi > 70)   & (rsi.shift(1) <= 70)
    return golden, dead, rsi_buy, rsi_sell

def get_close(ticker, market, yf_period, days):
    if market == "미국":
        df    = get_us_data(ticker, yf_period)
        close = df["Close"][ticker] if ticker in df["Close"] else df["Close"].iloc[:, 0]
    else:
        df    = get_kr_data(ticker, days)
        close = df["Close"]
    return close

# ── 데이터 로드 ──────────────────────────────────────
with st.spinner("데이터 불러오는 중..."):
    try:
        if market == "미국":
            df     = get_us_data(ticker, yf_period)
            df_52w = get_us_52w(ticker)
            close  = df["Close"][ticker]  if ticker in df["Close"]  else df["Close"].iloc[:, 0]
            open_  = df["Open"][ticker]   if ticker in df["Open"]   else df["Open"].iloc[:, 0]
            high   = df["High"][ticker]   if ticker in df["High"]   else df["High"].iloc[:, 0]
            low    = df["Low"][ticker]    if ticker in df["Low"]    else df["Low"].iloc[:, 0]
            volume = df["Volume"][ticker] if ticker in df["Volume"] else df["Volume"].iloc[:, 0]
            h52    = df_52w["High"][ticker]  if ticker in df_52w["High"]  else df_52w["High"].iloc[:, 0]
            l52    = df_52w["Low"][ticker]   if ticker in df_52w["Low"]   else df_52w["Low"].iloc[:, 0]
            currency = "USD"
        else:
            df       = get_kr_data(ticker, days)
            df_52w   = get_kr_52w(ticker)
            close    = df["Close"]
            open_    = df["Open"]
            high     = df["High"]
            low      = df["Low"]
            volume   = df["Volume"]
            h52      = df_52w["High"]
            l52      = df_52w["Low"]
            currency = "KRW"

        if len(df) == 0:
            st.error("데이터를 찾을 수 없습니다.")
            st.stop()

    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

# ── 지표 계산 ────────────────────────────────────────
ma5  = close.rolling(window=5).mean()
ma20 = close.rolling(window=20).mean()
ma60 = close.rolling(window=60).mean()
rsi  = calc_rsi(close)
macd, signal, hist = calc_macd(close)
golden, dead, rsi_buy, rsi_sell = calc_signals(close, ma5, ma20, rsi)

week52_high   = h52.max()
week52_low    = l52.min()
current_price = close.iloc[-1]
prev_price    = close.iloc[-2]
change        = current_price - prev_price
change_pct    = (change / prev_price) * 100
week52_pct    = (current_price - week52_low) / (week52_high - week52_low) * 100

# ── 요약 카드 ────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("현재가",    f"{current_price:,.0f} {currency}")
col2.metric("전일 대비", f"{change:+,.0f}", f"{change_pct:+.2f}%")
col3.metric("RSI",       f"{rsi.iloc[-1]:.1f}")
col4.metric("MACD",      f"{macd.iloc[-1]:.2f}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("52주 최고가", f"{week52_high:,.0f} {currency}")
col6.metric("52주 최저가", f"{week52_low:,.0f} {currency}")
col7.metric("52주 위치",   f"{week52_pct:.1f}%",
            "신고가 근접" if week52_pct >= 90 else ("신저가 근접" if week52_pct <= 10 else "중간"))
col8.metric("52주 등락폭", f"{((week52_high - week52_low) / week52_low * 100):.1f}%")

st.divider()

# ── 탭 구성 ──────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📈 차트 분석", "📊 재무제표", "⚖️ 종목 비교", "⭐ 관심 종목"])

# ════════════════════════════════════════════════════
# 탭 1 — 차트
# ════════════════════════════════════════════════════
with tab1:

    if show_signals:
        st.subheader("🚨 최근 매매 신호")
        sig_col1, sig_col2, sig_col3, sig_col4 = st.columns(4)

        def last_signal_date(mask):
            dates = close.index[mask]
            return dates[-1].strftime("%Y-%m-%d") if len(dates) > 0 else "없음"

        sig_col1.metric("골든크로스 (매수)", last_signal_date(golden),   "MA5 > MA20 돌파")
        sig_col2.metric("데드크로스 (매도)", last_signal_date(dead),     "MA5 < MA20 하락")
        sig_col3.metric("RSI 과매도 (매수)", last_signal_date(rsi_buy),  "RSI 30 이하")
        sig_col4.metric("RSI 과매수 (매도)", last_signal_date(rsi_sell), "RSI 70 이상")

    show_rsi  = "RSI"  in indicators
    show_macd = "MACD" in indicators
    num_rows  = 1 + True + show_rsi + show_macd

    row_heights = [0.5, 0.15]
    if show_rsi:  row_heights.append(0.175)
    if show_macd: row_heights.append(0.175)

    fig = make_subplots(
        rows=num_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.03
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=open_, high=high, low=low, close=close,
        name=ticker
    ), row=1, col=1)

    if "MA5"  in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=ma5,  name="MA5",  line=dict(color="blue",   width=1)), row=1, col=1)
    if "MA20" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=ma20, name="MA20", line=dict(color="orange", width=1)), row=1, col=1)
    if "MA60" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=ma60, name="MA60", line=dict(color="green",  width=1)), row=1, col=1)

    fig.add_hline(y=week52_high, line_dash="dot", line_color="red",
                  annotation_text=f"52주 최고가 {week52_high:,.0f}",
                  annotation_position="top right", row=1, col=1)
    fig.add_hline(y=week52_low,  line_dash="dot", line_color="blue",
                  annotation_text=f"52주 최저가 {week52_low:,.0f}",
                  annotation_position="bottom right", row=1, col=1)

    if show_signals:
        fig.add_trace(go.Scatter(
            x=close.index[golden], y=low[golden] * 0.98,
            mode="markers+text", name="골든크로스", text="▲",
            textposition="bottom center",
            marker=dict(color="green", size=14, symbol="triangle-up"),
            textfont=dict(color="green", size=12),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=close.index[dead], y=high[dead] * 1.02,
            mode="markers+text", name="데드크로스", text="▼",
            textposition="top center",
            marker=dict(color="red", size=14, symbol="triangle-down"),
            textfont=dict(color="red", size=12),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=close.index[rsi_buy], y=low[rsi_buy] * 0.97,
            mode="markers", name="RSI 매수",
            marker=dict(color="skyblue", size=12, symbol="triangle-up"),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=close.index[rsi_sell], y=high[rsi_sell] * 1.03,
            mode="markers", name="RSI 매도",
            marker=dict(color="orange", size=12, symbol="triangle-down"),
        ), row=1, col=1)

    volume_colors = ["#ef5350" if c >= o else "#26a69a"
                     for c, o in zip(close, open_)]
    fig.add_trace(go.Bar(
        x=df.index, y=volume, name="거래량",
        marker_color=volume_colors
    ), row=2, col=1)

    if show_rsi:
        rsi_row = 3
        fig.add_trace(go.Scatter(
            x=df.index, y=rsi, name="RSI",
            line=dict(color="purple", width=1)
        ), row=rsi_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red",   row=rsi_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=rsi_row, col=1)

    if show_macd:
        macd_row = 3 + show_rsi
        fig.add_trace(go.Scatter(x=df.index, y=macd,   name="MACD",   line=dict(color="blue",   width=1)), row=macd_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color="orange", width=1)), row=macd_row, col=1)
        fig.add_trace(go.Bar(    x=df.index, y=hist,   name="Hist",   marker_color="gray"),                row=macd_row, col=1)

    fig.update_layout(
        title=f"{ticker} 종합 차트",
        xaxis_rangeslider_visible=False,
        height=800,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("최근 10일 데이터")
    table = pd.DataFrame({
        "시가":      open_.round(2),
        "고가":      high.round(2),
        "저가":      low.round(2),
        "종가":      close.round(2),
        "거래량":    volume.map("{:,.0f}".format),
        "MA5":       ma5.round(2),
        "MA20":      ma20.round(2),
        "RSI":       rsi,
        "MACD":      macd,
        "골든크로스": golden.map({True: "✅", False: ""}),
        "데드크로스": dead.map({True: "🔴", False: ""}),
    }).tail(10).iloc[::-1]
    st.dataframe(table, use_container_width=True)

# ════════════════════════════════════════════════════
# 탭 2 — 재무제표
# ════════════════════════════════════════════════════
with tab2:
    st.subheader(f"📊 {ticker} 재무제표 분석")

    def fmt(val, suffix="", multiply=1, decimal=2):
        if val is None:
            return "N/A"
        try:
            return f"{float(val) * multiply:,.{decimal}f}{suffix}"
        except:
            return "N/A"

    if market == "미국":
        with st.spinner("재무 데이터 불러오는 중..."):
            fin    = get_us_financials(ticker)
            income = get_us_income(ticker)

        st.markdown("#### 핵심 투자 지표")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("PER",  fmt(fin["PER"],  "배"))
        f2.metric("PBR",  fmt(fin["PBR"],  "배"))
        f3.metric("ROE",  fmt(fin["ROE"],  "%", 100))
        f4.metric("ROA",  fmt(fin["ROA"],  "%", 100))

        f5, f6, f7, f8 = st.columns(4)
        f5.metric("EPS",      fmt(fin["EPS"], "$"))
        f6.metric("부채비율", fmt(fin["부채비율"], "%"))
        f7.metric("배당수익률", fmt(fin["배당수익률"], "%", 100))
        f8.metric("시가총액", f"${fin['시가총액']/1e9:.1f}B" if fin["시가총액"] else "N/A")

        st.divider()
        st.markdown("#### 연간 손익계산서")
        if income is not None and not income.empty:
            key_rows     = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
            display_rows = [r for r in key_rows if r in income.index]
            if display_rows:
                inc_display = income.loc[display_rows].applymap(
                    lambda x: f"${x/1e9:.2f}B" if pd.notna(x) else "N/A"
                )
                inc_display.index = ["매출액", "매출총이익", "영업이익", "순이익"][:len(display_rows)]
                st.dataframe(inc_display, use_container_width=True)

        st.divider()
        st.markdown("#### 지표 해석 가이드")
        per_val = fin["PER"]
        pbr_val = fin["PBR"]
        roe_val = fin["ROE"]
        if per_val:
            st.info(f"**PER {per_val:.1f}배** — {'📉 저평가' if per_val < 10 else '✅ 적정' if per_val < 20 else '⚠️ 다소 고평가' if per_val < 30 else '🔴 고평가'}")
        if pbr_val:
            st.info(f"**PBR {pbr_val:.1f}배** — {'📉 저평가' if pbr_val < 1 else '✅ 적정' if pbr_val < 3 else '⚠️ 고평가'}")
        if roe_val:
            st.info(f"**ROE {roe_val*100:.1f}%** — {'✅ 우수' if roe_val*100 >= 15 else '🟡 보통' if roe_val*100 >= 8 else '⚠️ 낮음'}")

    else:
        with st.spinner("재무 데이터 불러오는 중..."):
            kr_info   = get_kr_financials(ticker)
            kr_income = get_kr_income(ticker)

        if kr_info:
            st.markdown("#### 핵심 투자 지표")
            per_val = kr_info.get("trailingPE")
            pbr_val = kr_info.get("priceToBook")
            roe_val = kr_info.get("returnOnEquity")
            roa_val = kr_info.get("returnOnAssets")
            eps_val = kr_info.get("trailingEps")
            div_val = kr_info.get("dividendYield")
            cap_val = kr_info.get("marketCap")
            deb_val = kr_info.get("debtToEquity")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("PER", fmt(per_val, "배"))
            k2.metric("PBR", fmt(pbr_val, "배"))
            k3.metric("ROE", fmt(roe_val, "%", 100))
            k4.metric("ROA", fmt(roa_val, "%", 100))

            k5, k6, k7, k8 = st.columns(4)
            k5.metric("EPS",      fmt(eps_val, "원", decimal=0))
            k6.metric("부채비율", fmt(deb_val, "%"))
            k7.metric("배당수익률", fmt(div_val, "%", 100))
            k8.metric("시가총액", f"{cap_val/1e12:.2f}조" if cap_val else "N/A")

            st.divider()
            st.markdown("#### 연간 손익계산서")
            if kr_income is not None and not kr_income.empty:
                key_rows     = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
                display_rows = [r for r in key_rows if r in kr_income.index]
                if display_rows:
                    inc_display = kr_income.loc[display_rows].applymap(
                        lambda x: f"{x/1e8:,.0f}억" if pd.notna(x) else "N/A"
                    )
                    inc_display.index = ["매출액", "매출총이익", "영업이익", "순이익"][:len(display_rows)]
                    st.dataframe(inc_display, use_container_width=True)
            else:
                st.info("손익계산서 데이터를 가져올 수 없습니다.")

            st.divider()
            st.markdown("#### 지표 해석 가이드")
            if per_val:
                st.info(f"**PER {per_val:.1f}배** — {'📉 저평가' if per_val < 10 else '✅ 적정' if per_val < 20 else '⚠️ 고평가'}")
            if pbr_val:
                st.info(f"**PBR {pbr_val:.1f}배** — {'📉 저평가' if pbr_val < 1 else '✅ 적정' if pbr_val < 3 else '⚠️ 고평가'}")
            if roe_val:
                st.info(f"**ROE {roe_val*100:.1f}%** — {'✅ 우수' if roe_val*100 >= 15 else '🟡 보통' if roe_val*100 >= 8 else '⚠️ 낮음'}")
        else:
            st.warning("재무 데이터를 가져오지 못했습니다. 종목코드를 확인해주세요.")

# ════════════════════════════════════════════════════
# 탭 3 — 종목 비교
# ════════════════════════════════════════════════════
with tab3:
    st.subheader("⚖️ 두 종목 나란히 비교")

    cmp_col1, cmp_col2 = st.columns(2)
    with cmp_col1:
        cmp_market1 = st.radio("시장 1", ["미국", "국내"], key="cm1")
        cmp_ticker1 = st.text_input(
            "종목 1",
            value="AAPL" if cmp_market1 == "미국" else "005930",
            key="ct1"
        ).upper() if cmp_market1 == "미국" else st.text_input("종목 1", value="005930", key="ct1k")

    with cmp_col2:
        cmp_market2 = st.radio("시장 2", ["미국", "국내"], key="cm2")
        cmp_ticker2 = st.text_input(
            "종목 2",
            value="MSFT" if cmp_market2 == "미국" else "000660",
            key="ct2"
        ).upper() if cmp_market2 == "미국" else st.text_input("종목 2", value="000660", key="ct2k")

    cmp_period = st.selectbox("비교 기간", ["3개월", "6개월", "1년", "2년"], key="cp")
    cmp_yf_period, cmp_days = period_map[cmp_period]

    if st.button("비교 시작 ▶"):
        with st.spinner("두 종목 데이터 불러오는 중..."):
            try:
                # 종목 1 데이터
                if cmp_market1 == "미국":
                    df1    = get_us_data(cmp_ticker1, cmp_yf_period)
                    close1 = df1["Close"][cmp_ticker1] if cmp_ticker1 in df1["Close"] else df1["Close"].iloc[:, 0]
                else:
                    df1    = get_kr_data(cmp_ticker1, cmp_days)
                    close1 = df1["Close"]

                # 종목 2 데이터
                if cmp_market2 == "미국":
                    df2    = get_us_data(cmp_ticker2, cmp_yf_period)
                    close2 = df2["Close"][cmp_ticker2] if cmp_ticker2 in df2["Close"] else df2["Close"].iloc[:, 0]
                else:
                    df2    = get_kr_data(cmp_ticker2, cmp_days)
                    close2 = df2["Close"]

                # 수익률 정규화 (시작점 100 기준)
                norm1 = (close1 / close1.iloc[0] * 100).round(2)
                norm2 = (close2 / close2.iloc[0] * 100).round(2)

                # ── 수익률 비교 카드 ──────────────────────
                ret1 = ((close1.iloc[-1] - close1.iloc[0]) / close1.iloc[0] * 100)
                ret2 = ((close2.iloc[-1] - close2.iloc[0]) / close2.iloc[0] * 100)

                st.divider()
                st.markdown("#### 기간 수익률 비교")
                r1, r2 = st.columns(2)
                r1.metric(cmp_ticker1, f"{ret1:+.2f}%")
                r2.metric(cmp_ticker2, f"{ret2:+.2f}%",
                          f"차이 {ret2 - ret1:+.2f}%p")

                # ── 정규화 수익률 차트 ────────────────────
                fig_cmp = go.Figure()
                fig_cmp.add_trace(go.Scatter(
                    x=close1.index, y=norm1,
                    name=cmp_ticker1,
                    line=dict(color="blue", width=2)
                ))
                fig_cmp.add_trace(go.Scatter(
                    x=close2.index, y=norm2,
                    name=cmp_ticker2,
                    line=dict(color="red", width=2)
                ))
                fig_cmp.add_hline(y=100, line_dash="dash", line_color="gray")
                fig_cmp.update_layout(
                    title=f"{cmp_ticker1} vs {cmp_ticker2} 수익률 비교 (시작점 = 100)",
                    yaxis_title="상대 수익률",
                    height=450,
                )
                st.plotly_chart(fig_cmp, use_container_width=True)

                # ── RSI 비교 차트 ─────────────────────────
                rsi1 = calc_rsi(close1)
                rsi2 = calc_rsi(close2)

                fig_rsi = make_subplots(rows=1, cols=2,
                    subplot_titles=[f"{cmp_ticker1} RSI", f"{cmp_ticker2} RSI"])
                fig_rsi.add_trace(go.Scatter(x=close1.index, y=rsi1, name=f"{cmp_ticker1} RSI",
                    line=dict(color="blue", width=1)), row=1, col=1)
                fig_rsi.add_trace(go.Scatter(x=close2.index, y=rsi2, name=f"{cmp_ticker2} RSI",
                    line=dict(color="red",  width=1)), row=1, col=2)
                for col in [1, 2]:
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="red",   row=1, col=col)
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", row=1, col=col)
                fig_rsi.update_layout(title="RSI 비교", height=300)
                st.plotly_chart(fig_rsi, use_container_width=True)

                # ── 재무 지표 비교 테이블 ─────────────────
                st.markdown("#### 재무 지표 비교")

                def get_fin_summary(t, mkt):
                    if mkt == "미국":
                        info = yf.Ticker(t).info
                    else:
                        info = yf.Ticker(f"{t}.KS").info
                        if not info or info.get("regularMarketPrice") is None:
                            info = yf.Ticker(f"{t}.KQ").info
                    return {
                        "PER":        info.get("trailingPE"),
                        "PBR":        info.get("priceToBook"),
                        "ROE":        info.get("returnOnEquity"),
                        "배당수익률": info.get("dividendYield"),
                        "시가총액":   info.get("marketCap"),
                    }

                fin1 = get_fin_summary(cmp_ticker1, cmp_market1)
                fin2 = get_fin_summary(cmp_ticker2, cmp_market2)

                def fmt_cmp(val, multiply=1, decimal=2):
                    if val is None:
                        return "N/A"
                    try:
                        return f"{float(val) * multiply:,.{decimal}f}"
                    except:
                        return "N/A"

                cmp_table = pd.DataFrame({
                    "지표":       ["PER", "PBR", "ROE (%)", "배당수익률 (%)", "시가총액"],
                    cmp_ticker1: [
                        fmt_cmp(fin1["PER"]),
                        fmt_cmp(fin1["PBR"]),
                        fmt_cmp(fin1["ROE"], 100),
                        fmt_cmp(fin1["배당수익률"], 100),
                        f"${fin1['시가총액']/1e9:.1f}B" if fin1["시가총액"] and cmp_market1 == "미국"
                        else f"{fin1['시가총액']/1e12:.2f}조" if fin1["시가총액"] else "N/A"
                    ],
                    cmp_ticker2: [
                        fmt_cmp(fin2["PER"]),
                        fmt_cmp(fin2["PBR"]),
                        fmt_cmp(fin2["ROE"], 100),
                        fmt_cmp(fin2["배당수익률"], 100),
                        f"${fin2['시가총액']/1e9:.1f}B" if fin2["시가총액"] and cmp_market2 == "미국"
                        else f"{fin2['시가총액']/1e12:.2f}조" if fin2["시가총액"] else "N/A"
                    ],
                }).set_index("지표")

                st.dataframe(cmp_table, use_container_width=True)

            except Exception as e:
                st.error(f"비교 데이터 로드 실패: {e}")

# ════════════════════════════════════════════════════
# 탭 4 — 관심 종목 즐겨찾기
# ════════════════════════════════════════════════════
with tab4:
    st.subheader("⭐ 관심 종목 즐겨찾기")

    # ── 즐겨찾기 저장/불러오기 (session_state 활용) ──
    if "favorites" not in st.session_state:
        st.session_state.favorites = [
            {"ticker": "AAPL",   "market": "미국"},
            {"ticker": "NVDA",   "market": "미국"},
            {"ticker": "005930", "market": "국내"},
            {"ticker": "000660", "market": "국내"},
        ]

    # ── 종목 추가 ────────────────────────────────────
    st.markdown("#### 종목 추가")
    add_col1, add_col2, add_col3 = st.columns([1, 2, 1])

    with add_col1:
        add_market = st.radio("시장", ["미국", "국내"], key="fav_market")
    with add_col2:
        add_ticker = st.text_input(
            "티커 / 종목코드",
            placeholder="AAPL 또는 005930",
            key="fav_ticker"
        )
    with add_col3:
        st.write("")
        st.write("")
        if st.button("➕ 추가"):
            add_ticker = add_ticker.upper() if add_market == "미국" else add_ticker
            already = any(
                f["ticker"] == add_ticker for f in st.session_state.favorites
            )
            if add_ticker and not already:
                st.session_state.favorites.append({
                    "ticker": add_ticker,
                    "market": add_market
                })
                st.success(f"{add_ticker} 추가 완료!")
                st.rerun()
            elif already:
                st.warning("이미 추가된 종목입니다.")

    st.divider()

    # ── 관심 종목 현황 ───────────────────────────────
    st.markdown("#### 관심 종목 현황")

    if not st.session_state.favorites:
        st.info("관심 종목을 추가해주세요.")
    else:
        with st.spinner("관심 종목 데이터 불러오는 중..."):
            fav_rows = []
            for fav in st.session_state.favorites:
                t   = fav["ticker"]
                mkt = fav["market"]
                try:
                    if mkt == "미국":
                        info = yf.Ticker(t).info
                        name      = info.get("shortName", t)
                        cur_price = info.get("regularMarketPrice")
                        prev      = info.get("regularMarketPreviousClose")
                        chg_pct   = ((cur_price - prev) / prev * 100) if cur_price and prev else None
                        currency  = "USD"
                    else:
                        info = yf.Ticker(f"{t}.KS").info
                        if not info or info.get("regularMarketPrice") is None:
                            info = yf.Ticker(f"{t}.KQ").info
                        name      = info.get("shortName", t)
                        cur_price = info.get("regularMarketPrice")
                        prev      = info.get("regularMarketPreviousClose")
                        chg_pct   = ((cur_price - prev) / prev * 100) if cur_price and prev else None
                        currency  = "KRW"

                    fav_rows.append({
                        "종목코드": t,
                        "종목명":   name,
                        "시장":     mkt,
                        "현재가":   f"{cur_price:,.0f} {currency}" if cur_price else "N/A",
                        "등락률":   f"{chg_pct:+.2f}%" if chg_pct else "N/A",
                        "상태":     "🔴 하락" if chg_pct and chg_pct < 0 else "🟢 상승" if chg_pct and chg_pct > 0 else "⚪ 보합",
                    })
                except:
                    fav_rows.append({
                        "종목코드": t,
                        "종목명":   t,
                        "시장":     mkt,
                        "현재가":   "N/A",
                        "등락률":   "N/A",
                        "상태":     "❓",
                    })

        fav_df = pd.DataFrame(fav_rows)
        st.dataframe(fav_df, use_container_width=True)

        # ── 종목 삭제 ─────────────────────────────────
        st.divider()
        st.markdown("#### 종목 삭제")

        del_ticker = st.selectbox(
            "삭제할 종목 선택",
            [f["ticker"] for f in st.session_state.favorites]
        )
        if st.button("🗑️ 삭제"):
            st.session_state.favorites = [
                f for f in st.session_state.favorites
                if f["ticker"] != del_ticker
            ]
            st.success(f"{del_ticker} 삭제 완료!")
            st.rerun()

        # ── 전체 새로고침 ─────────────────────────────
        st.divider()
        if st.button("🔄 전체 새로고침"):
            st.cache_data.clear()
            st.rerun()