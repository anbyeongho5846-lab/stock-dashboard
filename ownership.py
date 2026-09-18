"""
외국인 / 기관 / 개인 매매 동향 (네이버증권 스크래핑)
사용법:
  python ownership.py 005930            # 삼성전자 (기본 30일)
  python ownership.py 000660 --days 90
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots
from pykrx import stock as krx

logging.getLogger("pykrx").setLevel(logging.ERROR)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
}

# 네이버 모바일 증권 API — 투자자별 매매 동향
# (2026-09 개편: finance.naver.com/item/frgn 스크래핑이 stock.naver.com SPA
#  이전으로 깨짐 → 아래 내부 JSON API를 사용한다. pageSize 최대 60,
#  page 파라미터는 무효라 과거는 bizdate 앵커로 이어붙인다.)
_TREND_API = "https://m.stock.naver.com/api/stock/{code}/trend"


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_price(ticker: str, start: str, end: str) -> pd.DataFrame:
    s, e = start.replace("-", ""), end.replace("-", "")
    df = krx.get_market_ohlcv_by_date(s, e, ticker)
    df = df.rename(columns={"시가": "Open", "고가": "High",
                             "저가": "Low", "종가": "Close", "거래량": "Volume"})
    df.index = pd.to_datetime(df.index)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def _to_num(v) -> float:
    """콤마·%·부호 섞인 문자열 → float."""
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("+", ""))
    except (ValueError, TypeError):
        return float("nan")


def _fetch_trend_page(ticker: str, anchor: str | None = None) -> list:
    """trend API 한 페이지(최대 60 거래일). anchor(bizdate) 이전까지 반환."""
    params = {"pageSize": 60}
    if anchor:
        params["bizdate"] = anchor
    r = requests.get(_TREND_API.format(code=ticker), headers=_HEADERS,
                     params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def fetch_investor_trading(ticker: str, max_days: int = 180) -> pd.DataFrame:
    """외국인·기관·개인 일별 순매수 — 네이버 모바일 API(/api/stock/{code}/trend).

    한 콜당 최대 60 거래일이라, max_days만큼 확보될 때까지 bizdate 앵커로
    과거를 이어붙인다. (중복 날짜는 dict로 제거)
    """
    records: dict[str, dict] = {}
    anchor: str | None = None
    try:
        for _ in range(4):                 # 60일 × 최대 4콜 ≈ 240 거래일
            batch = _fetch_trend_page(ticker, anchor)
            if not batch:
                break
            before = len(records)
            for rec in batch:
                bd = rec.get("bizdate")
                if bd:
                    records[bd] = rec
            if len(records) == before:     # 더 이상 새 날짜 없음
                break
            if len(records) >= max_days:
                break
            anchor = min(r["bizdate"] for r in batch)  # 다음 콜은 이 날짜 이전
    except Exception:
        if not records:
            return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    rows = [{
        "date":          bd,
        "종가":          _to_num(rec.get("closePrice")),
        "거래량":        _to_num(rec.get("accumulatedTradingVolume")),
        "외국인_순매수": _to_num(rec.get("foreignerPureBuyQuant")),
        "기관_순매수":   _to_num(rec.get("organPureBuyQuant")),
        "개인_순매수":   _to_num(rec.get("individualPureBuyQuant")),
        "외인보유비율":  _to_num(rec.get("foreignerHoldRatio")),
    } for bd, rec in records.items()]

    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df[df.index.notna()].drop(columns=["date"]).sort_index()
    return df


def get_name(ticker: str) -> str:
    try:
        return krx.get_market_ticker_name(ticker)
    except Exception:
        return ticker


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame, ticker: str, name: str) -> None:
    print(f"\n{'='*56}")
    print(f"  {name} ({ticker}) — 투자자별 매매 동향")
    print(f"  최근 {min(20, len(df))}일 기준")
    print(f"{'='*56}")

    recent = df.tail(20)
    for col, label in [("외국인_순매수", "외국인"), ("기관_순매수", "기관")]:
        if col in recent.columns:
            total = recent[col].sum()
            days_buy  = (recent[col] > 0).sum()
            days_sell = (recent[col] < 0).sum()
            direction = "매수우위" if total > 0 else "매도우위"
            print(f"  {label:<6}: 누적 {total:>+12,.0f}주  "
                  f"매수 {days_buy}일 / 매도 {days_sell}일  {direction}")

    if "외인보유비율" in df.columns:
        latest = df["외인보유비율"].dropna()
        if not latest.empty:
            print(f"  외인보유비율: 현재 {latest.iloc[-1]:.2f}%  "
                  f"(최근 최고 {latest.max():.2f}% / 최저 {latest.min():.2f}%)")
    print(f"{'='*56}\n")


# ── 차트 ─────────────────────────────────────────────────────────────────────

def plot(price: pd.DataFrame, inv: pd.DataFrame, ticker: str, name: str, show: bool = True) -> go.Figure:
    has_foreign = "외국인_순매수" in inv.columns
    has_inst    = "기관_순매수" in inv.columns
    has_ratio   = "외인보유비율" in inv.columns

    n_rows   = 2 + has_foreign + has_inst + has_ratio
    heights  = [0.40] + [0.20] * (n_rows - 1)
    subtitles = [f"{name} ({ticker}) — 주가"] + \
                (["외국인 순매수 (주)"] if has_foreign else []) + \
                (["기관 순매수 (주)"]   if has_inst    else []) + \
                (["외국인 보유비율(%)"] if has_ratio   else []) + \
                ["거래량"]

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=subtitles[:n_rows],
        row_heights=heights[:n_rows],
    )
    row = 1

    # ① 주가 캔들
    fig.add_trace(go.Candlestick(
        x=price.index,
        open=price["Open"], high=price["High"],
        low=price["Low"],  close=price["Close"],
        increasing_line_color="#e63946",
        decreasing_line_color="#457b9d",
        name="주가",
    ), row=row, col=1)
    row += 1

    def _net_bar(series: pd.Series, label: str, r: int) -> None:
        colors = ["#e63946" if v >= 0 else "#457b9d" for v in series]
        fig.add_trace(go.Bar(
            x=series.index, y=series,
            marker_color=colors, name=label,
        ), row=r, col=1)
        # 5일 이동평균 누적선
        fig.add_trace(go.Scatter(
            x=series.index, y=series.cumsum(),
            line=dict(color="#f4a261", width=1.5),
            name=f"{label} 누적",
        ), row=r, col=1)
        fig.add_hline(y=0, line_dash="dash",
                      line_color="rgba(255,255,255,0.2)", row=r, col=1)

    # ② 외국인 순매수
    if has_foreign:
        _net_bar(inv["외국인_순매수"].dropna(), "외국인", row)
        row += 1

    # ③ 기관 순매수
    if has_inst:
        _net_bar(inv["기관_순매수"].dropna(), "기관", row)
        row += 1

    # ④ 외인 보유비율
    if has_ratio:
        ratio = inv["외인보유비율"].dropna()
        fig.add_trace(go.Scatter(
            x=ratio.index, y=ratio,
            fill="tozeroy", fillcolor="rgba(244,162,97,0.1)",
            line=dict(color="#f4a261", width=2),
            name="외인보유비율",
        ), row=row, col=1)
        row += 1

    # ⑤ 거래량
    if "Volume" in price.columns:
        vol_colors = ["#e63946" if c >= o else "#457b9d"
                      for c, o in zip(price["Close"], price["Open"])]
        fig.add_trace(go.Bar(
            x=price.index, y=price["Volume"],
            marker_color=vol_colors, name="거래량",
        ), row=row, col=1)

    fig.update_layout(
        height=900,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02),
        margin=dict(t=80, b=40),
        title=dict(text=f"{name} ({ticker}) — 외국인·기관 매매 동향", font=dict(size=17)),
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    if show:
        fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="외국인/기관 매매 동향")
    parser.add_argument("ticker")
    parser.add_argument("--days", type=int, default=60, help="주가 조회 기간 (일, 기본 60)")
    args = parser.parse_args()

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    name = get_name(args.ticker)
    print(f"[{args.ticker}] {name}  네이버증권 데이터 수집 중...")

    price = fetch_price(args.ticker, start, end)
    inv   = fetch_investor_trading(args.ticker)

    if inv.empty:
        print("[오류] 투자자 매매 데이터를 가져오지 못했습니다.")
        return

    # 기간 필터
    cutoff = pd.Timestamp(start)
    inv = inv[inv.index >= cutoff]

    print_summary(inv, args.ticker, name)
    plot(price, inv, args.ticker, name)


if __name__ == "__main__":
    main()
