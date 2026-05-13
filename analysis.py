import pandas as pd

# 데이터 불러오기
df = pd.read_csv("AAPL.csv", header=[0,1], index_col=0)
df.index = pd.to_datetime(df.index)
close = df["Close"]["AAPL"]

# 이동평균선
ma5  = close.rolling(window=5).mean()
ma20 = close.rolling(window=20).mean()

# RSI
def calc_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    return (100 - (100 / (1 + rs))).round(2)

# MACD
def calc_macd(series):
    ema12  = series.ewm(span=12).mean()
    ema26  = series.ewm(span=26).mean()
    macd   = (ema12 - ema26).round(2)
    signal = macd.ewm(span=9).mean().round(2)
    hist   = (macd - signal).round(2)
    return macd, signal, hist

rsi              = calc_rsi(close)
macd, signal, hist = calc_macd(close)

# 결과 확인
result = pd.DataFrame({
    "종가"    : close,
    "MA5"     : ma5.round(2),
    "MA20"    : ma20.round(2),
    "RSI"     : rsi,
    "MACD"    : macd,
    "Signal"  : signal,
    "Hist"    : hist,
})

print("=== 전체 지표 ===")
print(result.tail(10))
print(f"\n현재 RSI  : {rsi.iloc[-1]}")
print(f"현재 MACD : {macd.iloc[-1]}")