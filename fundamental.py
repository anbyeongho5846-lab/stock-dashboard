"""
기업 기본 분석 — 재무제표(매출·영업이익·순이익) + PER·PBR·ROE·부채비율
국내(.KS) / 미국 종목 모두 지원 (yfinance 기반)

사용법:
  python fundamental.py 005930           # 삼성전자 (국내, 기본 4년)
  python fundamental.py AAPL             # 애플 (미국)
  python fundamental.py 005930 --years 3
"""

import argparse
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _ticker_symbol(ticker: str, kr: bool) -> str:
    """pykrx 코드(005930) → yfinance 심볼(005930.KS)."""
    if kr and not ticker.endswith((".KS", ".KQ")):
        return f"{ticker}.KS"
    return ticker


def _unit(val: float) -> tuple[float, str]:
    """숫자를 읽기 좋은 단위(조/억/만)로 변환."""
    if abs(val) >= 1e12:  return val / 1e12,  "조원"
    if abs(val) >= 1e8:   return val / 1e8,   "억원"
    if abs(val) >= 1e4:   return val / 1e4,   "만원"
    return val, "원"


def _fmt_val(val: float) -> str:
    v, u = _unit(val)
    return f"{v:,.1f}{u}"


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_all(ticker: str, kr: bool, years: int) -> dict:
    # 국내 종목: .KS(KOSPI) 먼저 시도, 실패 시 .KQ(KOSDAQ) 시도
    symbols = []
    if kr and not ticker.endswith((".KS", ".KQ")):
        symbols = [f"{ticker}.KS", f"{ticker}.KQ"]
    else:
        symbols = [ticker]

    info, fin, bal, cf, hist, symbol = {}, None, None, None, None, symbols[0]

    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            _info = t.info or {}
            # info가 비어있지 않으면 이 심볼 사용
            if _info and (_info.get("regularMarketPrice") or _info.get("currentPrice")
                          or _info.get("shortName") or _info.get("longName")):
                info   = _info
                symbol = sym
                break
            elif _info:
                info   = _info
                symbol = sym
        except Exception:
            continue

    # 나머지 데이터는 확정된 심볼로 조회
    try:
        t = yf.Ticker(symbol)
    except Exception:
        t = None

    if t:
        if not info:
            try:   info = t.info or {}
            except Exception: info = {}

        try:   fin  = t.financials
        except Exception: fin = pd.DataFrame()

        try:   bal  = t.balance_sheet
        except Exception: bal = pd.DataFrame()

        try:   cf   = t.cash_flow
        except Exception: cf = pd.DataFrame()

        try:   hist = t.history(period=f"{years}y")
        except Exception: hist = pd.DataFrame()

    # 최소한 심볼 정보라도 있으면 반환
    if info or (hist is not None and not hist.empty):
        return dict(info=info or {}, financials=fin, balance=bal, cashflow=cf,
                    history=hist, symbol=symbol, ticker=ticker)

    raise ValueError(f"데이터를 가져오지 못했습니다: {ticker}")


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_summary(d: dict) -> None:
    info = d["info"]
    name = info.get("longName") or info.get("shortName") or d["symbol"]

    cur_price = info.get("currentPrice") or info.get("regularMarketPrice")
    mkt_cap   = info.get("marketCap")
    per       = info.get("trailingPE") or info.get("forwardPE")
    pbr       = info.get("priceToBook")
    roe       = info.get("returnOnEquity")
    de_ratio  = info.get("debtToEquity")
    div_yield = info.get("dividendYield")
    eps       = info.get("trailingEps")
    beta      = info.get("beta")

    def _show(label: str, val, fmt: str = "", suffix: str = "") -> None:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            print(f"  {label:<22}: N/A")
        else:
            print(f"  {label:<22}: {val:{fmt}}{suffix}")

    print(f"\n{'='*56}")
    print(f"  {name}  ({d['symbol']})")
    print(f"  기준: {datetime.today().strftime('%Y-%m-%d')}")
    print(f"{'='*56}")
    if cur_price:  print(f"  현재가               : {cur_price:>12,.2f}")
    if mkt_cap:    print(f"  시가총액             : {_fmt_val(mkt_cap):>15}")
    _show("PER (주가수익비율)",  per,  ".2f", "배")
    _show("PBR (주가순자산비율)", pbr, ".2f", "배")
    _show("EPS (주당순이익)",    eps,  ",.2f")
    _show("ROE (자기자본이익률)", roe and roe * 100, ".2f", "%")
    _show("부채비율",           de_ratio, ".2f", "%")
    _show("배당수익률",         div_yield and div_yield * 100, ".2f", "%")
    _show("Beta",              beta,   ".3f")
    print(f"{'='*56}\n")


# ── 차트 ─────────────────────────────────────────────────────────────────────

def _get_row(df: pd.DataFrame, *keys) -> pd.Series | None:
    """키 목록 중 DataFrame에 있는 첫 번째 행 반환."""
    if df is None or df.empty:
        return None
    for key in keys:
        if key in df.index:
            return df.loc[key].sort_index()
    return None


def plot(d: dict, show: bool = True) -> go.Figure:
    info = d["info"]
    fin  = d["financials"]
    bal  = d["balance"]
    hist = d["history"]
    name = info.get("longName") or info.get("shortName") or d["symbol"]

    # 재무 데이터 추출
    revenue   = _get_row(fin,  "Total Revenue")
    op_income = _get_row(fin,  "Operating Income", "EBIT")
    net_income= _get_row(fin,  "Net Income")
    total_eq  = _get_row(bal,  "Stockholders Equity", "Total Equity Gross Minority Interest",
                               "Common Stock Equity")
    total_debt= _get_row(bal,  "Total Debt", "Long Term Debt And Capital Lease Obligation")
    fcf       = _get_row(d["cashflow"], "Free Cash Flow")

    has_fin  = any(x is not None for x in [revenue, op_income, net_income])
    has_bal  = any(x is not None for x in [total_eq, total_debt])

    rows    = 3 if has_fin else 2
    heights = [0.40, 0.30, 0.30] if has_fin else [0.55, 0.45]
    titles  = [f"{name} ({d['symbol']}) — 주가", "재무 지표 (PER/PBR)", "연간 손익 추이"][:rows]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=False,
        vertical_spacing=0.06,
        subplot_titles=titles,
        row_heights=heights,
    )

    # ① 주가 차트
    if not hist.empty:
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist["Close"],
            fill="tozeroy", fillcolor="rgba(69,123,157,0.1)",
            line=dict(color="#457b9d", width=2),
            name="주가",
        ), row=1, col=1)

    # ② 재무 지표 바차트 (연간)
    if has_fin:
        years_idx = None
        for s in [revenue, op_income, net_income]:
            if s is not None:
                years_idx = s.index
                break

        if years_idx is not None:
            yr_labels = [str(y)[:4] for y in years_idx]

            def _bar(series, name_, color):
                if series is None: return
                vals, unit = [], ""
                for v in series:
                    vv, unit = _unit(v) if not pd.isna(v) else (0, "")
                    vals.append(vv)
                fig.add_trace(go.Bar(
                    x=yr_labels, y=vals,
                    name=f"{name_}({unit})",
                    marker_color=color, opacity=0.85,
                ), row=rows, col=1)

            _bar(revenue,    "매출액",    "#457b9d")
            _bar(op_income,  "영업이익",  "#2dc653")
            _bar(net_income, "순이익",    "#f4a261")

            # 영업이익률 선 (보조축)
            if revenue is not None and op_income is not None:
                margin = (op_income / revenue * 100).dropna()
                fig.add_trace(go.Scatter(
                    x=[str(y)[:4] for y in margin.index],
                    y=margin,
                    name="영업이익률(%)",
                    mode="lines+markers",
                    line=dict(color="#e63946", width=2, dash="dot"),
                    yaxis="y4",
                ), row=rows, col=1)

    # ③ PER / PBR (현재 값 텍스트)
    per = info.get("trailingPE") or info.get("forwardPE")
    pbr = info.get("priceToBook")
    roe = info.get("returnOnEquity")

    metrics   = []
    bar_vals  = []
    bar_colors= []
    for label, val, good_thresh, color in [
        ("PER", per, 15, "#f4a261"),
        ("PBR", pbr, 1,  "#9b5de5"),
        ("ROE%", roe and roe * 100, 10, "#2dc653"),
    ]:
        if val is not None and not pd.isna(val):
            metrics.append(label)
            bar_vals.append(round(val, 2))
            bar_colors.append(color)

    if metrics:
        fig.add_trace(go.Bar(
            x=metrics, y=bar_vals,
            marker_color=bar_colors,
            text=[f"{v:.2f}" for v in bar_vals],
            textposition="outside",
            name="투자지표",
            showlegend=False,
        ), row=2, col=1)

    fig.update_layout(
        height=900,
        template="plotly_dark",
        legend=dict(orientation="h", y=1.02),
        margin=dict(t=80, b=40),
        title=dict(text=f"{name} — 기업 기본 분석", font=dict(size=17)),
        barmode="group",
    )
    if show:
        fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="기업 기본 분석 (yfinance)")
    parser.add_argument("ticker",        help="종목코드 예) 005930 또는 AAPL")
    parser.add_argument("--kr",          action="store_true", help="국내 주식 (자동 .KS 추가)")
    parser.add_argument("--years", "-y", type=int, default=4, help="조회 기간 (년, 기본 4)")
    args = parser.parse_args()

    # 6자리 숫자면 국내 주식으로 자동 인식
    is_kr = args.kr or args.ticker.isdigit()

    print(f"[{args.ticker}] 데이터 수집 중...")
    d = fetch_all(args.ticker, is_kr, args.years)

    if d["history"].empty and (d["financials"] is None or d["financials"].empty):
        print("[오류] 데이터를 가져오지 못했습니다. 종목코드를 확인하세요.")
        return

    print_summary(d)
    plot(d)


if __name__ == "__main__":
    main()
