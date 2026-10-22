"""
지수 · 환율 · 시장지표 — 현재 값은 네이버 모바일 증권 API(실시간), 추이는 yfinance
사용법:
  python market_index.py          # 전체 현재 값 출력
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
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

# 소스 구분
#   kr    : 국내 지수   m.stock.naver.com/api/index/{code}/basic
#   world : 해외 지수   api.stock.naver.com/index/{code}/basic
#   mi    : 시장지표    m.stock.naver.com/front-api/marketIndex/productDetail (환율·금리·원자재)
# yf: 추이 차트용 yfinance 심볼 (None이면 차트 미지원), yf_mul: 단위 보정 배수
# dec: 표시 소수점 자릿수
ITEMS = {
    # 국내 지수
    "KOSPI":  dict(group="kr", name="코스피",     src="kr", code="KOSPI",  yf="^KS11", dec=2),
    "KOSDAQ": dict(group="kr", name="코스닥",     src="kr", code="KOSDAQ", yf="^KQ11", dec=2),
    "KPI200": dict(group="kr", name="코스피 200", src="kr", code="KPI200", yf=None,    dec=2),
    # 환율 (원화 기준)
    "USDKRW": dict(group="fx", name="원/달러",       src="mi", cat="exchange", code="FX_USDKRW",
                   yf="KRW=X", dec=2, unit="원"),
    "JPYKRW": dict(group="fx", name="원/엔 (100엔)", src="mi", cat="exchange", code="FX_JPYKRW",
                   yf="JPYKRW=X", yf_mul=100, dec=2, unit="원"),   # yfinance는 1엔 기준
    "EURKRW": dict(group="fx", name="원/유로",       src="mi", cat="exchange", code="FX_EURKRW",
                   yf="EURKRW=X", dec=2, unit="원"),
    "CNYKRW": dict(group="fx", name="원/위안",       src="mi", cat="exchange", code="FX_CNYKRW",
                   yf=None, dec=2, unit="원"),
    # 해외 지수
    "DJI":  dict(group="world", name="다우존스",          src="world", code=".DJI",  yf="^DJI",  dec=2),
    "SPX":  dict(group="world", name="S&P 500",           src="world", code=".INX",  yf="^GSPC", dec=2),
    "IXIC": dict(group="world", name="나스닥",            src="world", code=".IXIC", yf="^IXIC", dec=2),
    "SOX":  dict(group="world", name="필라델피아 반도체", src="world", code=".SOX",  yf="^SOX",  dec=2),
    # 금리 · 달러
    "US10Y": dict(group="rates", name="미국채 10년", src="mi", cat="bond",     code="US10YT=RR",
                  yf="^TNX", dec=3, unit="%"),
    "KR3Y":  dict(group="rates", name="국고채 3년",  src="mi", cat="bond",     code="KR3YT=RR",
                  yf=None, dec=3, unit="%"),
    "DXY":   dict(group="rates", name="달러인덱스",  src="mi", cat="exchange", code=".DXY",
                  yf="DX-Y.NYB", dec=2),
    # 원자재 · 심리
    "WTI":   dict(group="commod", name="WTI 원유",    src="mi", cat="energy",   code="CLcv1",
                  yf="CL=F", dec=2, unit="$"),
    "GOLD":  dict(group="commod", name="국제 금",     src="mi", cat="metals",   code="GCcv1",
                  yf="GC=F", dec=2, unit="$"),
    "VIX":   dict(group="commod", name="VIX 공포지수", src="world", code=".VIX", yf="^VIX", dec=2),
}

GROUPS = {   # 그룹당 3~4개 → 카드가 한 줄에 고르게 배치됨
    "kr":     "🏠 국내 지수",   # 국기 이모지는 Windows에서 'KR' 글자로 보여 사용 안 함
    "fx":     "💱 환율",
    "world":  "🌎 해외 지수",
    "rates":  "🏦 금리 · 달러",
    "commod": "🛢️ 원자재 · 공포지수",
}


# ── 현재 값 (네이버) ───────────────────────────────────────────────────────────

def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        return float("nan")


def _get(url: str, params: dict = None) -> dict:
    r = requests.get(url, headers=_HEADERS, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_quote(key: str) -> dict | None:
    """한 항목의 현재 값. 실패 시 None."""
    it = ITEMS[key]
    try:
        if it["src"] == "kr":
            js = _get(f"https://m.stock.naver.com/api/index/{it['code']}/basic")
            change = js.get("compareToPreviousClosePrice")
        elif it["src"] == "world":
            js = _get(f"https://api.stock.naver.com/index/{it['code']}/basic")
            change = js.get("compareToPreviousClosePrice")
        else:
            js = _get("https://m.stock.naver.com/front-api/marketIndex/productDetail",
                      {"category": it["cat"], "reutersCode": it["code"]}).get("result") or {}
            change = js.get("fluctuations")
    except Exception:
        return None

    price = _num(js.get("closePrice"))
    if price != price:          # NaN → 실패로 간주
        return None
    return {
        "key":    key,
        "name":   it["name"],
        "group":  it["group"],
        "price":  price,
        "change": _num(change),
        "pct":    _num(js.get("fluctuationsRatio")),
        "status": js.get("marketStatus") or "",
        "time":   js.get("localTradedAt") or "",
        "delay":  js.get("delayTimeName") or "",
        "dec":    it.get("dec", 2),
        "unit":   it.get("unit", ""),
    }


def fetch_quotes(keys=None) -> dict:
    """여러 항목을 병렬로 조회 → {key: quote}. 실패한 항목은 빠짐."""
    keys = list(keys or ITEMS)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch_quote, keys))
    return {k: q for k, q in zip(keys, results) if q}


# ── 추이 (yfinance) ───────────────────────────────────────────────────────────

PERIODS = {   # 표시명 → (yfinance period, interval)
    "오늘":   ("1d",  "5m"),
    "1개월":  ("1mo", "1d"),
    "3개월":  ("3mo", "1d"),
    "6개월":  ("6mo", "1d"),
    "1년":    ("1y",  "1d"),
    "3년":    ("3y",  "1wk"),
}


def fetch_history(key: str, period: str = "3개월") -> pd.Series:
    """종가 추이 (index=시각). 실패/미지원이면 빈 Series."""
    it = ITEMS.get(key, {})
    sym = it.get("yf")
    if not sym:
        return pd.Series(dtype=float)
    yf_period, interval = PERIODS.get(period, ("3mo", "1d"))
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period=yf_period, interval=interval)
    except Exception:
        return pd.Series(dtype=float)
    if h is None or h.empty or "Close" not in h:
        return pd.Series(dtype=float)
    s = h["Close"].dropna() * it.get("yf_mul", 1)   # 장중 미완성 행(NaN) 제거
    return s


# ── 표시용 헬퍼 ───────────────────────────────────────────────────────────────

_STATUS = {"OPEN": "장중", "CLOSE": "마감", "PREOPEN": "개장 전"}


def describe_time(q: dict) -> str:
    """'장중 · 14:02' / '마감 · 10/21 16:31 현지' / '10분 지연' 같은 보조 문구."""
    parts = []
    st_ = _STATUS.get(q.get("status", ""), "")
    if st_:
        parts.append(st_)
    t = q.get("time", "")
    try:
        dt = datetime.fromisoformat(t)
        is_kst = dt.utcoffset() is not None and dt.utcoffset().total_seconds() == 9 * 3600
        if is_kst:
            today = datetime.now(dt.tzinfo).date()
            parts.append(dt.strftime("%H:%M") if dt.date() == today else dt.strftime("%m/%d %H:%M"))
        else:
            parts.append(dt.strftime("%m/%d %H:%M") + " 현지")
    except Exception:
        pass
    d = q.get("delay", "")
    if d and d != "실시간":
        parts.append(d)
    return " · ".join(parts)


def main() -> None:
    quotes = fetch_quotes()
    for g, title in GROUPS.items():
        print(f"\n[{title}]")
        for k, it in ITEMS.items():
            if it["group"] != g:
                continue
            q = quotes.get(k)
            if not q:
                print(f"  {it['name']:<14} (조회 실패)")
                continue
            print(f"  {q['name']:<14} {q['price']:>12,.{q['dec']}f}  "
                  f"{q['change']:>+10,.{q['dec']}f}  ({q['pct']:+.2f}%)  {describe_time(q)}")


if __name__ == "__main__":
    main()
