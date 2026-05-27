"""
시장 순위 & 랭킹 대시보드 (네이버증권 스크래핑)
사용법:
  python ranking.py                   # KOSPI 전체 (등락률·거래량·시총 상위/하위)
  python ranking.py --market KOSDAQ
  python ranking.py --top 30
  python ranking.py --no-chart
"""

import argparse
import sys
from datetime import datetime
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

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
    "Referer": "https://finance.naver.com/",
}

# 네이버증권 시세 URL 맵
_MARKET_PARAM = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}
_NAVER_SISE   = "https://finance.naver.com/sise/sise_market_sum.naver"


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def _scrape_table(url: str, params: dict | None = None, table_idx: int = 1) -> pd.DataFrame:
    r = requests.get(url, headers=_HEADERS, params=params, timeout=15)
    html = r.content.decode("euc-kr", errors="replace")
    tables = pd.read_html(StringIO(html), thousands=",")
    if not tables or len(tables) <= table_idx:
        return pd.DataFrame()
    return tables[table_idx]


def _scrape_rise_fall(market: str = "KOSPI", rise: bool = True) -> pd.DataFrame:
    """등락률 상위(rise=True) / 하위(rise=False)."""
    path = "sise_rise" if rise else "sise_fall"
    url  = f"https://finance.naver.com/sise/{path}.naver"
    r = requests.get(url, headers=_HEADERS, params={"sosok": "0" if market == "KOSPI" else "1"}, timeout=15)
    html = r.content.decode("euc-kr", errors="replace")
    tables = pd.read_html(StringIO(html), thousands=",")

    df = None
    for t in tables:
        if t.shape[1] >= 6 and len(t) > 5:
            df = t
            break
    if df is None:
        return pd.DataFrame()

    # 컬럼 정규화
    df.columns = [str(c) for c in df.columns]
    rename = {}
    for c in df.columns:
        if "종목" in c or "이름" in c or "name" in c.lower(): rename[c] = "종목명"
        elif "현재" in c or "가격" in c:                       rename[c] = "현재가"
        elif "등락률" in c:                                    rename[c] = "등락률"
        elif "거래량" in c:                                    rename[c] = "거래량"
        elif "시가총액" in c:                                  rename[c] = "시가총액"
        elif "N" == c or "순위" in c:                          rename[c] = "순위"
    df = df.rename(columns=rename)
    df = df.dropna(subset=["종목명"] if "종목명" in df.columns else df.columns[:1])
    df = df[df["종목명"].notna() & (df["종목명"] != "종목명")]

    for col in ["현재가", "등락률", "거래량", "시가총액"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("%", "").str.replace("+", ""),
                errors="coerce"
            )
    return df.reset_index(drop=True)


def _scrape_volume(market: str = "KOSPI") -> pd.DataFrame:
    """거래량 상위."""
    r = requests.get(
        "https://finance.naver.com/sise/sise_quant.naver",
        headers=_HEADERS,
        params={"sosok": "0" if market == "KOSPI" else "1"},
        timeout=15,
    )
    html = r.content.decode("euc-kr", errors="replace")
    tables = pd.read_html(StringIO(html), thousands=",")
    df = None
    for t in tables:
        if t.shape[1] >= 5 and len(t) > 5:
            df = t; break
    if df is None: return pd.DataFrame()

    df.columns = [str(c) for c in df.columns]
    rename = {}
    for c in df.columns:
        if "종목" in c or "이름" in c: rename[c] = "종목명"
        elif "현재" in c:              rename[c] = "현재가"
        elif "등락률" in c:            rename[c] = "등락률"
        elif "거래량" in c:            rename[c] = "거래량"
        elif "시가총액" in c:          rename[c] = "시가총액"
    df = df.rename(columns=rename).dropna(how="all")
    df = df[df.get("종목명", pd.Series(dtype=str)).notna()]
    for col in ["현재가", "등락률", "거래량", "시가총액"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("%", "").str.replace("+", ""),
                errors="coerce"
            )
    return df.reset_index(drop=True)


def fetch_rankings(market: str) -> dict[str, pd.DataFrame]:
    print("  등락률 상위 수집 중...", end="\r", flush=True)
    rise = _scrape_rise_fall(market, rise=True)
    print("  등락률 하위 수집 중...", end="\r", flush=True)
    fall = _scrape_rise_fall(market, rise=False)
    print("  거래량 상위 수집 중...", end="\r", flush=True)
    vol  = _scrape_volume(market)
    print(" " * 30, end="\r")
    return {"rise": rise, "fall": fall, "volume": vol}


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_report(data: dict, market: str, top: int) -> None:
    now = datetime.today().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*72}")
    print(f"  {market} 시장 순위  ({now})")
    print(f"{'='*72}")

    def _section(title: str, df: pd.DataFrame) -> None:
        if df.empty:
            print(f"\n  [{title}]  (데이터 없음)")
            return
        print(f"\n  [{title}]")
        name_col = "종목명" if "종목명" in df.columns else df.columns[0]
        cols = [name_col]
        for c in ["현재가", "등락률", "거래량", "시가총액"]:
            if c in df.columns: cols.append(c)
        sub = df[cols].head(top).copy()

        header = f"  {'종목명':<16}"
        if "현재가"  in cols: header += f" {'현재가':>10}"
        if "등락률"  in cols: header += f" {'등락률':>7}"
        if "거래량"  in cols: header += f" {'거래량(만)':>11}"
        if "시가총액" in cols: header += f" {'시총(억)':>10}"
        print(header)
        print(f"  {'-'*70}")

        for _, row in sub.iterrows():
            line = f"  {str(row[name_col])[:15]:<16}"
            if "현재가"  in cols: line += f" {row['현재가']:>10,.0f}"
            if "등락률"  in cols: line += f" {row['등락률']:>+6.2f}%"
            if "거래량"  in cols: line += f" {row['거래량']/10000:>10,.0f}"
            if "시가총액" in cols: line += f" {row['시가총액']/1e4:>9,.0f}"
            print(line)

    _section(f"등락률 상위 {top}", data["rise"])
    _section(f"등락률 하위 {top}", data["fall"])
    _section(f"거래량 상위 {top}", data["volume"])
    print()


# ── 차트 ─────────────────────────────────────────────────────────────────────

def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    """컬럼이 없으면 0으로 채운 Series 반환 (list 반환으로 fillna 실패 방지)."""
    if col in df.columns:
        return df[col].fillna(0)
    return pd.Series([0] * len(df), index=df.index)


def _make_table(df: pd.DataFrame, top: int) -> go.Table:
    name_col = "종목명" if "종목명" in df.columns else df.columns[0]
    sub = df.head(top)
    chg_vals = _safe_col(sub, "등락률").tolist()
    row_bg   = ["#252840" if i % 2 == 0 else "#1e2132" for i in range(len(sub))]
    chg_bg   = ["#1a6b3a" if v > 0 else "#6b0000" if v < 0 else "#3a3a5c" for v in chg_vals]

    return go.Table(
        header=dict(
            values=["종목명", "현재가", "등락률", "거래량(만)", "시총(억)"],
            fill_color="#1a1a2e",
            font=dict(color="white", size=11),
            align="center", height=26,
        ),
        cells=dict(
            values=[
                [str(r)[:12] for r in sub[name_col]],
                [f"{v:,.0f}" for v in _safe_col(sub, "현재가")],
                [f"{v:+.2f}%" for v in chg_vals],
                [f"{v/10000:.0f}" for v in _safe_col(sub, "거래량")],
                [f"{v/1e4:,.0f}" for v in _safe_col(sub, "시가총액")],
            ],
            fill_color=[row_bg, row_bg, chg_bg, row_bg, row_bg],
            font=dict(color="white", size=10),
            align="center", height=22,
        ),
    )


def plot_dashboard(data: dict, market: str, top: int, show: bool = True) -> go.Figure:
    rise = data["rise"]
    fall = data["fall"]
    vol  = data["volume"]

    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=(
            f"등락률 상위 {top}",
            f"등락률 하위 {top}",
            f"거래량 상위 {top}",
            "등락률 상위 — 바차트",
            "등락률 하위 — 바차트",
            "거래량 상위 — 바차트",
        ),
        specs=[[{"type": "table"}]*3, [{"type": "bar"}]*3],
        vertical_spacing=0.08,
        horizontal_spacing=0.04,
        row_heights=[0.55, 0.45],
    )

    name_col = lambda df: "종목명" if "종목명" in df.columns else df.columns[0]

    # 테이블
    for col_idx, df in enumerate([rise, fall, vol], 1):
        if not df.empty:
            fig.add_trace(_make_table(df, top), row=1, col=col_idx)

    # 바차트 - 등락률 상위
    if not rise.empty:
        nc = name_col(rise)
        top_rise = rise.head(top)
        fig.add_trace(go.Bar(
            x=top_rise[nc].astype(str).tolist(),
            y=top_rise.get("등락률", pd.Series([0]*len(top_rise))).tolist(),
            marker_color="#e63946", showlegend=False,
        ), row=2, col=1)

    # 바차트 - 등락률 하위
    if not fall.empty:
        nc = name_col(fall)
        top_fall = fall.head(top)
        fig.add_trace(go.Bar(
            x=top_fall[nc].astype(str).tolist(),
            y=top_fall.get("등락률", pd.Series([0]*len(top_fall))).tolist(),
            marker_color="#457b9d", showlegend=False,
        ), row=2, col=2)

    # 바차트 - 거래량
    if not vol.empty:
        nc = name_col(vol)
        top_vol = vol.head(top)
        fig.add_trace(go.Bar(
            x=top_vol[nc].astype(str).tolist(),
            y=(top_vol.get("거래량", pd.Series([0]*len(top_vol))).fillna(0) / 1e4).tolist(),
            marker_color="#9b5de5", showlegend=False,
        ), row=2, col=3)

    fig.update_layout(
        height=900,
        template="plotly_dark",
        title=dict(
            text=f"{market} 시장 현황  —  {datetime.today().strftime('%Y-%m-%d')}",
            font=dict(size=17),
        ),
        margin=dict(t=80, b=30),
    )
    fig.update_yaxes(title_text="등락률(%)",  row=2, col=1)
    fig.update_yaxes(title_text="등락률(%)",  row=2, col=2)
    fig.update_yaxes(title_text="거래량(만주)", row=2, col=3)
    if show:
        fig.show()
        print("[완료] 브라우저에서 대시보드를 확인하세요.")
    return fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="시장 순위 & 랭킹")
    parser.add_argument("--market",   default="KOSPI", choices=["KOSPI", "KOSDAQ"])
    parser.add_argument("--top",      type=int, default=20)
    parser.add_argument("--no-chart", action="store_true")
    args = parser.parse_args()

    print(f"[{args.market}] 네이버증권 실시간 순위 수집 중...")
    data = fetch_rankings(args.market)

    total = sum(len(v) for v in data.values())
    if total == 0:
        print("[오류] 데이터를 가져오지 못했습니다.")
        return

    print_report(data, args.market, args.top)
    if not args.no_chart:
        plot_dashboard(data, args.market, args.top)


if __name__ == "__main__":
    main()
