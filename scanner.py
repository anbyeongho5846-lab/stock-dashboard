"""
포트폴리오 스캐너 — watchlist.txt의 종목을 한 번에 분석해 신호 순위 출력
사용법:
  python scanner.py                        # watchlist.txt 기본 경로
  python scanner.py --watchlist my.txt     # 다른 감시 목록
  python scanner.py --days 120             # 지표 계산 기간 (기본 120일)
  python scanner.py --no-chart             # 차트 없이 터미널 출력만
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analyzer import add_indicators, fetch_kr, fetch_us

logging.getLogger("pykrx").setLevel(logging.ERROR)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_WATCHLIST = Path(__file__).parent / "watchlist.txt"

OPINION_COLOR = {
    "강매수": "#1a6b3a",
    "매수":   "#2dc653",
    "중립":   "#3a3a5c",
    "매도":   "#c0392b",
    "강매도": "#6b0000",
}
OPINION_ORDER = ["강매수", "매수", "중립", "매도", "강매도"]


# ── watchlist 로드 ─────────────────────────────────────────────────────────────

def load_watchlist(path: Path) -> list[tuple[str, str]]:
    tickers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()   # 주석 제거
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            ticker = parts[0].upper()
            market = parts[1].lower() if len(parts) > 1 else "us"
            tickers.append((ticker, market))
    return tickers


# ── 신호 분석 ─────────────────────────────────────────────────────────────────

def _check_recent_cross(df: pd.DataFrame, window: int = 5) -> tuple[bool, bool]:
    """최근 N일 내 골든/데드크로스 발생 여부 반환."""
    golden, dead = False, False
    n = min(window + 1, len(df))
    for i in range(-n, -1):
        try:
            cur  = df.iloc[i]
            prev = df.iloc[i - 1]
            if pd.isna(cur["MA5"]) or pd.isna(cur["MA20"]):
                continue
            if cur["MA5"] > cur["MA20"] and prev["MA5"] <= prev["MA20"]:
                golden = True
            if cur["MA5"] < cur["MA20"] and prev["MA5"] >= prev["MA20"]:
                dead = True
        except IndexError:
            break
    return golden, dead


def analyze(df: pd.DataFrame, ticker: str, market: str) -> dict | None:
    if df.empty or len(df) < 30:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close      = last["Close"]
    change_pct = (close - prev["Close"]) / prev["Close"] * 100
    rsi        = float(last["RSI"])    if not pd.isna(last.get("RSI", float("nan")))       else 50.0
    ma5        = float(last["MA5"])    if not pd.isna(last.get("MA5", float("nan")))       else close
    ma20       = float(last["MA20"])   if not pd.isna(last.get("MA20", float("nan")))      else close
    ma60       = float(last["MA60"])   if not pd.isna(last.get("MA60", float("nan")))      else close
    macd_hist  = float(last["MACD_Diff"]) if not pd.isna(last.get("MACD_Diff", float("nan"))) else 0.0

    ma_golden    = ma5 > ma20
    above_ma60   = close > ma60
    macd_up      = macd_hist > 0

    recent_golden, recent_dead = _check_recent_cross(df)

    # 매수 신호
    buys: list[str] = []
    if recent_golden:   buys.append("골든크로스")
    if rsi < 30:        buys.append("RSI 과매도")
    if macd_up:         buys.append("MACD 상승")
    if above_ma60 and ma_golden: buys.append("MA60 위")

    # 매도 신호
    sells: list[str] = []
    if recent_dead:     sells.append("데드크로스")
    if rsi > 70:        sells.append("RSI 과매수")
    if not macd_up:     sells.append("MACD 하락")
    if not ma_golden:   sells.append("MA 하락배열")

    score = len(buys) - len(sells) * 0.5

    if score >= 3:      opinion = "강매수"
    elif score >= 1.5:  opinion = "매수"
    elif score >= 0:    opinion = "중립"
    elif score >= -1:   opinion = "매도"
    else:               opinion = "강매도"

    return {
        "ticker":        ticker,
        "market":        market.upper(),
        "close":         close,
        "change_pct":    change_pct,
        "rsi":           rsi,
        "ma_golden":     ma_golden,
        "above_ma60":    above_ma60,
        "macd_up":       macd_up,
        "recent_golden": recent_golden,
        "recent_dead":   recent_dead,
        "buys":          buys,
        "sells":         sells,
        "score":         score,
        "opinion":       opinion,
        "volume":        int(last["Volume"]),
        "ma5":           ma5,
        "ma20":          ma20,
        "ma60":          ma60,
    }


# ── 스캔 실행 ─────────────────────────────────────────────────────────────────

def scan(watchlist: list[tuple[str, str]], days: int) -> list[dict]:
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    results = []

    for i, (ticker, market) in enumerate(watchlist, 1):
        print(f"  [{i:2d}/{len(watchlist)}] {ticker:10s} ({market.upper()}) 분석 중...",
              end="\r", flush=True)
        try:
            df = fetch_kr(ticker, start, end) if market == "kr" else fetch_us(ticker, start, end)
            if df.empty:
                continue
            df  = add_indicators(df)
            row = analyze(df, ticker, market)
            if row:
                results.append(row)
        except Exception as e:
            print(f"\n  [건너뜀] {ticker}: {e}")

    print(" " * 60, end="\r")
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_report(results: list[dict]) -> None:
    now = datetime.today().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*85}")
    print(f"  포트폴리오 스캔 결과  ({now})  총 {len(results)}개 종목")
    print(f"{'='*85}")
    print(f"  {'종목':<10} {'시장':<4} {'현재가':>12} {'등락':>7}"
          f" {'RSI':>5} {'MA배열':<7} {'MACD':<5} {'매수신호':<28} {'의견'}")
    print(f"  {'-'*83}")

    for r in results:
        close_str  = f"{r['close']:,.0f}"
        change_str = f"{r['change_pct']:+.1f}%"
        ma_str     = "골든" if r["ma_golden"] else "데드"
        macd_str   = "UP" if r["macd_up"] else "DN"
        buy_str    = ", ".join(r["buys"]) if r["buys"] else "-"

        print(
            f"  {r['ticker']:<10} {r['market']:<4} {close_str:>12} {change_str:>7}"
            f" {r['rsi']:>5.0f} {ma_str:<7} {macd_str:<5} {buy_str:<28} {r['opinion']}"
        )

    print(f"{'='*85}")

    buy_list  = [r["ticker"] for r in results if r["opinion"] in ("강매수", "매수")]
    sell_list = [r["ticker"] for r in results if r["opinion"] in ("강매도", "매도")]
    if buy_list:  print(f"\n  [매수 신호]  {', '.join(buy_list)}")
    if sell_list: print(f"  [매도 신호]  {', '.join(sell_list)}")
    print()


def plot_dashboard(results: list[dict], show: bool = True) -> go.Figure:
    if not results:
        return

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.68, 0.32],
        subplot_titles=("종목별 신호 현황", "의견 분포"),
        specs=[[{"type": "table"}, {"type": "pie"}]],
        horizontal_spacing=0.05,
    )

    # ── 종목 테이블 ──────────────────────────────────────────────────────────
    def _rsi_color(v: float) -> str:
        if v > 70: return "#6b0000"
        if v < 30: return "#1a6b3a"
        return "#252840"

    def _chg_color(v: float) -> str:
        return "#1a6b3a" if v > 0 else "#6b0000" if v < 0 else "#252840"

    row_bg = ["#252840" if i % 2 == 0 else "#1e2132" for i in range(len(results))]

    fig.add_trace(go.Table(
        header=dict(
            values=["종목", "시장", "현재가", "등락", "RSI", "MA", "MACD", "매수 신호", "의견"],
            fill_color="#1a1a2e",
            font=dict(color="white", size=12),
            align="center", height=30,
        ),
        cells=dict(
            values=[
                [r["ticker"]                              for r in results],
                [r["market"]                              for r in results],
                [f"{r['close']:,.0f}"                     for r in results],
                [f"{r['change_pct']:+.1f}%"               for r in results],
                [f"{r['rsi']:.0f}"                        for r in results],
                ["골든" if r["ma_golden"] else "데드"      for r in results],
                ["UP" if r["macd_up"] else "DN"           for r in results],
                [", ".join(r["buys"]) if r["buys"] else "-" for r in results],
                [r["opinion"]                             for r in results],
            ],
            fill_color=[
                row_bg,
                row_bg,
                row_bg,
                [_chg_color(r["change_pct"])              for r in results],
                [_rsi_color(r["rsi"])                     for r in results],
                ["#1a6b3a" if r["ma_golden"] else "#6b0000" for r in results],
                ["#1a6b3a" if r["macd_up"]   else "#6b0000" for r in results],
                row_bg,
                [OPINION_COLOR.get(r["opinion"], "#252840") for r in results],
            ],
            font=dict(color="white", size=11),
            align="center", height=26,
        ),
    ), row=1, col=1)

    # ── 의견 분포 파이차트 ────────────────────────────────────────────────────
    opinion_counts = {o: 0 for o in OPINION_ORDER}
    for r in results:
        opinion_counts[r["opinion"]] = opinion_counts.get(r["opinion"], 0) + 1

    labels  = [o for o, cnt in opinion_counts.items() if cnt > 0]
    values  = [opinion_counts[o] for o in labels]
    colors  = [OPINION_COLOR[o] for o in labels]

    fig.add_trace(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#1a1a2e", width=2)),
        textinfo="label+value",
        textfont=dict(color="white", size=12),
        showlegend=False,
        hole=0.35,
    ), row=1, col=2)

    fig.update_layout(
        height=max(400, 100 + len(results) * 28),
        template="plotly_dark",
        title=dict(
            text=f"포트폴리오 스캔  —  {datetime.today().strftime('%Y-%m-%d')}",
            font=dict(size=17),
        ),
        margin=dict(t=80, b=20),
    )
    if show:
        fig.show()
        print("[완료] 브라우저에서 대시보드를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="포트폴리오 스캐너")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST,
                        help=f"감시 목록 파일 (기본: {DEFAULT_WATCHLIST.name})")
    parser.add_argument("--days",     type=int, default=120, help="데이터 조회 기간 (기본 120일)")
    parser.add_argument("--no-chart", action="store_true",   help="차트 없이 터미널 출력만")
    args = parser.parse_args()

    if not args.watchlist.exists():
        print(f"[오류] {args.watchlist} 파일을 찾을 수 없습니다.")
        return

    watchlist = load_watchlist(args.watchlist)
    print(f"총 {len(watchlist)}개 종목 스캔 시작...")

    results = scan(watchlist, args.days)
    print_report(results)

    if not args.no_chart:
        plot_dashboard(results)


if __name__ == "__main__":
    main()
