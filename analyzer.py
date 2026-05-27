"""
주식 분석 스크립트 — 국내(KRX) / 미국 종목 지원
사용법:
  python analyzer.py AAPL            # 미국 주식 (기본값)
  python analyzer.py 005930 --kr     # 국내 주식 (삼성전자)
  python analyzer.py TSLA --days 90  # 기간 지정 (기본 180일)
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.momentum import RSIIndicator
from ta.trend import MACD


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_us(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def fetch_kr(ticker: str, start: str, end: str) -> pd.DataFrame:
    from pykrx import stock as krx
    s = start.replace("-", "")
    e = end.replace("-", "")
    df = krx.get_market_ohlcv_by_date(s, e, ticker)
    df = df.rename(columns={"시가": "Open", "고가": "High", "저가": "Low",
                             "종가": "Close", "거래량": "Volume"})
    df.index = pd.to_datetime(df.index)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


# ── 지표 계산 ─────────────────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 이동평균선
    for window in (5, 20, 60):
        df[f"MA{window}"] = df["Close"].rolling(window).mean()

    # RSI (14일)
    df["RSI"] = RSIIndicator(df["Close"], window=14).rsi()

    # MACD
    macd = MACD(df["Close"])
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()
    df["MACD_Hist"] = macd.macd_diff()

    return df


# ── 차트 ─────────────────────────────────────────────────────────────────────

MA_COLORS = {"MA5": "#f4a261", "MA20": "#457b9d", "MA60": "#9b2226"}


def plot(df: pd.DataFrame, title: str, show: bool = True) -> go.Figure:
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        subplot_titles=(f"{title} — 주가 & 이동평균", "거래량", "RSI (14)", "MACD"),
        row_heights=[0.50, 0.15, 0.15, 0.20],
    )

    # ① 캔들스틱
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#e63946",   # 한국식: 빨강=상승
        decreasing_line_color="#457b9d",   # 파랑=하락
        name="주가",
    ), row=1, col=1)

    # ② 이동평균선
    for ma, color in MA_COLORS.items():
        if ma in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ma], name=ma,
                line=dict(color=color, width=1.2), opacity=0.85,
            ), row=1, col=1)

    # ③ 거래량 (상승일=빨강, 하락일=파랑)
    vol_colors = [
        "#e63946" if c >= o else "#457b9d"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors, name="거래량",
    ), row=2, col=1)

    # ④ RSI
    fig.add_trace(go.Scatter(
        x=df.index, y=df["RSI"],
        line=dict(color="#9b5de5", width=1.5), name="RSI",
    ), row=3, col=1)
    for level, color in ((70, "rgba(230,57,70,0.4)"), (30, "rgba(69,123,157,0.4)")):
        fig.add_hline(y=level, line_dash="dash", line_color=color, row=3, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(255,255,255,0.03)",
                  line_width=0, row=3, col=1)

    # ⑤ MACD
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD"],
        line=dict(color="#457b9d", width=1.5), name="MACD",
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD_Signal"],
        line=dict(color="#e63946", width=1.2, dash="dot"), name="Signal",
    ), row=4, col=1)
    hist_colors = ["#e63946" if v >= 0 else "#457b9d" for v in df["MACD_Hist"]]
    fig.add_trace(go.Bar(
        x=df.index, y=df["MACD_Hist"],
        marker_color=hist_colors, name="Histogram", opacity=0.7,
    ), row=4, col=1)

    fig.update_layout(
        height=900,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.01, x=0),
        margin=dict(t=80, b=40),
        title=dict(text=title, font=dict(size=18)),
    )
    # 주말/공휴일 제거 (gaps 숨기기)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    if show:
        fig.show()
        print(f"\n[완료] 브라우저에서 차트를 확인하세요.")
    return fig


# ── 요약 출력 ─────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame, ticker: str) -> None:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    change = (last["Close"] - prev["Close"]) / prev["Close"] * 100
    sign = "▲" if change >= 0 else "▼"

    print(f"\n{'='*40}")
    print(f"  {ticker}")
    print(f"  종가:  {last['Close']:,.0f}  {sign} {abs(change):.2f}%")
    print(f"  고가:  {last['High']:,.0f}")
    print(f"  저가:  {last['Low']:,.0f}")
    print(f"  거래량: {last['Volume']:,.0f}")
    print(f"  RSI:  {last['RSI']:.1f}  {'(과매수)' if last['RSI'] > 70 else '(과매도)' if last['RSI'] < 30 else ''}")
    print(f"  MA5:  {last['MA5']:,.0f}  |  MA20: {last['MA20']:,.0f}  |  MA60: {last['MA60']:,.0f}")
    print(f"{'='*40}\n")


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="주식 분석 도구")
    parser.add_argument("ticker", help="종목코드  예) AAPL  또는  005930")
    parser.add_argument("--kr", action="store_true", help="국내 주식 (KRX)")
    parser.add_argument("--days", type=int, default=180, help="조회 기간 (일, 기본 180)")
    args = parser.parse_args()

    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    market = "KRX" if args.kr else "US"

    print(f"[{market}] {args.ticker}  {start} ~ {end} 데이터 수집 중...")

    try:
        df = fetch_kr(args.ticker, start, end) if args.kr else fetch_us(args.ticker, start, end)
    except Exception as e:
        print(f"[오류] 데이터 수집 실패: {e}")
        return

    if df.empty:
        print("[오류] 데이터가 없습니다. 종목코드를 확인하세요.")
        return

    df = add_indicators(df)
    title = f"{args.ticker}  ({market})"

    print_summary(df, args.ticker)
    plot(df, title)


if __name__ == "__main__":
    main()
