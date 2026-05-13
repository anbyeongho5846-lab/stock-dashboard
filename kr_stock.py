from pykrx import stock
import pandas as pd

ticker = "005930"
start  = "20250101"
end    = "20251231"

df = stock.get_market_ohlcv(start, end, ticker)

print("=== 삼성전자 주가 데이터 ===")
print(f"총 {len(df)}일치 데이터")
print(df.tail())

df.to_csv(f"{ticker}.csv", encoding="utf-8-sig")
print(f"\n{ticker}.csv 저장 완료!")