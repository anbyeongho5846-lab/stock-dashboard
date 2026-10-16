"""
업종 / 테마 현황 대시보드 (네이버증권 스크래핑)
사용법:
  python sector.py                    # 업종 현황 (기본)
  python sector.py --type theme       # 테마 현황
  python sector.py --no-chart
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import requests

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

_TYPE_LABEL = {"upjong": "업종", "theme": "테마"}

# 클라우드 서버는 UTC → 표시 시각은 한국 시간(UTC+9)으로 고정
_KST = timezone(timedelta(hours=9))


def _now_kst_str() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d %H:%M")

# 네이버 모바일 증권 JSON API
# (2026-09 개편: finance.naver.com sise_group 페이지가 stock.naver.com SPA로
#  이전되어 표 스크래핑이 깨짐 → 아래 내부 API를 사용한다.)
_MOBILE_API = "https://m.stock.naver.com/api/stocks"
# 앱 내부 코드(upjong/theme) → API 리소스명
_API_KIND = {"upjong": "industry", "theme": "theme"}


# ── 데이터 수집 (네이버 모바일 API) ──────────────────────────────────────────

def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0


def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        return float("nan")


def _api_get(path: str, page: int, page_size: int = 100) -> dict:
    r = requests.get(f"{_MOBILE_API}/{path}", headers=_HEADERS,
                     params={"page": page, "pageSize": page_size}, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_sector(type_: str = "upjong") -> pd.DataFrame:
    """업종/테마별 시세 — 네이버 모바일 API의 groups 목록."""
    kind = _API_KIND.get(type_, "industry")
    groups: list = []
    try:
        for page in range(1, 6):          # 최대 500개 (테마 264개 → 3페이지)
            js = _api_get(kind, page)
            g = js.get("groups", [])
            if not g:
                break
            groups.extend(g)
            if len(groups) >= js.get("totalCount", 0):
                break
    except Exception:
        if not groups:
            return pd.DataFrame()

    rows = []
    for g in groups:
        name = g.get("name", "")
        if not name:
            continue
        rows.append({
            "섹터명":   name,
            "등락률":   _to_float(g.get("changeRate")),
            "종목수":   _to_int(g.get("totalCount")),
            "상승수":   _to_int(g.get("riseCount")),
            "하락수":   _to_int(g.get("fallCount")),
            "보합수":   _to_int(g.get("steadyCount")),
            "sector_no": str(g.get("no", "")),   # 드릴다운용
        })
    return pd.DataFrame(rows).reset_index(drop=True)


def fetch_sector_detail(type_: str, no: str) -> pd.DataFrame:
    """업종/테마 소속 종목 목록 — /api/stocks/{industry|theme}/{no}."""
    kind = _API_KIND.get(type_, "industry")
    stocks: list = []
    try:
        for page in range(1, 11):         # 최대 1,000종목
            js = _api_get(f"{kind}/{no}", page)
            s = js.get("stocks", [])
            if not s:
                break
            stocks.extend(s)
            if len(stocks) >= js.get("totalCount", 0):
                break
    except Exception:
        if not stocks:
            return pd.DataFrame()

    rows = []
    for s in stocks:
        name = s.get("stockName", "")
        if not name:
            continue
        rows.append({
            "종목명":   name,
            "현재가":   _to_int(s.get("closePriceRaw") or s.get("closePrice")),
            "등락률":   _to_float(s.get("fluctuationsRatio")),
            "거래량":   _to_int(s.get("accumulatedTradingVolumeRaw")
                             or s.get("accumulatedTradingVolume")),
            # marketValueRaw(원) → 억원 (뷰에서 ×1e8 후 포맷하므로 억원 단위로 저장)
            "시가총액": _to_int(s.get("marketValueRaw")) / 1e8,
        })
    return pd.DataFrame(rows).reset_index(drop=True)


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_report(df: pd.DataFrame, type_label: str) -> None:
    if df.empty:
        print("[오류] 데이터가 없습니다.")
        return

    now = _now_kst_str()
    print(f"\n{'='*60}")
    print(f"  {type_label}별 시세 현황  ({now})")
    print(f"  총 {len(df)}개 {type_label}")
    print(f"{'='*60}")

    if "등락률" not in df.columns:
        print("  (등락률 데이터 없음)\n")
        return

    chg = df["등락률"].dropna()
    rising  = int((chg > 0).sum())
    falling = int((chg < 0).sum())
    flat    = len(df) - rising - falling

    # 종목수 통계 (있으면 표시)
    if "상승수" in df.columns:
        total_up   = int(df["상승수"].sum())
        total_down = int(df["하락수"].sum()) if "하락수" in df.columns else 0
        print(f"  업종 상승: {rising}  하락: {falling}  보합: {flat}")
        print(f"  종목 상승: {total_up}  하락: {total_down}\n")
    else:
        print(f"  상승: {rising}  하락: {falling}  보합/N/A: {flat}\n")

    sorted_df = df.dropna(subset=["등락률"]).sort_values("등락률", ascending=False)

    print("  [상승 상위 5]")
    print(f"  {'섹터명':<22} {'등락률':>8}  {'상승/하락':>10}")
    print(f"  {'-'*46}")
    for _, row in sorted_df.head(5).iterrows():
        updn = ""
        if "상승수" in df.columns:
            updn = f"{int(row.get('상승수',0)):3d} ▲ / {int(row.get('하락수',0)):3d} ▼"
        print(f"  {str(row['섹터명'])[:22]:<22} {row['등락률']:>+7.2f}%  {updn}")

    print("\n  [하락 상위 5]")
    print(f"  {'섹터명':<22} {'등락률':>8}  {'상승/하락':>10}")
    print(f"  {'-'*46}")
    for _, row in sorted_df.tail(5).iterrows():
        updn = ""
        if "상승수" in df.columns:
            updn = f"{int(row.get('상승수',0)):3d} ▲ / {int(row.get('하락수',0)):3d} ▼"
        print(f"  {str(row['섹터명'])[:22]:<22} {row['등락률']:>+7.2f}%  {updn}")
    print()


# ── 차트 ─────────────────────────────────────────────────────────────────────
# 히트맵과 등락률 순위를 각각 독립된 그림으로 만든다
# (한 그림에 좌우로 붙이면 둘 다 좁아지고 컬러바가 바차트 레이블을 가림).

# 히트맵 색: ±3%에서 색이 꽉 차도록 고정 → +1%대 변동도 한눈에 빨강/파랑으로 구분
# (국내 관례: 상승 빨강 / 하락 파랑, 보합은 회색)
_TM_RANGE = 3.0
_TM_COLORSCALE = [
    [0.0,  "#1d4ed8"],   # -3% 이하
    [0.3,  "#35548f"],
    [0.5,  "#414554"],   # 보합
    [0.7,  "#963c48"],
    [1.0,  "#ef4444"],   # +3% 이상
]


def plot_treemap(df: pd.DataFrame, type_label: str) -> go.Figure:
    """업종/테마 히트맵 — 크기: 종목수(제곱근), 색: 등락률."""
    fig = go.Figure()
    if df.empty or "등락률" not in df.columns:
        return fig
    tm = df.dropna(subset=["등락률"]).copy()
    if tm.empty:
        return fig

    def _col(name):
        return (tm[name].fillna(0).astype(int) if name in tm.columns
                else pd.Series(0, index=tm.index))

    n_stock, n_up, n_down = _col("종목수"), _col("상승수"), _col("하락수")

    # 크기: 종목수의 제곱근 → '기타'처럼 종목이 아주 많은 업종이 화면을 독차지하지 않게
    sizes = (n_stock.clip(lower=1) ** 0.5 if n_stock.any()
             else pd.Series(1, index=tm.index))

    # 표시 문자열은 파이썬에서 미리 만든다
    # (트리맵 texttemplate은 customdata에 '+.2f' 서식이 적용되지 않아 '5.3%'처럼 보였음)
    names = tm["섹터명"].astype(str)
    chg   = tm["등락률"].astype(float)
    text  = [f"<b>{n}</b><br>{v:+.2f}%" for n, v in zip(names, chg)]
    hover = [f"<b>{n}</b><br>등락률: {v:+.2f}%<br>종목 {s}개 (▲{u} ▼{d})"
             for n, v, s, u, d in zip(names, chg, n_stock, n_up, n_down)]

    fig.add_trace(go.Treemap(
        labels=names,
        parents=[""] * len(tm),
        values=sizes,
        text=text,
        textinfo="text",
        hovertext=hover,
        hovertemplate="%{hovertext}<extra></extra>",
        textposition="middle center",
        textfont=dict(size=15, color="white"),   # 큰 타일은 15px, 작은 타일은 자동 축소
        pathbar=dict(visible=False),             # 단일 계층이라 상단 경로바 불필요
        marker=dict(
            colors=tm["등락률"],
            colorscale=_TM_COLORSCALE,
            cmin=-_TM_RANGE, cmax=_TM_RANGE,
            line=dict(color="#0e1117", width=2),   # 타일 경계를 또렷하게
            pad=dict(t=0, l=0, r=0, b=0),          # 상단 빈 띠(루트 헤더 영역) 제거
            showscale=True,
            colorbar=dict(
                title=dict(text="등락률", side="top"),
                tickvals=[-3, -2, -1, 0, 1, 2, 3],
                ticktext=["-3%↓", "-2%", "-1%", "0", "+1%", "+2%", "+3%↑"],
                thickness=12, len=0.8,
                tickfont=dict(color="#cbd5e1"),
            ),
        ),
    ))
    fig.update_layout(
        height=620 if len(tm) <= 100 else 780,
        template="plotly_dark",
        margin=dict(t=10, b=10, l=5, r=5),
        hoverlabel=dict(font_size=13),
    )
    return fig


_UP, _DOWN = "#ef4444", "#3b82f6"   # 국내 관례: 상승 빨강 / 하락 파랑


def plot_bar(df: pd.DataFrame, type_label: str, top_n: int | None = 15) -> go.Figure:
    """업종/테마별 등락률 수평 바차트 — 기본은 상위 N + 하위 N, top_n=None이면 전체."""
    fig = go.Figure()
    if df.empty or "등락률" not in df.columns:
        return fig
    bar = df.dropna(subset=["등락률"]).sort_values("등락률", ascending=False)
    if bar.empty:
        return fig

    names = bar["섹터명"].astype(str).tolist()
    vals  = bar["등락률"].astype(float).tolist()

    # 상위 N + 하위 N만 표시하고, 사이에 '생략' 행을 넣어 구간을 구분
    if top_n and len(bar) > top_n * 2:
        gap = f"⋯ 중간 {len(bar) - top_n * 2}개 생략 ⋯"
        names = names[:top_n] + [gap] + names[-top_n:]
        vals  = vals[:top_n] + [None] + vals[-top_n:]

    fig.add_trace(go.Bar(
        x=vals,
        y=names,          # 전체 이름 사용 (클릭 시 드릴다운에 그대로 연결됨)
        orientation="h",
        marker_color=[_UP if (v or 0) >= 0 else _DOWN for v in vals],
        text=["" if v is None else f"{v:+.2f}%" for v in vals],
        textposition="outside",
        textfont=dict(size=12, color="#e2e8f0"),
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>등락률: %{x:+.2f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line_dash="dash", line_width=1,
                  line_color="rgba(255,255,255,0.3)")

    # x축: 실제 값 범위 + 막대 밖 값 라벨 공간 (모두 상승한 날엔 왼쪽 여백을 최소화)
    real = [v for v in vals if v is not None]
    lo, hi = min(min(real), 0.0), max(max(real), 0.0)
    pad = max(hi - lo, 1.0) * 0.18
    x_range = [lo - pad if lo < 0 else -pad * 0.15,
               hi + pad if hi > 0 else pad * 0.15]

    fig.update_layout(
        height=max(380, 70 + len(names) * 26),
        template="plotly_dark",
        margin=dict(t=10, b=40, l=10, r=20),
        showlegend=False,
        bargap=0.25,
        xaxis=dict(title="등락률 (%)", range=x_range, zeroline=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12), automargin=True),
        hoverlabel=dict(font_size=13),
    )
    return fig


def plot(df: pd.DataFrame, type_label: str, show: bool = True) -> go.Figure:
    """CLI용: 히트맵·바차트를 각각 브라우저로 띄우고 히트맵 그림을 반환."""
    tm_fig  = plot_treemap(df, type_label)
    bar_fig = plot_bar(df, type_label)
    title = f"{type_label}별 시세 현황  —  {_now_kst_str()}"
    tm_fig.update_layout(title=dict(text=title, font=dict(size=17)), margin=dict(t=60))
    bar_fig.update_layout(title=dict(text=title, font=dict(size=17)), margin=dict(t=60))
    if show:
        tm_fig.show()
        bar_fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return tm_fig


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="업종/테마 현황 대시보드")
    parser.add_argument("--type", dest="type_", default="upjong",
                        choices=["upjong", "theme"],
                        help="upjong=업종별 (기본) / theme=테마별")
    parser.add_argument("--no-chart", action="store_true")
    args = parser.parse_args()

    type_label = _TYPE_LABEL.get(args.type_, "업종")
    print(f"네이버증권 {type_label} 현황 수집 중...")

    df = fetch_sector(args.type_)
    if df.empty:
        print("[오류] 데이터를 가져오지 못했습니다.")
        return

    print_report(df, type_label)
    if not args.no_chart:
        plot(df, type_label)


if __name__ == "__main__":
    main()
