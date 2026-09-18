"""
종목 뉴스 수집 모듈
1. 네이버 모바일 증권 종목별 뉴스 API (링크 포함)
2. 네이버 뉴스 검색 API (Naver API 키 있을 때)
3. 감성 분석 (긍정/부정 키워드 기반)
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 네이버 모바일 증권 종목 뉴스 API
# (2026-09 개편: finance.naver.com 종목뉴스가 stock.naver.com SPA로 이전되어
#  HTML 스크래핑이 깨짐 → 아래 JSON API 사용)
_STOCK_NEWS_API = "https://m.stock.naver.com/api/news/stock/{code}"

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(t: str) -> str:
    return html.unescape(_TAG_RE.sub("", t or "")).strip()


def _fmt_datetime(s) -> str:
    """네이버 datetime(YYYYMMDDHHMM) → 'YYYY.MM.DD HH:MM'."""
    s = str(s)
    if len(s) >= 12:
        return f"{s[0:4]}.{s[4:6]}.{s[6:8]} {s[8:10]}:{s[10:12]}"
    if len(s) >= 8:
        return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"
    return s

# ── 감성 분석 키워드 ───────────────────────────────────────────────────────────

_POS_WORDS = [
    "상승", "급등", "신고가", "호재", "계약", "수주", "흑자", "성장", "돌파",
    "강세", "매수", "증가", "반등", "개선", "회복", "확대", "기대", "목표가 상향",
    "배당", "영업이익 증가", "어닝서프라이즈", "최대", "최고", "혁신", "수출 증가",
    "협약", "투자", "신제품", "상향", "호실적", "흑자전환", "강력매수",
]
_NEG_WORDS = [
    "하락", "급락", "신저가", "악재", "적자", "손실", "부진", "우려", "리스크",
    "하향", "매도", "감소", "폭락", "위기", "하락세", "악화", "경고", "목표가 하향",
    "영업이익 감소", "어닝쇼크", "최저", "최악", "적자전환", "피해", "논란",
    "실망", "침체", "취소", "파산", "구조조정", "강력매도",
]


def analyze_sentiment(title: str) -> tuple[str, int]:
    """
    제목에서 감성 분석.
    Returns: ('positive'|'negative'|'neutral', score)
    score: 양수=긍정, 음수=부정, 0=중립
    """
    t = title.lower()
    pos = sum(1 for w in _POS_WORDS if w in t)
    neg = sum(1 for w in _NEG_WORDS if w in t)
    score = pos - neg
    if score > 0:
        return "positive", score
    elif score < 0:
        return "negative", score
    return "neutral", 0


# ── 네이버 금융 종목 뉴스 스크래핑 ───────────────────────────────────────────────

def fetch_naver_stock_news(ticker: str, max_items: int = 20) -> list[dict]:
    """
    네이버 모바일 증권 종목별 뉴스 API.
    https://m.stock.naver.com/api/news/stock/005930

    응답은 [{total, items:[...]}, ...] (관련기사 묶음). 이를 평탄화한다.
    Returns list of dicts: {title, url, press, date, description, sentiment, sentiment_score}
    """
    results: list[dict] = []
    try:
        resp = requests.get(_STOCK_NEWS_API.format(code=ticker), headers=_HEADERS,
                            params={"pageSize": max_items}, timeout=8)
        resp.raise_for_status()
        groups = resp.json()
    except Exception:
        return results

    seen_titles: set[str] = set()
    for grp in (groups if isinstance(groups, list) else []):
        for item in (grp.get("items", []) if isinstance(grp, dict) else []):
            title = _clean(item.get("title") or item.get("titleFull") or "")
            if not title or len(title) < 5 or title in seen_titles:
                continue
            seen_titles.add(title)

            sentiment, score = analyze_sentiment(title)
            results.append({
                "title":           title,
                "url":             item.get("mobileNewsUrl", ""),
                "press":           item.get("officeName", ""),
                "date":            _fmt_datetime(item.get("datetime", "")),
                "description":     _clean(item.get("body", "")),
                "sentiment":       sentiment,
                "sentiment_score": score,
            })
            if len(results) >= max_items:
                return results

    return results


# ── 네이버 뉴스 검색 API ─────────────────────────────────────────────────────

_NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"


def fetch_naver_api_news(
    query: str,
    client_id: str,
    client_secret: str,
    max_items: int = 20,
) -> list[dict]:
    """
    네이버 뉴스 검색 API.
    종목명/키워드로 검색 (국내·미국 주식 모두 지원).

    Returns list of dicts: {title, url, press, date, description, sentiment, sentiment_score}
    """
    params = {
        "query":   query,
        "display": min(max_items, 100),
        "sort":    "date",
    }
    headers = {
        "X-Naver-Client-Id":     client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    try:
        resp = requests.get(_NAVER_SEARCH_URL, params=params,
                            headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results = []
    tag_re  = re.compile(r"<[^>]+>")   # HTML 태그 제거

    for item in data.get("items", []):
        title = tag_re.sub("", item.get("title", "")).strip()
        desc  = tag_re.sub("", item.get("description", "")).strip()
        url   = item.get("link") or item.get("originallink", "")
        press = item.get("channelTitle", "")

        # 날짜 파싱: "Thu, 05 Jun 2026 10:30:00 +0900"
        raw_date = item.get("pubDate", "")
        try:
            dt    = datetime.strptime(raw_date, "%a, %d %b %Y %H:%M:%S %z")
            date  = dt.strftime("%Y.%m.%d %H:%M")
        except Exception:
            date  = raw_date[:16]

        if not title:
            continue

        sentiment, score = analyze_sentiment(title)
        results.append({
            "title":           title,
            "url":             url,
            "press":           press,
            "date":            date,
            "description":     desc,
            "sentiment":       sentiment,
            "sentiment_score": score,
        })

    return results


# ── 통합 함수 ─────────────────────────────────────────────────────────────────

def fetch_news(
    ticker: str,
    corp_name: str = "",
    is_kr: bool = True,
    naver_id: str = "",
    naver_secret: str = "",
    max_items: int = 20,
) -> tuple[list[dict], str]:
    """
    종목 뉴스 통합 수집.
    우선순위: 네이버 금융 스크래핑(국내) → 네이버 API → 빈 리스트

    Returns: (news_list, source_label)
    """
    # 국내 종목: 네이버 금융 직접 스크래핑
    if is_kr:
        items = fetch_naver_stock_news(ticker, max_items)
        if items:
            return items, "네이버 금융"

    # 네이버 검색 API (국내·미국 모두 가능)
    if naver_id and naver_secret:
        query = corp_name or ticker
        items = fetch_naver_api_news(query, naver_id, naver_secret, max_items)
        if items:
            return items, "네이버 뉴스 API"

    return [], ""


# ── 감성 요약 ─────────────────────────────────────────────────────────────────

def sentiment_summary(news_list: list[dict]) -> dict:
    """뉴스 목록에서 감성 통계 집계."""
    pos = sum(1 for n in news_list if n["sentiment"] == "positive")
    neg = sum(1 for n in news_list if n["sentiment"] == "negative")
    neu = len(news_list) - pos - neg
    total = len(news_list) or 1

    overall_score = sum(n["sentiment_score"] for n in news_list)
    if overall_score > 2:   overall = "positive"
    elif overall_score < -2: overall = "negative"
    else:                    overall = "neutral"

    return {
        "positive":      pos,
        "negative":      neg,
        "neutral":       neu,
        "total":         len(news_list),
        "pos_pct":       round(pos / total * 100),
        "neg_pct":       round(neg / total * 100),
        "overall":       overall,
        "overall_score": overall_score,
    }
