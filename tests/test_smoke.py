# -*- coding: utf-8 -*-
"""
CI 스모크 테스트 — GitHub Actions에서 실행.

1) 모든 모듈/뷰 임포트 (문법·임포트 오류 감지, 결정적)
2) 핵심 로직 단위 테스트 (결정적)
3) 라이브 데이터 점검 (네이버/yfinance, 재시도) — 소스 개편/차단 감지

하나라도 실패하면 exit 1 → GitHub Actions가 실패로 표시하고 소유자에게 알림.
"""
import importlib
import io
import os
import sys
import time

# 저장소 루트를 경로·작업디렉터리로
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

FAIL = []


def check(name, fn, deterministic=False):
    tries = 1 if deterministic else 3
    for i in range(tries):
        try:
            fn()
            print(f"  [OK]   {name}", flush=True)
            return
        except Exception as e:
            if i < tries - 1:
                time.sleep(3)
                continue
            print(f"  [FAIL] {name}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            FAIL.append(name)


print("== 1. 모듈 임포트 (결정적) ==", flush=True)
MODULES = [
    "common", "analyzer", "ranking", "sector", "ownership", "sentiment",
    "news", "smart_money", "regime", "alt_data", "scanner", "backtester",
    "compare", "optimizer", "fundamental", "dart_screener",
    "virtual_portfolio", "ai_report",
    "views.market", "views.sectors", "views.market_sentiment", "views.stock",
    "views.company", "views.investors", "views.advanced", "views.backtest",
    "views.strategy_compare", "views.ma_optimizer", "views.watchlist_scanner",
    "views.dart", "views.buy_timing", "views.portfolio", "views.ai_assistant",
    "views.compare_stocks",
]
for m in MODULES:
    check(f"import {m}", (lambda mm=m: importlib.import_module(mm)), deterministic=True)

print("== 2. 핵심 로직 단위 테스트 (결정적) ==", flush=True)


def t_sanitize():
    from virtual_portfolio import sanitize_pid
    assert sanitize_pid("") == "default"
    assert sanitize_pid("Hong2026") == "hong2026"


check("sanitize_pid", t_sanitize, deterministic=True)


def t_perf():
    from virtual_portfolio import performance_stats
    p = {"transactions": [
        {"action": "SELL", "pnl": 5000}, {"action": "SELL", "pnl": -2000},
        {"action": "BUY", "pnl": None}]}
    s = performance_stats(p, {"rows": [{"손익": 1000}]})
    assert s["realized"] == 3000 and s["n_sell"] == 2 and s["n_buy"] == 1
    assert s["unrealized"] == 1000 and s["win_rate"] == 50.0


check("performance_stats", t_perf, deterministic=True)


def t_fallback():
    import pandas as pd
    import common
    assert not common._is_empty(pd.DataFrame({"x": [1]}))
    assert common._is_empty(pd.DataFrame())
    common._with_fallback("ci_test", pd.DataFrame({"x": [1]}))
    assert len(common._with_fallback("ci_test", pd.DataFrame())) == 1   # 폴백


check("_with_fallback 폴백", t_fallback, deterministic=True)

print("== 3. 라이브 데이터 (네이버/yfinance, 재시도) ==", flush=True)


def t_rankings():
    from ranking import fetch_rankings
    d = fetch_rankings("KOSPI")
    assert d and any((not v.empty) for v in d.values()), "시장현황 데이터 비어있음"


check("ranking.fetch_rankings(KOSPI)", t_rankings)


def t_sector():
    from sector import fetch_sector
    assert not fetch_sector("upjong").empty, "섹터 데이터 비어있음"


check("sector.fetch_sector(upjong)", t_sector)


def t_news():
    from sentiment import fetch_market_news
    assert len(fetch_market_news()) > 0, "시장 뉴스 비어있음"


check("sentiment.fetch_market_news", t_news)


def t_yf():
    from datetime import datetime, timedelta
    from analyzer import fetch_us
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    assert not fetch_us("AAPL", start, end).empty, "yfinance 데이터 비어있음"


check("analyzer.fetch_us(AAPL)", t_yf)

print(flush=True)
if FAIL:
    print(f"❌ 실패 {len(FAIL)}개: {FAIL}", flush=True)
    sys.exit(1)
print("✅ 전체 통과", flush=True)
