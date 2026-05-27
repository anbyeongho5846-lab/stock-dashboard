"""
KIS (한국투자증권) 모의투자 자동매매
사용법:
  python kis_trader.py balance              # 잔고 조회
  python kis_trader.py price 005930         # 현재가 조회
  python kis_trader.py buy  005930 10       # 시장가 매수 10주
  python kis_trader.py sell 005930 5        # 시장가 매도 5주
  python kis_trader.py auto                 # watchlist 기반 자동매매 1회 실행

사전 준비:
  1. https://apiportal.koreainvestment.com 에서 앱 등록 (모의투자)
  2. .env.example → .env 로 복사 후 키 값 입력
  3. pip install python-dotenv
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# .env 파일 로드 (없으면 환경변수만 사용)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import os

logging.getLogger("pykrx").setLevel(logging.ERROR)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 설정 ──────────────────────────────────────────────────────────────────────

BASE_URL = {
    "paper": "https://openapivts.koreainvestment.com:29443",
    "real":  "https://openapi.koreainvestment.com:9443",
}
TR_ID = {
    "paper": {"buy": "VTTC0802U", "sell": "VTTC0801U", "balance": "VTTC8434R"},
    "real":  {"buy": "TTTC0802U", "sell": "TTTC0801U", "balance": "TTTC8434R"},
}
TOKEN_CACHE = Path(__file__).parent / ".kis_token.json"


def _load_config() -> dict:
    app_key = os.getenv("KIS_APP_KEY", "")
    app_secret = os.getenv("KIS_APP_SECRET", "")
    account = os.getenv("KIS_ACCOUNT", "")
    mode = os.getenv("KIS_MODE", "paper").lower()

    missing = [k for k, v in [
        ("KIS_APP_KEY", app_key),
        ("KIS_APP_SECRET", app_secret),
        ("KIS_ACCOUNT", account),
    ] if not v or "입력" in v]

    if missing:
        print("[오류] .env 파일에 다음 항목이 설정되지 않았습니다:")
        for m in missing:
            print(f"        {m}")
        print("\n  .env.example 을 .env 로 복사 후 값을 입력하세요.")
        sys.exit(1)

    parts = account.replace("-", "")
    return {
        "app_key":    app_key,
        "app_secret": app_secret,
        "cano":       parts[:8],
        "acnt_prdt":  parts[8:] if len(parts) > 8 else "01",
        "mode":       mode,
        "base_url":   BASE_URL[mode],
        "tr":         TR_ID[mode],
    }


# ── 인증 ──────────────────────────────────────────────────────────────────────

def _get_token(cfg: dict) -> str:
    """토큰 캐시 사용, 만료 시 재발급."""
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        expire = datetime.fromisoformat(cached.get("expires", "2000-01-01"))
        if datetime.now() < expire:
            return cached["token"]

    resp = requests.post(
        f"{cfg['base_url']}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey":     cfg["app_key"],
            "appsecret":  cfg["app_secret"],
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]

    TOKEN_CACHE.write_text(json.dumps({
        "token":   token,
        "expires": (datetime.now() + timedelta(hours=23)).isoformat(),
    }))
    return token


def _headers(cfg: dict, tr_id: str) -> dict:
    return {
        "content-type":  "application/json; charset=utf-8",
        "authorization": f"Bearer {_get_token(cfg)}",
        "appkey":        cfg["app_key"],
        "appsecret":     cfg["app_secret"],
        "tr_id":         tr_id,
        "custtype":      "P",
    }


# ── API 호출 ──────────────────────────────────────────────────────────────────

def get_price(cfg: dict, ticker: str) -> dict:
    """현재가 조회."""
    resp = requests.get(
        f"{cfg['base_url']}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers=_headers(cfg, "FHKST01010100"),
        params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker},
        timeout=10,
    )
    resp.raise_for_status()
    out = resp.json().get("output", {})
    return {
        "ticker":     ticker,
        "price":      int(out.get("stck_prpr", 0)),
        "change":     int(out.get("prdy_vrss", 0)),
        "change_pct": float(out.get("prdy_ctrt", 0)),
        "volume":     int(out.get("acml_vol", 0)),
        "high":       int(out.get("stck_hgpr", 0)),
        "low":        int(out.get("stck_lwpr", 0)),
    }


def get_balance(cfg: dict) -> dict:
    """잔고 조회."""
    resp = requests.get(
        f"{cfg['base_url']}/uapi/domestic-stock/v1/trading/inquire-balance",
        headers=_headers(cfg, cfg["tr"]["balance"]),
        params={
            "CANO":            cfg["cano"],
            "ACNT_PRDT_CD":    cfg["acnt_prdt"],
            "AFHR_FLPR_YN":    "N",
            "OFL_YN":          "",
            "INQR_DVSN":       "02",
            "UNPR_DVSN":       "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN":       "01",
            "CTX_AREA_FK100":  "",
            "CTX_AREA_NK100":  "",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    holdings = []
    for item in data.get("output1", []):
        qty = int(item.get("hldg_qty", 0))
        if qty > 0:
            holdings.append({
                "ticker":   item.get("pdno", ""),
                "name":     item.get("prdt_name", ""),
                "qty":      qty,
                "avg_price": float(item.get("pchs_avg_pric", 0)),
                "cur_price": int(item.get("prpr", 0)),
                "pnl_pct":  float(item.get("evlu_pfls_rt", 0)),
                "pnl_amt":  int(item.get("evlu_pfls_amt", 0)),
            })

    summary = data.get("output2", [{}])[0] if data.get("output2") else {}
    return {
        "cash":         int(summary.get("dnca_tot_amt", 0)),
        "total_eval":   int(summary.get("tot_evlu_amt", 0)),
        "total_pnl":    int(summary.get("evlu_pfls_smtl_amt", 0)),
        "holdings":     holdings,
    }


def place_order(cfg: dict, ticker: str, side: str, qty: int, price: int = 0) -> dict:
    """주문 실행. price=0 이면 시장가."""
    tr_id = cfg["tr"][side]
    body = {
        "CANO":          cfg["cano"],
        "ACNT_PRDT_CD":  cfg["acnt_prdt"],
        "PDNO":          ticker,
        "ORD_DVSN":      "01" if price == 0 else "00",   # 01=시장가, 00=지정가
        "ORD_QTY":       str(qty),
        "ORD_UNPR":      "0" if price == 0 else str(price),
    }
    resp = requests.post(
        f"{cfg['base_url']}/uapi/domestic-stock/v1/trading/order-cash",
        headers=_headers(cfg, tr_id),
        json=body,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "success":   data.get("rt_cd") == "0",
        "order_no":  data.get("output", {}).get("ODNO", ""),
        "message":   data.get("msg1", ""),
        "raw":       data,
    }


# ── 자동매매 로직 ─────────────────────────────────────────────────────────────

def auto_trade(cfg: dict, dry_run: bool = True) -> None:
    """
    watchlist 스캔 → 신호 기반 자동 매매.
    dry_run=True 면 실제 주문 없이 로그만 출력.
    """
    from scanner import load_watchlist, scan, DEFAULT_WATCHLIST

    print(f"\n[자동매매] {'=== 시뮬레이션 모드 ===' if dry_run else '=== 실행 모드 ==='}")
    print(f"[자동매매] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 잔고 조회
    bal = get_balance(cfg)
    cash = bal["cash"]
    holdings_map = {h["ticker"]: h for h in bal["holdings"]}

    print(f"[잔고] 현금 {cash:,}원  |  보유 종목 {len(holdings_map)}개  |  총평가 {bal['total_eval']:,}원")

    # 스캔 (국내 종목만 자동매매)
    watchlist = [(t, m) for t, m in load_watchlist(DEFAULT_WATCHLIST) if m == "kr"]
    if not watchlist:
        print("[오류] watchlist.txt에 국내(kr) 종목이 없습니다.")
        return

    results = scan(watchlist, days=120)

    buy_budget = cash * 0.1       # 종목당 현금의 10% 투입
    orders: list[dict] = []

    for r in results:
        ticker  = r["ticker"]
        opinion = r["opinion"]

        # 매수 조건: 강매수/매수 신호 + 미보유
        if opinion in ("강매수", "매수") and ticker not in holdings_map:
            if buy_budget < 10_000:
                print(f"[스킵] {ticker} — 예산 부족 ({buy_budget:,.0f}원)")
                continue
            price_info = get_price(cfg, ticker)
            cur_price  = price_info["price"]
            if cur_price <= 0:
                continue
            qty = max(1, int(buy_budget / cur_price))
            orders.append({"side": "buy",  "ticker": ticker, "qty": qty,
                           "price": cur_price, "reason": opinion})

        # 매도 조건: 강매도/매도 신호 + 보유 중
        elif opinion in ("강매도", "매도") and ticker in holdings_map:
            qty = holdings_map[ticker]["qty"]
            orders.append({"side": "sell", "ticker": ticker, "qty": qty,
                           "price": holdings_map[ticker]["cur_price"], "reason": opinion})

    if not orders:
        print("[자동매매] 실행할 신호가 없습니다.")
        return

    print(f"\n  {'액션':<5} {'종목':<12} {'수량':>5} {'단가':>10} {'금액':>12}  이유")
    print(f"  {'-'*55}")
    for o in orders:
        amt = o["qty"] * o["price"]
        print(f"  {o['side'].upper():<5} {o['ticker']:<12} {o['qty']:>5}주 {o['price']:>10,}원 {amt:>12,}원  [{o['reason']}]")

    if dry_run:
        print("\n  [시뮬레이션] 실제 주문은 실행되지 않았습니다.")
        print("  실제 주문하려면: python kis_trader.py auto --execute")
        return

    # 실제 주문 실행
    for o in orders:
        result = place_order(cfg, o["ticker"], o["side"], o["qty"])
        status = "성공" if result["success"] else "실패"
        print(f"  [{status}] {o['side'].upper()} {o['ticker']} {o['qty']}주"
              f"  주문번호: {result['order_no']}  {result['message']}")
        time.sleep(0.3)   # API 호출 간격


# ── CLI 출력 도우미 ──────────────────────────────────────────────────────────

def cmd_balance(cfg: dict) -> None:
    bal = get_balance(cfg)
    print(f"\n{'='*55}")
    print(f"  계좌 잔고  [{cfg['mode'].upper()}]")
    print(f"{'='*55}")
    print(f"  현금        : {bal['cash']:>15,}원")
    print(f"  총 평가액   : {bal['total_eval']:>15,}원")
    sign = "+" if bal["total_pnl"] >= 0 else ""
    print(f"  평가 손익   : {sign}{bal['total_pnl']:>14,}원")
    if bal["holdings"]:
        print(f"\n  {'종목':<10} {'종목명':<16} {'수량':>5} {'평균가':>9} {'현재가':>9} {'손익률':>7} {'손익액':>12}")
        print(f"  {'-'*73}")
        for h in bal["holdings"]:
            pnl_str = f"{h['pnl_pct']:+.1f}%"
            print(f"  {h['ticker']:<10} {h['name']:<16} {h['qty']:>5}주"
                  f" {h['avg_price']:>9,.0f} {h['cur_price']:>9,} {pnl_str:>7} {h['pnl_amt']:>12,}원")
    else:
        print("  보유 종목 없음")
    print(f"{'='*55}\n")


def cmd_price(cfg: dict, ticker: str) -> None:
    p = get_price(cfg, ticker)
    sign = "▲" if p["change"] >= 0 else "▼"
    print(f"\n  {ticker}  현재가: {p['price']:,}원  "
          f"{sign} {abs(p['change']):,} ({abs(p['change_pct']):.2f}%)  "
          f"거래량: {p['volume']:,}\n")


def cmd_order(cfg: dict, side: str, ticker: str, qty: int) -> None:
    print(f"\n  {'매수' if side == 'buy' else '매도'} 주문: {ticker}  {qty}주 (시장가)")
    result = place_order(cfg, ticker, side, qty)
    if result["success"]:
        print(f"  [성공] 주문번호: {result['order_no']}")
    else:
        print(f"  [실패] {result['message']}")
    print()


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="KIS 모의투자 자동매매")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("balance", help="잔고 조회")

    p_price = sub.add_parser("price", help="현재가 조회")
    p_price.add_argument("ticker")

    p_buy = sub.add_parser("buy", help="시장가 매수")
    p_buy.add_argument("ticker")
    p_buy.add_argument("qty", type=int)

    p_sell = sub.add_parser("sell", help="시장가 매도")
    p_sell.add_argument("ticker")
    p_sell.add_argument("qty", type=int)

    p_auto = sub.add_parser("auto", help="watchlist 기반 자동매매")
    p_auto.add_argument("--execute", action="store_true",
                        help="실제 주문 실행 (기본: 시뮬레이션만)")

    args = parser.parse_args()
    cfg  = _load_config()

    mode_label = "모의투자" if cfg["mode"] == "paper" else "실전투자"
    print(f"[KIS {mode_label}] 연결 중...")

    try:
        if   args.cmd == "balance":  cmd_balance(cfg)
        elif args.cmd == "price":    cmd_price(cfg, args.ticker)
        elif args.cmd == "buy":      cmd_order(cfg, "buy",  args.ticker, args.qty)
        elif args.cmd == "sell":     cmd_order(cfg, "sell", args.ticker, args.qty)
        elif args.cmd == "auto":     auto_trade(cfg, dry_run=not args.execute)
    except requests.HTTPError as e:
        print(f"[API 오류] {e.response.status_code}: {e.response.text}")
    except requests.ConnectionError:
        print("[연결 오류] KIS 서버에 접속할 수 없습니다. 네트워크를 확인하세요.")


if __name__ == "__main__":
    main()
