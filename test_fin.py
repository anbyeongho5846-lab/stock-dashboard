from pykrx import stock
from datetime import datetime, timedelta

ticker = "005930"

# 최근 5일 시도
for i in range(1, 6):
    day = (datetime.today() - timedelta(days=i)).strftime("%Y%m%d")
    df  = stock.get_market_fundamental(day, day, ticker)
    print(f"{day} 시도 결과:")
    print(df)
    print()
    if not df.empty:
        print("✅ 데이터 수신 성공!")
        break