import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta

# ── 페이지 설정 ──────────────────────────────────────
st.set_page_config(
    page_title="백테스팅",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 백테스팅 — 전략 수익률 검증")
st.caption("과거 데이터로 매매 전략의 수익률을 시뮬레이션합니다.")

# ── 사이드바 ─────────────────────────────────────────
st.sidebar.header("백테스팅 설정")

market = st.sidebar.radio("시장 선택", ["미국", "국내"])

if market == "미국":
    ticker = st.sidebar.text_input("티커 입력", value="AAPL").upper()
else:
    ticker = st.sidebar.text_input("종목코드 입력", value="005930")

period = st.sidebar.selectbox("기간 선택", ["6개월", "1년", "2년", "3년"])

strategy = st.sidebar.selectbox("전략 선택", [
    "골든크로스 (MA5/MA20)",
    "골든크로스 (MA20/MA60)",
    "RSI 과매도 매수",
    "MACD 시그널 교차",
])

initial_capital = st.sidebar.number_input(
    "초기 자본금 (원/달러)", value=1000000, step=100000
)

# ── 기간 변환 ────────────────────────────────────────
period_map = {
    "6개월": ("6mo", 180),
    "1년":   ("1y",  365),
    "2년":   ("2y",  730),
    "3년":   ("3y",  1095),
}
yf_period, days = period_map[period]

# ── 데이터 수집 ──────────────────────────────────────
@st.cache_data(ttl=3600)
def get_us_data(ticker, period):
    return yf.download(ticker, period=period, progress=False)

@st.cache_data(ttl=3600)
def get_kr_data(ticker, days):
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    df    = stock.get_market_ohlcv(start, end, ticker)
    df.columns = ["Open", "High", "Low", "Close", "Volume", "Change"]
    return df

with st.spinner("데이터 불러오는 중..."):
    try:
        if market == "미국":
            df    = get_us_data(ticker, yf_period)
            close = df["Close"][ticker] if ticker in df["Close"] else df["Close"].iloc[:, 0]
            open_ = df["Open"][ticker]  if ticker in df["Open"]  else df["Open"].iloc[:, 0]
        else:
            df    = get_kr_data(ticker, days)
            close = df["Close"]
            open_ = df["Open"]

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
    return macd, signal

rsi          = calc_rsi(close)
macd, sig    = calc_macd(close)

# ── 전략별 매매 신호 생성 ────────────────────────────
def generate_signals(strategy):
    signals = pd.Series(0, index=close.index)

    if strategy == "골든크로스 (MA5/MA20)":
        # MA5가 MA20 위로 올라갈 때 매수, 아래로 내려갈 때 매도
        cross_up   = (ma5 > ma20) & (ma5.shift(1) <= ma20.shift(1))
        cross_down = (ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))
        signals[cross_up]   =  1   # 매수
        signals[cross_down] = -1   # 매도

    elif strategy == "골든크로스 (MA20/MA60)":
        cross_up   = (ma20 > ma60) & (ma20.shift(1) <= ma60.shift(1))
        cross_down = (ma20 < ma60) & (ma20.shift(1) >= ma60.shift(1))
        signals[cross_up]   =  1
        signals[cross_down] = -1

    elif strategy == "RSI 과매도 매수":
        # RSI 30 아래로 내려갈 때 매수, 70 위로 올라갈 때 매도
        signals[rsi < 30] =  1
        signals[rsi > 70] = -1

    elif strategy == "MACD 시그널 교차":
        cross_up   = (macd > sig) & (macd.shift(1) <= sig.shift(1))
        cross_down = (macd < sig) & (macd.shift(1) >= sig.shift(1))
        signals[cross_up]   =  1
        signals[cross_down] = -1

    return signals

signals = generate_signals(strategy)

# ── 백테스팅 엔진 ────────────────────────────────────
def run_backtest(close, signals, initial_capital):
    capital    = initial_capital  # 보유 현금
    position   = 0                # 보유 주식 수
    trades     = []               # 매매 기록
    portfolio  = []               # 날짜별 자산 가치

    for date, price in close.items():
        signal = signals.loc[date]

        # 매수 신호 + 현금 있을 때
        if signal == 1 and capital > 0:
            shares   = capital // price   # 살 수 있는 최대 주식 수
            cost     = shares * price
            capital -= cost
            position += shares
            trades.append({
                "날짜": date.strftime("%Y-%m-%d"),
                "구분": "매수",
                "가격": round(price, 2),
                "수량": int(shares),
                "금액": round(cost, 0),
            })

        # 매도 신호 + 주식 있을 때
        elif signal == -1 and position > 0:
            revenue   = position * price
            capital  += revenue
            trades.append({
                "날짜": date.strftime("%Y-%m-%d"),
                "구분": "매도",
                "가격": round(price, 2),
                "수량": int(position),
                "금액": round(revenue, 0),
            })
            position = 0

        # 날짜별 총 자산 (현금 + 주식 평가액)
        total = capital + position * price
        portfolio.append({"날짜": date, "자산": total})

    # 마지막에 주식 보유 중이면 현재가로 청산
    if position > 0:
        final_price  = close.iloc[-1]
        capital     += position * final_price

    return trades, portfolio, capital

trades, portfolio, final_capital = run_backtest(close, signals, initial_capital)

# ── 성과 계산 ────────────────────────────────────────
portfolio_df  = pd.DataFrame(portfolio).set_index("날짜")
total_return  = (final_capital - initial_capital) / initial_capital * 100
buy_and_hold  = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100
trade_count   = len([t for t in trades if t["구분"] == "매수"])

win_trades = 0
for i in range(0, len(trades) - 1, 2):
    if i + 1 < len(trades):
        if trades[i]["구분"] == "매수" and trades[i+1]["구분"] == "매도":
            if trades[i+1]["가격"] > trades[i]["가격"]:
                win_trades += 1

win_rate = (win_trades / trade_count * 100) if trade_count > 0 else 0

# ── 요약 카드 ────────────────────────────────────────
st.subheader("📊 백테스팅 결과")

col1, col2, col3, col4 = st.columns(4)
col1.metric("전략 수익률",   f"{total_return:+.2f}%")
col2.metric("단순 보유 수익률", f"{buy_and_hold:+.2f}%",
            f"전략 대비 {total_return - buy_and_hold:+.2f}%")
col3.metric("총 매매 횟수",  f"{trade_count}회")
col4.metric("승률",          f"{win_rate:.1f}%")

col5, col6, col7, col8 = st.columns(4)
col5.metric("초기 자본금",   f"{initial_capital:,.0f}")
col6.metric("최종 자산",     f"{final_capital:,.0f}")
col7.metric("손익",          f"{final_capital - initial_capital:+,.0f}")
col8.metric("기간",          period)

st.divider()

# ── 자산 변화 차트 ───────────────────────────────────
fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.7, 0.3],
    vertical_spacing=0.05
)

# 주가 + 매수/매도 신호 표시
fig.add_trace(go.Scatter(
    x=close.index, y=close,
    name="종가", line=dict(color="gray", width=1)
), row=1, col=1)

buy_dates  = [t["날짜"] for t in trades if t["구분"] == "매수"]
buy_prices = [t["가격"] for t in trades if t["구분"] == "매수"]
sell_dates  = [t["날짜"] for t in trades if t["구분"] == "매도"]
sell_prices = [t["가격"] for t in trades if t["구분"] == "매도"]

fig.add_trace(go.Scatter(
    x=buy_dates, y=buy_prices,
    mode="markers", name="매수",
    marker=dict(color="red", size=10, symbol="triangle-up")
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=sell_dates, y=sell_prices,
    mode="markers", name="매도",
    marker=dict(color="blue", size=10, symbol="triangle-down")
), row=1, col=1)

# 자산 변화
fig.add_trace(go.Scatter(
    x=portfolio_df.index, y=portfolio_df["자산"],
    name="자산 변화", line=dict(color="green", width=1.5),
    fill="tozeroy", fillcolor="rgba(38,166,154,0.1)"
), row=2, col=1)

fig.update_layout(
    title=f"{ticker} — {strategy} 백테스팅 결과",
    height=700,
    xaxis_rangeslider_visible=False,
)

st.plotly_chart(fig, use_container_width=True)

# ── 매매 기록 테이블 ─────────────────────────────────
st.subheader("📋 매매 기록")

if trades:
    trades_df = pd.DataFrame(trades)
    st.dataframe(trades_df, use_container_width=True)
else:
    st.info("해당 기간 동안 매매 신호가 발생하지 않았습니다. 기간을 늘려보세요.")
