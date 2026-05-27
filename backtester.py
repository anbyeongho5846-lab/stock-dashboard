"""
백테스터 — 이동평균 골든/데드크로스 전략
사용법:
  python backtester.py AAPL                      # 미국 주식
  python backtester.py 005930 --kr               # 국내 주식 (삼성전자)
  python backtester.py AAPL --short 5 --long 20  # MA 기간 직접 지정
  python backtester.py TSLA --days 365 --capital 10000000
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analyzer import add_indicators, fetch_kr, fetch_us

# Windows 터미널 UTF-8 출력
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── 백테스트 로직 ─────────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    short: int = 5,
    long: int = 20,
    capital: float = 10_000_000,
) -> tuple[pd.DataFrame, list[dict], dict]:
    df = df.copy()

    # MA 이미 없으면 계산
    if f"MA{short}" not in df.columns or f"MA{long}" not in df.columns:
        for w in (short, long):
            df[f"MA{w}"] = df["Close"].rolling(w).mean()

    ma_s = df[f"MA{short}"]
    ma_l = df[f"MA{long}"]

    # 크로스 신호: 1=골든크로스(매수), -1=데드크로스(매도)
    prev_above = ma_s.shift(1) > ma_l.shift(1)
    curr_above = ma_s > ma_l
    df["Signal"] = 0
    df.loc[curr_above & ~prev_above, "Signal"] = 1   # 골든크로스
    df.loc[~curr_above & prev_above, "Signal"] = -1  # 데드크로스

    # 포트폴리오 시뮬레이션
    cash = capital
    shares = 0.0
    position = False
    entry_price = 0.0
    entry_date = None
    trades: list[dict] = []
    port_values: list[float] = []

    for date, row in df.iterrows():
        # MA가 아직 계산 안 된 초반 구간은 건너뜀
        if pd.isna(ma_s[date]) or pd.isna(ma_l[date]):
            port_values.append(cash)
            continue

        if row["Signal"] == 1 and not position:
            shares = cash / row["Close"]
            entry_price = row["Close"]
            entry_date = date
            cash = 0.0
            position = True

        elif row["Signal"] == -1 and position:
            cash = shares * row["Close"]
            pnl = (row["Close"] - entry_price) / entry_price * 100
            trades.append({
                "entry_date": entry_date,
                "exit_date": date,
                "entry_price": entry_price,
                "exit_price": row["Close"],
                "pnl_pct": pnl,
                "won": pnl > 0,
                "open": False,
            })
            shares = 0.0
            position = False

        port_values.append(cash + shares * row["Close"])

    # 마지막에 포지션이 열려 있으면 미청산으로 기록
    if position:
        final_price = df["Close"].iloc[-1]
        cash = shares * final_price
        pnl = (final_price - entry_price) / entry_price * 100
        trades.append({
            "entry_date": entry_date,
            "exit_date": df.index[-1],
            "entry_price": entry_price,
            "exit_price": final_price,
            "pnl_pct": pnl,
            "won": pnl > 0,
            "open": True,
        })

    df["Portfolio"] = port_values
    df["BuyHold"] = capital * (df["Close"] / df["Close"].iloc[0])

    metrics = calc_metrics(df, trades, capital)
    return df, trades, metrics


def calc_metrics(df: pd.DataFrame, trades: list[dict], initial: float) -> dict:
    final    = df["Portfolio"].iloc[-1]
    bh_final = df["BuyHold"].iloc[-1]

    roll_max = df["Portfolio"].cummax()
    mdd = ((df["Portfolio"] - roll_max) / roll_max * 100).min()

    # 거래가 없으면 샤프 의미 없음
    if not trades:
        sharpe = 0.0
    else:
        daily_ret = df["Portfolio"].pct_change().dropna()
        excess = daily_ret - 0.03 / 252
        std = excess.std()
        sharpe = (excess.mean() / std * (252 ** 0.5)) if std > 1e-10 else 0.0

    won_trades  = [t for t in trades if t["won"]]
    lost_trades = [t for t in trades if not t["won"]]

    return {
        "initial":      initial,
        "final":        final,
        "total_return": (final - initial) / initial * 100,
        "bh_return":    (bh_final - initial) / initial * 100,
        "n_trades":     len(trades),
        "win_rate":     len(won_trades) / len(trades) * 100 if trades else 0.0,
        "avg_win":      sum(t["pnl_pct"] for t in won_trades)  / len(won_trades)  if won_trades  else 0.0,
        "avg_loss":     sum(t["pnl_pct"] for t in lost_trades) / len(lost_trades) if lost_trades else 0.0,
        "mdd":          mdd,
        "sharpe":       sharpe,
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_report(metrics: dict, trades: list[dict], ticker: str) -> None:
    m = metrics
    sign = "▲" if m["total_return"] >= 0 else "▼"
    bh_sign = "▲" if m["bh_return"] >= 0 else "▼"

    print(f"\n{'='*48}")
    print(f"  백테스트 결과 — {ticker}")
    print(f"{'='*48}")
    print(f"  초기 자본    : {m['initial']:>15,.0f}원")
    print(f"  최종 자산    : {m['final']:>15,.0f}원  {sign} {abs(m['total_return']):.2f}%")
    print(f"  Buy & Hold  : {sign if False else bh_sign} {abs(m['bh_return']):.2f}%  (비교 기준)")
    print(f"  초과 수익    : {m['total_return'] - m['bh_return']:+.2f}%")
    print(f"  최대낙폭(MDD): {m['mdd']:.2f}%")
    print(f"  샤프 지수    : {m['sharpe']:.2f}")
    print(f"  총 거래 수   : {m['n_trades']}회")
    print(f"  승률         : {m['win_rate']:.1f}%")
    print(f"  평균 수익    : {m['avg_win']:+.2f}%  |  평균 손실: {m['avg_loss']:+.2f}%")
    print(f"{'='*48}")

    if trades:
        print(f"\n  [거래 내역]")
        print(f"  {'진입일':<12} {'청산일':<12} {'진입가':>10} {'청산가':>10} {'수익률':>8}  상태")
        print(f"  {'-'*60}")
        for t in trades:
            flag = "(미청산)" if t.get("open") else ""
            result = "WIN" if t["won"] else "LOSS"
            print(
                f"  {str(t['entry_date'])[:10]:<12}"
                f" {str(t['exit_date'])[:10]:<12}"
                f" {t['entry_price']:>10,.0f}"
                f" {t['exit_price']:>10,.0f}"
                f" {t['pnl_pct']:>+7.2f}%  {result} {flag}"
            )
    print()


def plot_backtest(df: pd.DataFrame, trades: list[dict], title: str, short: int, long: int, show: bool = True) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            f"{title} — 매수/매도 신호",
            "포트폴리오 vs Buy & Hold",
        ),
        row_heights=[0.55, 0.45],
    )

    # ① 가격 + 이동평균
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#e63946",
        decreasing_line_color="#457b9d",
        name="주가",
    ), row=1, col=1)

    for ma, color in [(f"MA{short}", "#f4a261"), (f"MA{long}", "#457b9d")]:
        if ma in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ma], name=ma,
                line=dict(color=color, width=1.5),
            ), row=1, col=1)

    # ② 매수/매도 마커
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]

    fig.add_trace(go.Scatter(
        x=buys.index, y=buys["Low"] * 0.985,
        mode="markers+text",
        marker=dict(symbol="triangle-up", size=14, color="#2dc653"),
        text=["BUY"] * len(buys),
        textposition="bottom center",
        textfont=dict(size=9, color="#2dc653"),
        name="골든크로스 (매수)",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=sells.index, y=sells["High"] * 1.015,
        mode="markers+text",
        marker=dict(symbol="triangle-down", size=14, color="#e63946"),
        text=["SELL"] * len(sells),
        textposition="top center",
        textfont=dict(size=9, color="#e63946"),
        name="데드크로스 (매도)",
    ), row=1, col=1)

    # ③ 포트폴리오 곡선
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Portfolio"],
        line=dict(color="#f4a261", width=2),
        fill="tozeroy", fillcolor="rgba(244,162,97,0.1)",
        name="전략 포트폴리오",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BuyHold"],
        line=dict(color="#457b9d", width=2, dash="dot"),
        name="Buy & Hold",
    ), row=2, col=1)

    # 거래 구간 음영 (진입~청산)
    for t in trades:
        color = "rgba(45,198,83,0.06)" if t["won"] else "rgba(230,57,70,0.06)"
        fig.add_vrect(
            x0=t["entry_date"], x1=t["exit_date"],
            fillcolor=color, line_width=0,
            row=2, col=1,
        )

    fig.update_layout(
        height=850,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(t=80, b=40),
        title=dict(text=title, font=dict(size=18)),
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    if show:
        fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="이동평균 크로스 백테스터")
    parser.add_argument("ticker", help="종목코드  예) AAPL  또는  005930")
    parser.add_argument("--kr", action="store_true", help="국내 주식 (KRX)")
    parser.add_argument("--days", type=int, default=365, help="조회 기간 (일, 기본 365)")
    parser.add_argument("--short", type=int, default=5, help="단기 MA 기간 (기본 5)")
    parser.add_argument("--long", type=int, default=20, help="장기 MA 기간 (기본 20)")
    parser.add_argument("--capital", type=float, default=10_000_000, help="초기 자본 (기본 1000만)")
    args = parser.parse_args()

    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    market = "KRX" if args.kr else "US"

    print(f"[{market}] {args.ticker}  {start} ~ {end}  MA{args.short}/MA{args.long} 전략")

    try:
        df = fetch_kr(args.ticker, start, end) if args.kr else fetch_us(args.ticker, start, end)
    except Exception as e:
        print(f"[오류] 데이터 수집 실패: {e}")
        return

    if df.empty:
        print("[오류] 데이터 없음. 종목코드를 확인하세요.")
        return

    df = add_indicators(df)
    df, trades, metrics = run_backtest(df, args.short, args.long, args.capital)

    title = f"{args.ticker} ({market})  MA{args.short}/MA{args.long} 골든·데드크로스"
    print_report(metrics, trades, args.ticker)
    plot_backtest(df, trades, title, args.short, args.long)


if __name__ == "__main__":
    main()
