"""
가상투자 포트폴리오 관리 모듈
데이터 저장: 클라우드(Supabase) 또는 로컬(portfolio.json)
- Streamlit secrets에 [supabase] 설정 시 → Supabase DB 사용
- 없으면 → 로컬 portfolio.json 사용 (개발 환경)
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORTFOLIO_FILE = Path(__file__).parent / "portfolio.json"

# ── 수수료 / 세금 ─────────────────────────────────────────────────────────────
KR_BUY_FEE  = 0.00015          # 매수 증권사 수수료 0.015%
KR_SELL_FEE = 0.00015          # 매도 증권사 수수료 0.015%
KR_SELL_TAX = 0.0023           # 증권거래세 0.23%
US_FEE_PER_SHARE = 0.0         # 미국 수수료 (간소화: 무료)


# ── 포트폴리오 I/O ────────────────────────────────────────────────────────────

def _default(capital: float) -> dict:
    return {
        "initial_capital": capital,
        "cash":            capital,
        "holdings":        {},      # "TICKER:market" → {ticker, market, name, quantity, avg_price}
        "transactions":    [],      # 최신 순
        "created_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_supabase():
    """
    Supabase 클라이언트 반환.
    Streamlit secrets에 [supabase] 설정이 없으면 None 반환.
    """
    try:
        import streamlit as st
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def load_portfolio() -> dict:
    """포트폴리오 로드 — Supabase 우선, 없으면 로컬 파일."""
    sb = _get_supabase()
    if sb:
        try:
            res = sb.table("portfolio").select("data").eq("id", "default").execute()
            if res.data:
                return res.data[0]["data"]
            # DB에 행이 없으면 기본값 생성
            p = _default(10_000_000)
            sb.table("portfolio").insert({"id": "default", "data": p}).execute()
            return p
        except Exception:
            pass

    # 로컬 파일 (개발 환경 fallback)
    if PORTFOLIO_FILE.exists():
        try:
            return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    p = _default(10_000_000)
    save_portfolio(p)
    return p


def save_portfolio(p: dict) -> None:
    """포트폴리오 저장 — Supabase 우선, 없으면 로컬 파일."""
    sb = _get_supabase()
    if sb:
        try:
            sb.table("portfolio").upsert({"id": "default", "data": p}).execute()
            return
        except Exception:
            pass

    # 로컬 파일 (개발 환경 fallback)
    PORTFOLIO_FILE.write_text(
        json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def reset_portfolio(capital: float) -> dict:
    p = _default(capital)
    save_portfolio(p)
    return p


# ── 시세 조회 ─────────────────────────────────────────────────────────────────

def get_current_price(ticker: str, market: str) -> float | None:
    """현재가 조회 (국내: pykrx → yfinance .KS fallback, 미국: yfinance)"""
    import yfinance as yf

    if market.lower() == "kr":
        # 1차: pykrx (로컬 환경)
        try:
            from pykrx import stock as krx
            for i in range(7):
                d = (datetime.today() - timedelta(days=i)).strftime("%Y%m%d")
                df = krx.get_market_ohlcv_by_date(d, d, ticker)
                if not df.empty:
                    col = "종가" if "종가" in df.columns else df.columns[-2]
                    return float(df[col].iloc[-1])
        except Exception:
            pass
        # 2차: yfinance .KS / .KQ (클라우드 환경)
        for suffix in [".KS", ".KQ"]:
            try:
                hist = yf.Ticker(f"{ticker}{suffix}").history(period="5d")
                if not hist.empty:
                    return float(hist["Close"].iloc[-1])
            except Exception:
                continue
    else:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return None


def get_stock_name(ticker: str, market: str) -> str:
    try:
        if market.lower() == "kr":
            from pykrx import stock as krx
            n = krx.get_market_ticker_name(ticker)
            return n if n else ticker
        else:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker


# ── 매수 / 매도 ───────────────────────────────────────────────────────────────

def buy(p: dict, ticker: str, market: str,
        quantity: int, price: float, name: str = "") -> tuple[bool, str]:
    """매수 처리. 반환: (성공, 메시지)"""
    market = market.lower()
    fee    = round(price * quantity * KR_BUY_FEE) if market == "kr" else 0
    total  = price * quantity + fee

    if total > p["cash"]:
        return False, f"잔고 부족 — 필요 {total:,.0f}원 / 보유 현금 {p['cash']:,.0f}원"

    if not name:
        name = get_stock_name(ticker.upper(), market)

    key = f"{ticker.upper()}:{market}"
    if key in p["holdings"]:
        h = p["holdings"][key]
        new_qty  = h["quantity"] + quantity
        h["avg_price"] = round(
            (h["avg_price"] * h["quantity"] + price * quantity) / new_qty, 4
        )
        h["quantity"] = new_qty
    else:
        p["holdings"][key] = {
            "ticker":    ticker.upper(),
            "market":    market,
            "name":      name,
            "quantity":  quantity,
            "avg_price": price,
        }

    p["cash"] -= total
    p["transactions"].insert(0, {
        "date":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action":   "BUY",
        "ticker":   ticker.upper(),
        "market":   market.upper(),
        "name":     name,
        "price":    price,
        "quantity": quantity,
        "amount":   price * quantity,
        "fee":      fee,
        "pnl":      None,
    })
    return True, f"매수 완료: {name} {quantity:,}주 @ {price:,.0f}원 (수수료 {fee:,.0f}원)"


def sell(p: dict, ticker: str, market: str,
         quantity: int, price: float) -> tuple[bool, str]:
    """매도 처리. 반환: (성공, 메시지)"""
    market = market.lower()
    key = f"{ticker.upper()}:{market}"

    if key not in p["holdings"]:
        return False, "보유하지 않은 종목입니다."

    h = p["holdings"][key]
    if h["quantity"] < quantity:
        return False, f"수량 부족 — 보유 {h['quantity']:,}주"

    fee = round(price * quantity * (KR_SELL_FEE + KR_SELL_TAX)) if market == "kr" else 0
    net = price * quantity - fee
    pnl = round((price - h["avg_price"]) * quantity - fee)

    h["quantity"] -= quantity
    name = h["name"]
    if h["quantity"] == 0:
        del p["holdings"][key]

    p["cash"] += net
    p["transactions"].insert(0, {
        "date":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action":   "SELL",
        "ticker":   ticker.upper(),
        "market":   market.upper(),
        "name":     name,
        "price":    price,
        "quantity": quantity,
        "amount":   price * quantity,
        "fee":      fee,
        "pnl":      pnl,
    })
    sign = "+" if pnl >= 0 else ""
    return True, f"매도 완료: {name} {quantity:,}주 @ {price:,.0f}원 (손익 {sign}{pnl:,.0f}원)"


# ── 평가 ──────────────────────────────────────────────────────────────────────

def evaluate(p: dict, price_override: dict | None = None) -> dict:
    """
    포트폴리오 현재 평가.
    price_override: {"TICKER:market": price} — 외부에서 미리 조회한 가격을 주입
    """
    rows = []
    holdings_value = 0.0

    for key, h in p["holdings"].items():
        if price_override and key in price_override:
            cur = price_override[key]
        else:
            cur = get_current_price(h["ticker"], h["market"])
        if cur is None:
            cur = h["avg_price"]   # 조회 실패 시 평단가로 대체

        val     = cur * h["quantity"]
        pnl     = (cur - h["avg_price"]) * h["quantity"]
        pnl_pct = (cur / h["avg_price"] - 1) * 100 if h["avg_price"] else 0
        holdings_value += val
        rows.append({
            "종목명":   h["name"],
            "티커":     h["ticker"],
            "시장":     h["market"].upper(),
            "수량":     h["quantity"],
            "평균단가": h["avg_price"],
            "현재가":   cur,
            "평가금액": val,
            "손익":     pnl,
            "수익률":   pnl_pct,
        })

    total_value   = p["cash"] + holdings_value
    total_pnl     = total_value - p["initial_capital"]
    total_pnl_pct = (total_pnl / p["initial_capital"] * 100
                     if p["initial_capital"] else 0)

    return {
        "rows":            rows,
        "cash":            p["cash"],
        "holdings_value":  holdings_value,
        "total_value":     total_value,
        "total_pnl":       total_pnl,
        "total_pnl_pct":   total_pnl_pct,
        "initial_capital": p["initial_capital"],
    }


# ── 차트 ──────────────────────────────────────────────────────────────────────

def plot_portfolio(ev: dict, show: bool = True) -> go.Figure:
    """자산 구성 파이 + 종목별 수익률 바"""
    rows = ev["rows"]

    if not rows:
        fig = go.Figure()
        fig.add_annotation(
            text="보유 종목 없음<br><sub>종목을 매수하면 차트가 표시됩니다</sub>",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=16, color="#718096"),
        )
        fig.update_layout(template="plotly_dark", height=320,
                          margin=dict(t=20, b=20))
        if show:
            fig.show()
        return fig

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("자산 구성", "종목별 수익률 (%)"),
        specs=[[{"type": "pie"}, {"type": "bar"}]],
        column_widths=[0.42, 0.58],
        horizontal_spacing=0.12,
    )

    # 파이: 현금 + 종목 평가금액
    labels = ["현금"] + [r["종목명"] for r in rows]
    values = [ev["cash"]] + [r["평가금액"] for r in rows]
    fig.add_trace(go.Pie(
        labels=labels, values=values,
        hole=0.45,
        hovertemplate="%{label}<br>%{value:,.0f}원 (%{percent})<extra></extra>",
        textinfo="label+percent",
        insidetextorientation="radial",
    ), row=1, col=1)

    # 바: 종목별 수익률
    names    = [r["종목명"] for r in rows]
    pnl_pcts = [r["수익률"] for r in rows]
    bar_colors = ["#e63946" if v >= 0 else "#457b9d" for v in pnl_pcts]
    fig.add_trace(go.Bar(
        x=names, y=pnl_pcts,
        marker_color=bar_colors,
        text=[f"{v:+.2f}%" for v in pnl_pcts],
        textposition="outside",
        hovertemplate="%{x}<br>수익률: %{y:+.2f}%<extra></extra>",
    ), row=1, col=2)

    fig.update_layout(
        height=400,
        template="plotly_dark",
        margin=dict(t=50, b=30, l=10, r=30),
        showlegend=False,
    )
    fig.update_yaxes(title_text="수익률 (%)", row=1, col=2)

    if show:
        fig.show()
    return fig


# ── 종목 검색 ─────────────────────────────────────────────────────────────────

_KR_DB_PATH = Path(__file__).parent / "kr_tickers.json"
_kr_db_cache: dict | None = None   # 메모리 캐시 (프로세스 생존 중 유지)


def _load_kr_db() -> dict:
    """kr_tickers.json 로드 (메모리 캐시 적용)."""
    global _kr_db_cache
    if _kr_db_cache is None:
        if _KR_DB_PATH.exists():
            try:
                _kr_db_cache = json.loads(_KR_DB_PATH.read_text(encoding="utf-8"))
            except Exception:
                _kr_db_cache = {}
        else:
            _kr_db_cache = {}
    return _kr_db_cache


def rebuild_kr_ticker_db() -> tuple[bool, str]:
    """
    KOSPI + KOSDAQ 전체 종목 DB를 네이버 금융에서 재구축하여 kr_tickers.json 저장.
    반환: (성공, 메시지)
    """
    global _kr_db_cache
    try:
        import requests as _req
        import re as _re
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://finance.naver.com/",
        }
        url = "https://finance.naver.com/sise/sise_market_sum.naver"
        db: dict = {}

        for market, sosok, max_pages in [("KOSPI", 0, 50), ("KOSDAQ", 1, 37)]:
            for pg in range(1, max_pages + 1):
                try:
                    r = _req.get(url, params={"sosok": sosok, "page": pg},
                                 headers=headers, timeout=10)
                    text = r.content.decode("euc-kr", errors="replace")
                    matches = _re.findall(r'code=(\d{6})[^>]*>([^<]+)</a>', text)
                    added = 0
                    for code, name in matches:
                        name = name.strip()
                        if name and code not in db:
                            db[code] = {"name": name, "market": market}
                            added += 1
                    if added == 0:   # 빈 페이지 → 더 이상 없음
                        break
                except Exception:
                    continue

        if not db:
            return False, "종목 데이터를 가져오지 못했습니다."

        _KR_DB_PATH.write_text(
            json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _kr_db_cache = db   # 메모리 캐시 갱신
        n_kospi  = sum(1 for v in db.values() if v["market"] == "KOSPI")
        n_kosdaq = sum(1 for v in db.values() if v["market"] == "KOSDAQ")
        return True, f"종목 DB 갱신 완료: KOSPI {n_kospi}개, KOSDAQ {n_kosdaq}개"
    except Exception as e:
        return False, f"오류: {e}"


def search_kr_stocks(query: str) -> list:
    """
    로컬 kr_tickers.json DB에서 국내 종목 검색 (종목명 / 코드 부분 일치).
    반환: [{"code": "005930", "name": "삼성전자", "market": "KOSPI"}, ...]
    """
    db = _load_kr_db()
    q  = query.strip()
    if not q:
        return []

    results = []
    q_lower = q.lower()
    for code, info in db.items():
        name = info.get("name", "")
        if q in name or q_lower in code:
            results.append({
                "code":   code,
                "name":   name,
                "market": info.get("market", "KR"),
            })
        if len(results) >= 20:
            break
    return results


def search_us_stocks(query: str) -> list:
    """
    Yahoo Finance 검색 API로 미국 종목 검색.
    반환: [{"ticker": "AAPL", "name": "Apple Inc.", "type": "EQUITY", "exchange": "NASDAQ"}, ...]
    """
    try:
        import requests as _req
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q":               query,
            "lang":            "en-US",
            "region":          "US",
            "quotesCount":     20,
            "newsCount":       0,
            "enableFuzzyQuery": "false",
        }
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = _req.get(url, params=params, headers=headers, timeout=8)
        data = r.json()

        results = []
        for q in data.get("quotes", []):
            qt = q.get("quoteType", "")
            if qt not in ("EQUITY", "ETF"):
                continue
            ticker = q.get("symbol", "")
            name   = q.get("shortname") or q.get("longname") or ticker
            exch   = q.get("exchDisp", "")
            results.append({"ticker": ticker, "name": name, "type": qt, "exchange": exch})
        return results[:20]
    except Exception:
        return []
