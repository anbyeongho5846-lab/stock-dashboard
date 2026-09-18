"""
업종 / 테마 현황 대시보드 (네이버증권 스크래핑)
사용법:
  python sector.py                    # 업종 현황 (기본)
  python sector.py --type theme       # 테마 현황
  python sector.py --no-chart
"""

import argparse
import sys
from datetime import datetime

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
    "Referer": "https://m.stock.naver.com/",
}

_TYPE_LABEL = {"upjong": "업종", "theme": "테마"}

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

    now = datetime.today().strftime("%Y-%m-%d %H:%M")
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

def plot(df: pd.DataFrame, type_label: str, show: bool = True) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        if show:
            fig.show()
        return fig

    has_chg   = "등락률" in df.columns and df["등락률"].notna().any()
    has_size  = "종목수" in df.columns and df["종목수"].notna().any()
    has_updn  = "상승수" in df.columns and df["상승수"].notna().any()

    # ── 서브플롯 구성 (트리맵 | 수평 바) ─────────────────────────────────────
    treemap_title = (f"{type_label} 히트맵  (크기: 종목수 · 색: 등락률)"
                     if has_size else f"{type_label} 현황")
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.46, 0.54],
        horizontal_spacing=0.22,   # y축 한글 레이블이 히트맵과 겹치지 않도록
        subplot_titles=(treemap_title, f"{type_label}별 등락률 (%)"),
        specs=[[{"type": "treemap"}, {"type": "bar"}]],
    )

    # ① 트리맵 (종목수를 크기로, 등락률을 색으로)
    if has_chg:
        tm = df.dropna(subset=["등락률"]).copy()
        # 크기: 종목수 있으면 사용, 없으면 균등
        sizes = (tm["종목수"].clip(lower=1) if has_size
                 else pd.Series([1] * len(tm), index=tm.index))

        # 호버 텍스트 추가 정보
        if has_updn:
            hover_extra = [
                f"상승: {int(row.get('상승수', 0))} / 하락: {int(row.get('하락수', 0))}"
                for _, row in tm.iterrows()
            ]
            customdata = list(zip(tm["등락률"], hover_extra))
            hovertemplate = (
                "<b>%{label}</b><br>"
                "등락률: %{customdata[0]:+.2f}%<br>"
                "%{customdata[1]}<extra></extra>"
            )
        else:
            customdata = tm["등락률"].values
            hovertemplate = (
                "<b>%{label}</b><br>"
                "등락률: %{customdata:+.2f}%<extra></extra>"
            )

        fig.add_trace(go.Treemap(
            labels=tm["섹터명"].astype(str),
            parents=[""] * len(tm),
            values=sizes,
            customdata=customdata,
            texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%" if has_updn
                         else "<b>%{label}</b><br>%{customdata:+.2f}%",
            marker=dict(
                colors=tm["등락률"],
                colorscale=[
                    [0.0, "#457b9d"],   # 파랑 (하락)
                    [0.5, "#1e1e2e"],   # 중립
                    [1.0, "#e63946"],   # 빨강 (상승)
                ],
                cmid=0,
                showscale=True,
                colorbar=dict(title="등락률(%)", x=0.50, len=0.85,
                              tickfont=dict(color="white")),
            ),
            hovertemplate=hovertemplate,
        ), row=1, col=1)

    # ② 수평 바차트 (등락률 오름차순)
    if has_chg:
        bar = df.dropna(subset=["등락률"]).sort_values("등락률", ascending=True)
        colors = ["#e63946" if v >= 0 else "#457b9d" for v in bar["등락률"]]

        abs_vals = bar["등락률"].abs()
        max_abs  = float(abs_vals.max()) if len(abs_vals) > 0 else 1.0

        # y축 표시용 레이블: 최대 11자 (넘치면 … 처리), 전체 이름은 hover로
        full_names  = bar["섹터명"].astype(str)
        short_names = [s[:11] + "…" if len(s) > 11 else s for s in full_names]

        # 바 트레이스
        fig.add_trace(go.Bar(
            x=bar["등락률"],
            y=short_names,
            orientation="h",
            marker_color=colors,
            name="등락률",
            customdata=full_names,
            hovertemplate="<b>%{customdata}</b><br>등락률: %{x:+.2f}%<extra></extra>",
        ), row=1, col=2)

        # 0 기준선
        if not bar.empty:
            fig.add_trace(go.Scatter(
                x=[0, 0],
                y=[short_names[0], short_names[-1]],
                mode="lines",
                line=dict(color="rgba(255,255,255,0.3)", dash="dash", width=1),
                showlegend=False,
                hoverinfo="skip",
            ), row=1, col=2)

        # x축 범위: 바 양쪽에 약간의 여유만 확보 (레이블 없으므로 호버로 확인)
        fig.update_xaxes(
            range=[-(max_abs * 1.12), max_abs * 1.12],
            row=1, col=2,
        )

    now = datetime.today().strftime("%Y-%m-%d %H:%M")
    n_rows = len(df)
    fig.update_layout(
        height=max(560, 70 + n_rows * 24),
        template="plotly_dark",
        title=dict(text=f"{type_label}별 시세 현황  —  {now}", font=dict(size=17)),
        margin=dict(t=80, b=40, l=10, r=20),
        showlegend=False,
    )
    fig.update_xaxes(title_text="등락률 (%)", row=1, col=2)
    fig.update_yaxes(tickfont=dict(size=9), row=1, col=2)

    if show:
        fig.show()
        print("[완료] 브라우저에서 차트를 확인하세요.")
    return fig


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
