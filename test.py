import yfinance as yf

ticker = yf.Ticker("005930.KS")
df = ticker.history(period="5d")

print("=== 삼성전자 최근 5일 주가 ===")
print(df[["Open", "High", "Low", "Close", "Volume"]])
