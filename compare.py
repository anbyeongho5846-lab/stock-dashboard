"""
전략 비교 — MA 크로스 vs RSI vs MACD
사용법:
  python compare.py AAPL
  python compare.py 005930 --kr --days 730
  python compare.py TSLA --short 10 --long 60 --rsi-buy 35 --rsi-sell 65
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analyzer import add_indicators, fetch_kr, fetch_us
from backtester import calc_metrics, run_backtest

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

COLORS = {
    "MA":      "#f4a261",
    "RSI":     "#2dc653",
    "MACD":    "#9b5de5",
    "BuyHold": "#457b9d",
}


# ── 전략별 백테스트 ──────────────────────────────────────────────────────────

def backtest_rsi(
    df: pd.DataFrame,
    buy_level: int = 30,
    sell_level: int = 70,
    capital: float = 10_000_000,
) -> tuple[pd.DataFrame, list[dict], dict]:
    """RSI < buy_level 이면 매수, RSI > sell_level 이면 매도."""
    from ta.momentum import RSIIndicator
    df = df.copy()
    df["RSI"] = RSIIndicator(df["Close"], window=14).rsi()

    cash, shares = capital, 0.0
    position = False
    entry_price, entry_date = 0.0, None
    trades: list[dict] = []
    port_values: list[float] = []
    signals: dict = {}

    for date, row in df.iterrows():
        if pd.isna(row["RSI"]):
            port_values.append(cash)
            continue

        if not position and row["RSI"] < buy_level:
            shares = cash / row["Close"]
            entry_price, entry_date = row["Close"], date
            cash = 0.0
            position = True
            signals[date] = 1

        elif position and row["RSI"] > sell_level:
            cash = shares * row["Close"]
            pnl = (row["Close"] - entry_price) / entry_price * 100
            trades.append({
                "entry_date": entry_date, "exit_date": date,
                "entry_price": entry_price, "exit_price": row["Close"],
                "pnl_pct": pnl, "won": pnl > 0, "open": False,
            })
            shares, position = 0.0, False
            signals[date] = -1

        port_values.append(cash + shares * row["Close"])

    if position:
        fp = df["Close"].iloc[-1]
        pnl = (fp - entry_price) / entry_price * 100
        trades.append({
            "entry_date": entry_date, "exit_date": df.index[-1],
            "entry_price": entry_price, "exit_price": fp,
            "pnl_pct": pnl, "won": pnl > 0, "open": True,
        })

    df["Signal"]    = pd.Series(signals, index=df.index).fillna(0).astype(int)
    df["Portfolio"] = port_values
    df["BuyHold"]   = capital * (df["Close"] / df["Close"].iloc[0])
    return df, trades, calc_metrics(df, trades, capital)


def backtest_macd(
    df: pd.DataFrame,
    capital: float = 10_000_000,
) -> tuple[pd.DataFrame, list[dict], dict]:
    """MACD 히스토그램이 음→양 전환 시 매수, 양→음 전환 시 매도."""
    from ta.trend import MACD as MACDIndicator
    df = df.copy()
    _macd = MACDIndicator(df["Close"])
    df["MACD"]        = _macd.macd()
    df["MACD_Signal"] = _macd.macd_signal()
    df["MACD_Diff"]   = _macd.macd_diff()

    cash, shares = capital, 0.0
    position = False
    entry_price, entry_date = 0.0, None
    trades: list[dict] = []
    port_values: list[float] = []
    signals: dict = {}
    prev_hist = None

    for date, row in df.iterrows():
        if pd.isna(row["MACD_Diff"]):
            port_values.append(cash)
            prev_hist = None
            continue

        curr_hist = row["MACD_Diff"]

        if prev_hist is not None:
            if not position and prev_hist < 0 and curr_hist >= 0:
                shares = cash / row["Close"]
                entry_price, entry_date = row["Close"], date
                cash = 0.0
                position = True
                signals[date] = 1

            elif position and prev_hist > 0 and curr_hist <= 0:
                cash = shares * row["Close"]
                pnl = (row["Close"] - entry_price) / entry_price * 100
                trades.append({
                    "entry_date": entry_date, "exit_date": date,
                    "entry_price": entry_price, "exit_price": row["Close"],
                    "pnl_pct": pnl, "won": pnl > 0, "open": False,
                })
                shares, position = 0.0, False
                signals[date] = -1

        prev_hist = curr_hist
        port_values.append(cash + shares * row["Close"])

    if position:
        fp = df["Close"].iloc[-1]
        pnl = (fp - entry_price) / entry_price * 100
        trades.append({
            "entry_date": entry_date, "exit_date": df.index[-1],
            "entry_price": entry_price, "exit_price": fp,
            "pnl_pct": pnl, "won": pnl > 0, "open": True,
        })

    df["Signal"]    = pd.Series(signals, index=df.index).fillna(0).astype(int)
    df["Portfolio"] = port_values
    df["BuyHold"]   = capital * (df["Close"] / df["Close"].iloc[0])
    return df, trades, calc_metrics(df, trades, capital)


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_comparison(strategies: dict[str, dict], ticker: str) -> None:
    bh = next(iter(strategies.values()))["metrics"]["bh_return"]

    print(f"\n{'='*70}")
    print(f"  전략 비교 결과 — {ticker}  (Buy&Hold: {bh:+.1f}%)")
    print(f"{'='*70}")
    header = f"  {'전략':<10} {'수익률':>8} {'B&H대비':>8} {'승률':>6} {'샤프':>7} {'MDD':>8} {'거래수':>6}"
    print(header)
    print(f"  {'-'*66}")

    for name, data in strategies.items():
        m = data["metrics"]
        excess = m["total_return"] - m["bh_return"]
        mark = "★" if excess > 0 else " "
        print(
            f"  {mark}{name:<9} {m['total_return']:>+7.1f}%"
            f" {excess:>+7.1f}%"
            f" {m['win_rate']:>5.0f}%"
            f" {m['sharpe']:>7.2f}"
            f" {m['mdd']:>7.1f}%"
            f" {m['n_trades']:>5}회"
        )

    best = max(strategies.items(), key=lambda x: x[1]["metrics"]["total_return"])
    print(f"\n  최고 수익 전략: {best[0]}  ({best[1]['metrics']['total_return']:+.1f}%)")
    print(f"{'='*70}\n")


def plot_comparison(strategies: dict[str, dict], ticker: str, show: bool = True) -> go.Figure:
    """포트폴리오 비교 곡선 + 지표별 매수/매도 신호 + 지표 패널."""

    # 각 전략 df — 자기 지표를 직접 계산했으므로 각 패널에서 해당 df 사용
    ma_df   = strategies["MA"]["df"]
    rsi_df  = strategies["RSI"]["df"]
    macd_df = strategies["MACD"]["df"]

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(
            f"{ticker} — 포트폴리오 비교",
            "주가 + 매수/매도 신호",
            "RSI (14)",
            "MACD",
        ),
        row_heights=[0.30, 0.30, 0.18, 0.22],
    )

    # ① 포트폴리오 곡선
    fig.add_trace(go.Scatter(
        x=ma_df.index, y=ma_df["BuyHold"],
        name="Buy & Hold",
        line=dict(color=COLORS["BuyHold"], width=2, dash="dot"),
    ), row=1, col=1)

    for name, data in strategies.items():
        fig.add_trace(go.Scatter(
            x=data["df"].index,
            y=data["df"]["Portfolio"],
            name=name,
            line=dict(color=COLORS[name], width=2),
        ), row=1, col=1)

    # ② 주가 캔들
    fig.add_trace(go.Candlestick(
        x=ma_df.index,
        open=ma_df["Open"], high=ma_df["High"],
        low=ma_df["Low"],  close=ma_df["Close"],
        increasing_line_color="#e63946",
        decreasing_line_color="#457b9d",
        name="주가", showlegend=False,
    ), row=2, col=1)

    # MA 이동평균선
    for ma, color in [("MA5", "#f4a261"), ("MA20", "#aaa")]:
        if ma in ma_df.columns:
            fig.add_trace(go.Scatter(
                x=ma_df.index, y=ma_df[ma], name=ma,
                line=dict(color=color, width=1, dash="dot"),
                showlegend=False,
            ), row=2, col=1)

    # 전략별 매수/매도 마커 (▲ / ▼)
    MARKER_OFFSETS = {"MA": 0.97, "RSI": 0.95, "MACD": 0.93}
    for name, data in strategies.items():
        df_s = data["df"]
        buys  = df_s[df_s["Signal"] == 1]
        sells = df_s[df_s["Signal"] == -1]
        offset = MARKER_OFFSETS.get(name, 0.97)

        fig.add_trace(go.Scatter(
            x=buys.index,
            y=buys["Low"] * offset,
            mode="markers",
            marker=dict(symbol="triangle-up", size=10, color=COLORS[name]),
            name=f"{name} 매수", showlegend=False,
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=sells.index,
            y=sells["High"] * (2 - offset),
            mode="markers",
            marker=dict(symbol="triangle-down", size=10, color=COLORS[name]),
            name=f"{name} 매도", showlegend=False,
        ), row=2, col=1)

    # ③ RSI (rsi_df 사용 — 내부에서 직접 계산)
    fig.add_trace(go.Scatter(
        x=rsi_df.index, y=rsi_df["RSI"],
        line=dict(color=COLORS["RSI"], width=1.5), name="RSI", showlegend=False,
    ), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(230,57,70,0.5)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(45,198,83,0.5)",  row=3, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(255,255,255,0.02)", line_width=0, row=3, col=1)

    # ④ MACD (macd_df 사용 — 내부에서 직접 계산)
    fig.add_trace(go.Scatter(
        x=macd_df.index, y=macd_df["MACD"],
        line=dict(color=COLORS["MACD"], width=1.5), name="MACD", showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=macd_df.index, y=macd_df["MACD_Signal"],
        line=dict(color="#e63946", width=1, dash="dot"), name="Signal", showlegend=False,
    ), row=4, col=1)
    hist_colors = ["#e63946" if v >= 0 else "#457b9d" for v in macd_df["MACD_Diff"]]
    fig.add_trace(go.Bar(
        x=macd_df.index, y=macd_df["MACD_Diff"],
        marker_color=hist_colors, opacity=0.7, name="Histogram", showlegend=False,
    ), row=4, col=1)

    fig.update_layout(
        height=950,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(t=80, b=40),
        title=dict(text=ticker, font=dict(size=18)),
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    if show:
        fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="전략 비교: MA vs RSI vs MACD")
    parser.add_argument("ticker")
    parser.add_argument("--kr",       action="store_true")
    parser.add_argument("--days",     type=int,   default=365)
    parser.add_argument("--short",    type=int,   default=5,  help="MA 단기 (기본 5)")
    parser.add_argument("--long",     type=int,   default=20, help="MA 장기 (기본 20)")
    parser.add_argument("--rsi-buy",  type=int,   default=30, help="RSI 매수 기준 (기본 30)")
    parser.add_argument("--rsi-sell", type=int,   default=70, help="RSI 매도 기준 (기본 70)")
    parser.add_argument("--capital",  type=float, default=10_000_000)
    args = parser.parse_args()

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    market = "KRX" if args.kr else "US"

    print(f"[{market}] {args.ticker}  {start} ~ {end}  세 전략 비교 중...")

    try:
        df = fetch_kr(args.ticker, start, end) if args.kr else fetch_us(args.ticker, start, end)
    except Exception as e:
        print(f"[오류] {e}"); return

    if df.empty:
        print("[오류] 데이터 없음. 종목코드를 확인하세요."); return

    df = add_indicators(df)

    # 각 전략 실행
    df_ma,   _, m_ma   = run_backtest(df.copy(), args.short, args.long, args.capital)
    df_rsi,  _, m_rsi  = backtest_rsi(df.copy(), args.rsi_buy, args.rsi_sell, args.capital)
    df_macd, _, m_macd = backtest_macd(df.copy(), args.capital)

    strategies = {
        f"MA{args.short}/{args.long}": {"df": df_ma,   "metrics": m_ma},
        f"RSI({args.rsi_buy}/{args.rsi_sell})": {"df": df_rsi,  "metrics": m_rsi},
        "MACD":                          {"df": df_macd, "metrics": m_macd},
    }
    # compare.py 내부에서 COLORS 키를 "MA", "RSI", "MACD"로 참조하므로 매핑
    strategies = {
        "MA":   {"df": df_ma,   "metrics": m_ma,   "label": f"MA{args.short}/{args.long}"},
        "RSI":  {"df": df_rsi,  "metrics": m_rsi,  "label": f"RSI({args.rsi_buy}/{args.rsi_sell})"},
        "MACD": {"df": df_macd, "metrics": m_macd, "label": "MACD"},
    }

    title = f"{args.ticker} ({market})"
    print_comparison(strategies, args.ticker)
    plot_comparison(strategies, title)


if __name__ == "__main__":
    main()
