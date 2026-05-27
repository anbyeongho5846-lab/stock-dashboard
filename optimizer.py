"""
MA 파라미터 최적화 — 단기/장기 이동평균 조합 전체 탐색
사용법:
  python optimizer.py AAPL
  python optimizer.py 005930 --kr --days 730
  python optimizer.py TSLA --shorts 3 5 10 20 --longs 20 60 120
"""

import argparse
import sys
from datetime import datetime, timedelta
from itertools import product

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

DEFAULT_SHORTS = [3, 5, 10, 15, 20]
DEFAULT_LONGS  = [20, 30, 60, 120]


# ── 최적화 ────────────────────────────────────────────────────────────────────

def optimize(
    df: pd.DataFrame,
    shorts: list[int],
    longs: list[int],
    capital: float,
) -> pd.DataFrame:
    pairs = [(s, l) for s, l in product(shorts, longs) if s < l]
    results = []

    for i, (s, l) in enumerate(pairs, 1):
        print(f"  [{i:2d}/{len(pairs)}] MA{s}/MA{l} 테스트 중...", end="\r", flush=True)
        _, _, m = run_backtest(df.copy(), s, l, capital)
        results.append({
            "short": s,
            "long": l,
            "label": f"MA{s}/MA{l}",
            "total_return": m["total_return"],
            "bh_return":    m["bh_return"],
            "excess":       m["total_return"] - m["bh_return"],
            "win_rate":     m["win_rate"],
            "sharpe":       m["sharpe"],
            "mdd":          m["mdd"],
            "n_trades":     m["n_trades"],
        })

    print(" " * 50, end="\r")
    return pd.DataFrame(results).sort_values("total_return", ascending=False).reset_index(drop=True)


# ── 시각화 ────────────────────────────────────────────────────────────────────

def plot_results(results: pd.DataFrame, ticker: str, show: bool = True) -> go.Figure:
    shorts = sorted(results["short"].unique())
    longs  = sorted(results["long"].unique())
    bh     = results["bh_return"].iloc[0]

    # 히트맵 행렬 구성 (y=장기MA, x=단기MA)
    z, text = [], []
    for l in longs:
        row_z, row_t = [], []
        for s in shorts:
            match = results[(results["short"] == s) & (results["long"] == l)]
            if match.empty:
                row_z.append(None)
                row_t.append("—")
            else:
                v = match.iloc[0]["total_return"]
                row_z.append(v)
                row_t.append(f"{v:+.1f}%")
        z.append(row_z)
        text.append(row_t)

    top10 = results.head(10)
    excess_colors = [
        "#2dc653" if v >= 0 else "#e63946"
        for v in top10["excess"]
    ]

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.48, 0.52],
        subplot_titles=("수익률 히트맵 (%)", "상위 10개 조합"),
        specs=[[{"type": "heatmap"}, {"type": "table"}]],
        horizontal_spacing=0.06,
    )

    # 히트맵 (B&H 수익률을 중앙값으로)
    fig.add_trace(go.Heatmap(
        z=z,
        x=[f"MA{s}" for s in shorts],
        y=[f"MA{l}" for l in longs],
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=12),
        colorscale="RdYlGn",
        zmid=bh,
        colorbar=dict(title="수익률(%)"),
        hovertemplate="단기: %{x}<br>장기: %{y}<br>수익률: %{text}<extra></extra>",
    ), row=1, col=1)

    # Buy&Hold 기준선 표시용 주석
    fig.add_annotation(
        text=f"히트맵 중앙 = Buy&Hold ({bh:+.1f}%)<br>초록: 초과, 빨강: 미달",
        xref="paper", yref="paper", x=0.01, y=-0.12,
        showarrow=False, font=dict(size=11, color="#aaa"),
    )

    # 상위 10개 테이블
    fig.add_trace(go.Table(
        header=dict(
            values=["조합", "수익률", "B&H대비", "승률", "샤프지수", "MDD", "거래수"],
            fill_color="#1a1a2e",
            font=dict(color="white", size=12),
            align="center",
            height=28,
        ),
        cells=dict(
            values=[
                top10["label"],
                top10["total_return"].map("{:+.1f}%".format),
                top10["excess"].map("{:+.1f}%".format),
                top10["win_rate"].map("{:.0f}%".format),
                top10["sharpe"].map("{:.2f}".format),
                top10["mdd"].map("{:.1f}%".format),
                top10["n_trades"].map("{}회".format),
            ],
            fill_color=[["#252840" if i % 2 == 0 else "#1e2132" for i in range(len(top10))]],
            font=dict(
                color=[
                    excess_colors,           # 조합명: 초과수익 색
                    ["white"] * len(top10),
                    excess_colors,           # B&H대비: 동일 색
                    ["white"] * len(top10),
                    ["white"] * len(top10),
                    ["white"] * len(top10),
                    ["white"] * len(top10),
                ],
                size=11,
            ),
            align="center",
            height=24,
        ),
    ), row=1, col=2)

    fig.update_layout(
        height=520,
        template="plotly_dark",
        title=dict(
            text=f"{ticker} — MA 파라미터 최적화  |  Buy&Hold: {bh:+.1f}%",
            font=dict(size=16),
        ),
        margin=dict(t=80, b=60),
    )
    if show:
        fig.show()
        print("[완료] 브라우저에서 결과를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MA 파라미터 최적화")
    parser.add_argument("ticker")
    parser.add_argument("--kr",      action="store_true")
    parser.add_argument("--days",    type=int,   default=365)
    parser.add_argument("--shorts",  type=int,   nargs="+", default=DEFAULT_SHORTS, metavar="N")
    parser.add_argument("--longs",   type=int,   nargs="+", default=DEFAULT_LONGS,  metavar="N")
    parser.add_argument("--capital", type=float, default=10_000_000)
    args = parser.parse_args()

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    market = "KRX" if args.kr else "US"
    pairs = [(s, l) for s, l in product(args.shorts, args.longs) if s < l]

    print(f"[{market}] {args.ticker}  {start} ~ {end}  총 {len(pairs)}개 조합 탐색 시작")

    try:
        df = fetch_kr(args.ticker, start, end) if args.kr else fetch_us(args.ticker, start, end)
    except Exception as e:
        print(f"[오류] {e}"); return

    if df.empty:
        print("[오류] 데이터 없음. 종목코드를 확인하세요."); return

    df = add_indicators(df)
    results = optimize(df, args.shorts, args.longs, args.capital)

    bh = results["bh_return"].iloc[0]
    beat_bh = (results["excess"] > 0).sum()
    print(f"\n  Buy&Hold: {bh:+.1f}%  |  초과 달성 조합: {beat_bh}/{len(results)}개\n")
    print(f"  {'순위':<4} {'조합':<12} {'수익률':>8} {'B&H대비':>8} {'승률':>6} {'샤프':>6} {'MDD':>8} {'거래수':>6}")
    print(f"  {'-'*64}")
    for rank, r in results.head(10).iterrows():
        print(
            f"  {rank+1:<4} {r['label']:<12}"
            f" {r['total_return']:>+7.1f}%"
            f" {r['excess']:>+7.1f}%"
            f" {r['win_rate']:>5.0f}%"
            f" {r['sharpe']:>6.2f}"
            f" {r['mdd']:>7.1f}%"
            f" {r['n_trades']:>5}회"
        )
    print()

    plot_results(results, args.ticker)


if __name__ == "__main__":
    main()
