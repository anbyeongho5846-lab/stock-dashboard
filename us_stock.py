import yfinance as yf
import pandas as pd

ticker = "AAPL"
start  = "2025-01-01"
end    = "2025-12-31"

df = yf.download(ticker, start=start, end=end)

print(f"=== {ticker} 주가 데이터 ===")
print(f"총 {len(df)}일치 데이터")
print(df.tail())

df.to_csv(f"{ticker}.csv")
print(f"\n{ticker}.csv 저장 완료!")