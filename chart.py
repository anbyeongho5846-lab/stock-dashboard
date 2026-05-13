import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 데이터 불러오기
df = pd.read_csv("AAPL.csv", header=[0,1], index_col=0)
df.index = pd.to_datetime(df.index)

open_  = df["Open"]["AAPL"]
high   = df["High"]["AAPL"]
low    = df["Low"]["AAPL"]
close  = df["Close"]["AAPL"]

# 지표 계산
ma5  = close.rolling(window=5).mean()
ma20 = close.rolling(window=20).mean()

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

rsi              = calc_rsi(close)
macd, signal, hist = calc_macd(close)

# 3개 패널 차트 생성 (캔들 / RSI / MACD)
fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    row_heights=[0.6, 0.2, 0.2],
    vertical_spacing=0.03
)

# 패널 1 — 캔들차트 + 이동평균선
fig.add_trace(go.Candlestick(
    x=df.index, open=open_, high=high, low=low, close=close, name="AAPL"
), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=ma5,  name="MA5",  line=dict(color="blue",   width=1)), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=ma20, name="MA20", line=dict(color="orange", width=1)), row=1, col=1)

# 패널 2 — RSI
fig.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI", line=dict(color="purple", width=1)), row=2, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="red",   row=2, col=1)  # 과매수 기준선
fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)  # 과매도 기준선

# 패널 3 — MACD
fig.add_trace(go.Scatter(x=df.index, y=macd,   name="MACD",   line=dict(color="blue",   width=1)), row=3, col=1)
fig.add_trace(go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color="orange", width=1)), row=3, col=1)
fig.add_trace(go.Bar(    x=df.index, y=hist,   name="Hist",   marker_color="gray"), row=3, col=1)

fig.update_layout(
    title="애플 (AAPL) 종합 차트",
    xaxis_rangeslider_visible=False,
    height=800,
)

fig.show()
