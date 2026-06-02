"""
DART 기본적 분석 스크리너
- Open DART API → 연간 EPS·BPS·매출·영업이익·순이익
- yfinance → 주가 이력
- 역사적 PER/PBR 밴드 계산 + 저평가 종목 점수화
"""

import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import yfinance as yf

_DART_BASE        = "https://opendart.fss.or.kr/api"
_CORP_CACHE_PATH  = Path(__file__).parent / "dart_corp_codes.json"
_CORP_NAME_PATH   = Path(__file__).parent / "dart_corp_names.json"   # ticker→corp_name 매핑
_FIN_CACHE_PATH   = Path(__file__).parent / "dart_fin_cache.json"
_CACHE_TTL_DAYS   = 30   # corp codes 캐시 TTL
_FIN_CACHE_TTL    = 90   # 재무 데이터 캐시 TTL

# DART API에 연결할 수 없을 때 발생하는 예외
class DartNetworkError(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 재무 데이터 파일 캐시 (dart_fin_cache.json)
# 로컬에서 생성 후 커밋 → 클라우드는 파일에서 읽음
# ─────────────────────────────────────────────────────────────────────────────

def _load_fin_cache() -> dict:
    if _FIN_CACHE_PATH.exists():
        try:
            return json.loads(_FIN_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_fin_cache(cache: dict) -> None:
    try:
        _FIN_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, default=str), encoding="utf-8"
        )
    except Exception:
        pass


def _fin_cache_fresh(entry: dict, ttl_days: int = _FIN_CACHE_TTL) -> bool:
    updated = entry.get("updated", "")
    if not updated:
        return False
    try:
        age = (datetime.today() - datetime.fromisoformat(updated)).days
        return age < ttl_days
    except Exception:
        return False


def get_fin_from_cache(ticker: str) -> pd.DataFrame | None:
    """캐시 파일에서 종목 재무 데이터 반환. 없거나 만료면 None."""
    cache = _load_fin_cache()
    entry = cache.get(ticker.upper())
    if not entry or not _fin_cache_fresh(entry):
        return None
    rows = entry.get("financials", [])
    return pd.DataFrame(rows) if rows else None


def save_fin_to_cache(ticker: str, corp_name: str, fin_df: pd.DataFrame) -> None:
    """재무 데이터를 캐시 파일에 저장."""
    cache = _load_fin_cache()
    cache[ticker.upper()] = {
        "corp_name": corp_name,
        "updated":   datetime.today().strftime("%Y-%m-%d"),
        "financials": fin_df.where(fin_df.notna(), None).to_dict("records"),
    }
    _save_fin_cache(cache)


# ─────────────────────────────────────────────────────────────────────────────
# Corp Code 매핑 (종목코드 → DART 고유번호)
# ─────────────────────────────────────────────────────────────────────────────

def _cache_valid(path: Path, ttl_days: int) -> bool:
    if not path.exists():
        return False
    import os
    return (datetime.now().timestamp() - os.path.getmtime(path)) / 86400 < ttl_days


def fetch_corp_codes(api_key: str, force_refresh: bool = False) -> dict[str, str]:
    """종목코드 → DART 고유번호 매핑.

    캐시 파일(dart_corp_codes.json)이 있으면 TTL 내에서는 파일을 사용.
    파일이 없거나 force_refresh=True 일 때만 DART API 호출.
    """
    if not force_refresh and _cache_valid(_CORP_CACHE_PATH, _CACHE_TTL_DAYS):
        try:
            return json.loads(_CORP_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 캐시가 만료/없을 때 API 호출 — 실패해도 기존 캐시 반환
    try:
        resp = requests.get(
            f"{_DART_BASE}/corpCode.xml",
            params={"crtfc_key": api_key},
            timeout=60,
        )
        resp.raise_for_status()
    except (requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout) as e:
        # 네트워크 불가 → 기존 캐시 파일이라도 사용
        if _CORP_CACHE_PATH.exists():
            try:
                return json.loads(_CORP_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        raise DartNetworkError(
            "DART API(opendart.fss.or.kr)에 연결할 수 없습니다. "
            "해외 서버에서는 접속이 차단될 수 있습니다.\n"
            "로컬에서 generate_dart_cache.py를 실행하여 "
            "dart_corp_codes.json을 생성한 뒤 커밋해 주세요."
        ) from e

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ET.fromstring(xml_bytes.decode("utf-8"))
    mapping:  dict[str, str] = {}   # ticker → corp_code
    name_map: dict[str, str] = {}   # ticker → corp_name
    for item in root.findall("list"):
        sc = (item.findtext("stock_code") or "").strip()
        cc = (item.findtext("corp_code")  or "").strip()
        cn = (item.findtext("corp_name")  or "").strip()
        if sc and cc:
            mapping[sc]  = cc
            if cn:
                name_map[sc] = cn

    try:
        _CORP_CACHE_PATH.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=None), encoding="utf-8"
        )
    except Exception:
        pass

    # corp_name 별도 저장 → 검색에 사용
    try:
        _CORP_NAME_PATH.write_text(
            json.dumps(name_map, ensure_ascii=False, indent=None), encoding="utf-8"
        )
    except Exception:
        pass

    return mapping


def get_corp_name_map() -> dict[str, str]:
    """ticker → 회사명 매핑 반환 (dart_corp_names.json 우선, fin cache 보완)."""
    names: dict[str, str] = {}
    # corp_names.json
    if _CORP_NAME_PATH.exists():
        try:
            names.update(json.loads(_CORP_NAME_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    # fin_cache에서 보완
    if _FIN_CACHE_PATH.exists():
        try:
            for tk, entry in json.loads(
                _FIN_CACHE_PATH.read_text(encoding="utf-8")
            ).items():
                if tk not in names and entry.get("corp_name"):
                    names[tk] = entry["corp_name"]
        except Exception:
            pass
    return names


def get_corp_code(ticker: str, api_key: str) -> str | None:
    return fetch_corp_codes(api_key).get(ticker.strip().upper())


def corp_cache_exists() -> bool:
    """dart_corp_codes.json 캐시 파일 존재 여부."""
    return _CORP_CACHE_PATH.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 재무 데이터 수집
# ─────────────────────────────────────────────────────────────────────────────

_EPS_KEYS    = ("기본주당이익(손실)", "주당순이익", "기본주당순이익", "기본주당이익",
                "주당이익", "BasicEarnings", "EarningsPerShare")
_BPS_KEYS    = ("주당순자산가치", "주당순자산", "주당장부가치",
                "지배기업소유주에귀속되는주당순자산", "주당자본금",
                "BookValuePerShare")
_EQUITY_KEYS = ("지배기업 소유주지분", "지배기업소유주지분",
                "주주에귀속되는자본", "자본총계",
                "StockholdersEquity", "TotalEquity")
_REV_KEYS    = ("매출액", "수익(매출액)", "영업수익", "매출")
_OP_KEYS     = ("영업이익", "영업이익(손실)", "영업손익")
_NET_KEYS    = ("당기순이익", "당기순이익(손실)", "연결당기순이익")


def _dart_request(api_key: str, endpoint: str, **params) -> list[dict]:
    try:
        r = requests.get(
            f"{_DART_BASE}/{endpoint}",
            params={"crtfc_key": api_key, **params},
            timeout=30,
        )
        d = r.json()
        if d.get("status") == "000":
            return d.get("list", [])
    except (requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout) as e:
        raise DartNetworkError(
            f"DART API 연결 실패 ({endpoint}). "
            "해외 서버 접속 차단 또는 네트워크 오류입니다."
        ) from e
    except Exception:
        pass
    return []


def _parse_amount(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).replace(",", "").strip()
    if not s or s in ("-", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_field(items: list[dict], amount_field: str, *keywords) -> float | None:
    for item in items:
        nm  = item.get("account_nm", "")
        aid = item.get("account_id", "")
        for kw in keywords:
            if kw in nm or kw in aid:
                v = _parse_amount(item.get(amount_field))
                if v is not None:
                    return v
    return None


def _parse_year_from_items(items: list[dict], amount_field: str,
                            year_name_field: str) -> int | None:
    """thstrm_nm / frmtrm_nm에서 연도 추출 (예: '제 55 기' → 연도 불명, 직접 전달)."""
    return None


def fetch_financials_for_year(api_key: str, corp_code: str,
                               bsns_year: int) -> list[dict]:
    """DART fnlttSinglAcntAll 호출 → 당기·전기·전전기 데이터 파싱.

    반환: [{"year": int, "eps": ..., "bps": ..., ...}, ...]  (최대 3개)
    """
    rows = []
    for fs_div in ("CFS", "OFS"):
        items = _dart_request(
            api_key, "fnlttSinglAcntAll.json",
            corp_code=corp_code,
            bsns_year=str(bsns_year),
            reprt_code="11011",
            fs_div=fs_div,
        )
        if not items:
            continue

        # 당기(thstrm) / 전기(frmtrm) / 전전기(bfefrmtrm) 각각 추출
        year_slots = [
            (bsns_year,     "thstrm_amount",    "thstrm_nm"),
            (bsns_year - 1, "frmtrm_amount",    "frmtrm_nm"),
            (bsns_year - 2, "bfefrmtrm_amount", "bfefrmtrm_nm"),
        ]

        for y, amt_f, _ in year_slots:
            eps     = _extract_field(items, amt_f, *_EPS_KEYS)
            bps     = _extract_field(items, amt_f, *_BPS_KEYS)
            equity  = _extract_field(items, amt_f, *_EQUITY_KEYS)
            revenue = _extract_field(items, amt_f, *_REV_KEYS)
            op_inc  = _extract_field(items, amt_f, *_OP_KEYS)
            net_inc = _extract_field(items, amt_f, *_NET_KEYS)

            if any(v is not None for v in [eps, revenue, op_inc, net_inc]):
                rows.append(dict(
                    year=y, fs_div=fs_div,
                    eps=eps, bps=bps, equity=equity,
                    revenue=revenue, op_income=op_inc, net_income=net_inc,
                ))

        if rows:
            break   # CFS 성공 시 OFS 불필요

    return rows


def _get_shares_outstanding(ticker: str) -> int | None:
    """yfinance로 발행주식수 조회."""
    for suffix in (".KS", ".KQ", ""):
        try:
            info = yf.Ticker(f"{ticker}{suffix}").fast_info
            shares = getattr(info, "shares", None)
            if shares and shares > 0:
                return int(shares)
        except Exception:
            continue
    return None


def fetch_annual_financials(api_key: str, corp_code: str,
                             years: int = 5,
                             ticker: str = "",
                             force_refresh: bool = False) -> pd.DataFrame:
    """최근 N년 재무 데이터 수집.

    우선순위: ① 파일 캐시(dart_fin_cache.json) ② DART API 호출
    BPS: ① DART 직접 ② equity/shares 계산 ③ pykrx
    """
    # ── ① 파일 캐시 확인 ──────────────────────────────────────────────────────
    if ticker and not force_refresh:
        cached = get_fin_from_cache(ticker)
        if cached is not None and not cached.empty:
            return cached

    # ── ② DART API 호출 ──────────────────────────────────────────────────────
    cur_y  = datetime.today().year
    all_rows: list[dict] = []

    for pivot in (cur_y - 1, cur_y - 4):
        rows = fetch_financials_for_year(api_key, corp_code, pivot)
        all_rows.extend(rows)
        time.sleep(0.2)

    if not all_rows:
        return pd.DataFrame()

    df = (
        pd.DataFrame(all_rows)
        .drop_duplicates(subset=["year"])
        .sort_values("year")
        .reset_index(drop=True)
    )
    cutoff = cur_y - years - 1
    df = df[df["year"] >= cutoff].reset_index(drop=True)

    # BPS 계산: equity ÷ 발행주식수 (DART에서 직접 못 가져온 경우)
    if "bps" not in df.columns:
        df["bps"] = None
    if "equity" in df.columns and df["bps"].isna().any() and ticker:
        shares = _get_shares_outstanding(ticker)
        if shares and shares > 0:
            def _calc_bps(row):
                if pd.notna(row.get("bps")):
                    return row["bps"]
                eq = row.get("equity")
                if eq and eq > 0:
                    return round(eq / shares, 2)
                return None
            df["bps"] = df.apply(_calc_bps, axis=1)

    # pykrx fallback은 KRX 인증 필요로 비활성화 (equity/shares 계산으로 대체)

    # ── 결과를 파일 캐시에 저장 ───────────────────────────────────────────────
    if ticker and not df.empty:
        corp_name = _get_corp_name(api_key, corp_code) or ticker
        save_fin_to_cache(ticker, corp_name, df)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 주가 이력
# ─────────────────────────────────────────────────────────────────────────────

def fetch_price_history(ticker: str, years: int = 6) -> pd.DataFrame:
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=years * 365)).strftime("%Y-%m-%d")

    for suffix in (".KS", ".KQ", ""):
        try:
            df = yf.download(
                f"{ticker}{suffix}", start=start, end=end,
                auto_adjust=True, progress=False,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Close"]].dropna()
            if not df.empty:
                df.index = pd.to_datetime(df.index)
                return df
        except Exception:
            continue
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# PER / PBR 밴드 계산
# ─────────────────────────────────────────────────────────────────────────────

def calc_band(fin_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """연도별 PER/PBR 고가·저가·평균 밴드."""
    if fin_df.empty or price_df.empty:
        return pd.DataFrame()

    bands = []
    for _, row in fin_df.iterrows():
        y   = int(row["year"])
        eps = row.get("eps")
        bps = row.get("bps")

        yp = price_df[price_df.index.year == y]["Close"]
        if yp.empty:
            continue

        ph = float(yp.max())
        pl = float(yp.min())
        pa = float(yp.mean())
        b  = {"year": y, "p_high": ph, "p_low": pl, "p_avg": pa,
              "eps": eps, "bps": bps}

        if eps and eps > 0:
            b.update(per_high=ph / eps, per_low=pl / eps, per_avg=pa / eps)
        if bps and bps > 0:
            b.update(pbr_high=ph / bps, pbr_low=pl / bps, pbr_avg=pa / bps)

        bands.append(b)

    return pd.DataFrame(bands) if bands else pd.DataFrame()


def build_band_lines(fin_df: pd.DataFrame, price_df: pd.DataFrame,
                     multiples: list[float], mode: str = "per") -> dict[float, pd.Series]:
    """주가 시계열 × EPS/BPS → 밴드선 딕셔너리 반환.

    price_df.index는 DatetimeIndex 가정.
    """
    if fin_df.empty or price_df.empty:
        return {}

    key = "eps" if mode == "per" else "bps"

    # 연도별 EPS/BPS → 날짜 기준 매핑 (step function)
    annual = fin_df[["year", key]].dropna().copy()
    if annual.empty:
        return {}

    # 각 거래일에 해당 연도의 EPS/BPS 할당
    price_idx = price_df.index
    per_base  = pd.Series(index=price_idx, dtype=float)

    for _, row in annual.iterrows():
        y  = int(row["year"])
        ev = row[key]
        if ev and ev > 0:
            mask = price_idx.year == y
            per_base.loc[mask] = ev

    per_base = per_base.dropna()
    if per_base.empty:
        return {}

    return {m: per_base * m for m in multiples}


# ─────────────────────────────────────────────────────────────────────────────
# 저평가 점수
# ─────────────────────────────────────────────────────────────────────────────

def score_stock(band_df: pd.DataFrame, cur_price: float,
                fin_df: pd.DataFrame) -> dict:
    """저평가 종합 점수 (0~100) 계산."""
    score   = 50
    reasons: list[str] = []
    cur_per = cur_pbr = eps = bps = None

    if not fin_df.empty:
        last = fin_df.iloc[-1]
        eps  = last.get("eps")
        bps  = last.get("bps")
        if eps and eps > 0:
            cur_per = cur_price / eps
        if bps and bps > 0:
            cur_pbr = cur_price / bps

    if not band_df.empty:
        # ── PER 평가 ──────────────────────────────────────────────────────────
        per_s = band_df["per_avg"].dropna() if "per_avg" in band_df.columns else pd.Series(dtype=float)
        if cur_per is not None and len(per_s) >= 2:
            hist_avg = per_s.mean()
            r = cur_per / hist_avg
            if r < 0.60:
                score += 25; reasons.append(f"PER 역사적 대비 {(1-r)*100:.0f}% 저평가 (현재 {cur_per:.1f}배 vs 평균 {hist_avg:.1f}배)")
            elif r < 0.85:
                score += 12; reasons.append(f"PER 소폭 저평가 ({cur_per:.1f}배 vs 평균 {hist_avg:.1f}배)")
            elif r > 1.50:
                score -= 15; reasons.append(f"PER 고평가 ({cur_per:.1f}배 vs 평균 {hist_avg:.1f}배)")
            elif r > 1.20:
                score -= 7;  reasons.append(f"PER 소폭 고평가 ({cur_per:.1f}배 vs 평균 {hist_avg:.1f}배)")

        # ── PBR 평가 ──────────────────────────────────────────────────────────
        pbr_s = band_df["pbr_avg"].dropna() if "pbr_avg" in band_df.columns else pd.Series(dtype=float)
        if cur_pbr is not None and len(pbr_s) >= 2:
            hist_avg = pbr_s.mean()
            r = cur_pbr / hist_avg
            if r < 0.60:
                score += 20; reasons.append(f"PBR 역사적 대비 {(1-r)*100:.0f}% 저평가 (현재 {cur_pbr:.2f}배 vs 평균 {hist_avg:.2f}배)")
            elif r < 0.85:
                score += 10; reasons.append(f"PBR 소폭 저평가 ({cur_pbr:.2f}배 vs 평균 {hist_avg:.2f}배)")
            elif r > 1.50:
                score -= 12; reasons.append(f"PBR 고평가 ({cur_pbr:.2f}배 vs 평균 {hist_avg:.2f}배)")

    # ── PBR < 1 (청산가치 이하) ───────────────────────────────────────────────
    if cur_pbr is not None and 0 < cur_pbr < 1.0:
        score += 5; reasons.append(f"PBR 1배 미만 ({cur_pbr:.2f}배) — 청산가치 이하")

    # ── 이익 성장성 ────────────────────────────────────────────────────────────
    if not fin_df.empty and len(fin_df) >= 2:
        ni = fin_df["net_income"].dropna()
        if len(ni) >= 2:
            f_val, l_val = float(ni.iloc[0]), float(ni.iloc[-1])
            if f_val > 0 and l_val > f_val:
                g = (l_val - f_val) / abs(f_val) * 100
                if g > 50:   score += 10; reasons.append(f"순이익 {g:.0f}% 성장")
                elif g > 15: score += 5;  reasons.append(f"순이익 {g:.0f}% 성장")
            elif l_val < 0:
                score -= 15; reasons.append("최근 연도 순손실 발생")
            elif f_val > 0 and l_val < f_val * 0.7:
                score -= 8;  reasons.append("이익 30% 이상 감소")

    score = max(0, min(100, score))

    if score >= 75:   grade = "강력매수"
    elif score >= 63: grade = "매수"
    elif score >= 45: grade = "중립"
    elif score >= 30: grade = "주의"
    else:             grade = "매도"

    return dict(
        score=score, grade=grade, reasons=reasons,
        cur_per=cur_per, cur_pbr=cur_pbr, eps=eps, bps=bps,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 스크리너 실행
# ─────────────────────────────────────────────────────────────────────────────

def run_screener(tickers: list[str], api_key: str,
                 years: int = 5,
                 progress_cb=None) -> list[dict]:
    """복수 종목 스크리닝. progress_cb(i, total, ticker) 콜백 지원."""
    corp_codes = fetch_corp_codes(api_key)
    results    = []
    total      = len(tickers)

    for i, tk in enumerate(tickers):
        tk = tk.strip().upper()
        if progress_cb:
            progress_cb(i, total, tk)

        cc = corp_codes.get(tk)
        if not cc:
            continue

        try:
            fin_df = fetch_annual_financials(api_key, cc, years, ticker=tk)
            if fin_df.empty:
                continue

            price_df = fetch_price_history(tk, years + 1)
            if price_df.empty:
                continue

            cur_price = float(price_df["Close"].iloc[-1])
            band_df   = calc_band(fin_df, price_df)
            s         = score_stock(band_df, cur_price, fin_df)

            # 기업명 조회 (DART company endpoint)
            corp_name = _get_corp_name(api_key, cc)

            results.append(dict(
                ticker=tk,
                name=corp_name or tk,
                corp_code=cc,
                cur_price=cur_price,
                fin_df=fin_df,
                price_df=price_df,
                band_df=band_df,
                **s,
            ))
        except Exception:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# 종목 검색 (fin_cache + corp_names 기반 — API 호출 없음)
# ─────────────────────────────────────────────────────────────────────────────

def search_corps(query: str, max_results: int = 30) -> list[dict]:
    """회사명 또는 종목코드로 검색.

    dart_corp_names.json (전체 상장사 이름) 에서 검색하고,
    dart_fin_cache.json 에 재무 데이터가 있는 종목은 표시.
    """
    query = query.strip()
    if not query:
        return []

    name_map   = get_corp_name_map()           # ticker → corp_name
    fin_cache  = _load_fin_cache()             # ticker → fin entry

    results: list[dict] = []
    q_lower = query.lower()
    q_is_code = query.isdigit()

    for ticker, corp_name in name_map.items():
        # 종목코드 prefix 매치 또는 회사명 포함 매치
        if q_is_code:
            if not ticker.startswith(query):
                continue
        else:
            if q_lower not in corp_name.lower() and q_lower not in ticker:
                continue

        has_cache = ticker in fin_cache and _fin_cache_fresh(fin_cache[ticker])
        cached_entry = fin_cache.get(ticker, {})
        latest_eps = None
        if has_cache:
            rows = cached_entry.get("financials", [])
            if rows:
                last = rows[-1]
                latest_eps = last.get("eps")

        results.append({
            "ticker":     ticker,
            "corp_name":  corp_name,
            "has_cache":  has_cache,
            "latest_eps": latest_eps,
        })
        if len(results) >= max_results:
            break

    # 캐시 있는 종목 우선, 그 다음 코드 순
    results.sort(key=lambda x: (not x["has_cache"], x["ticker"]))
    return results


def _get_corp_name(api_key: str, corp_code: str) -> str | None:
    try:
        r = requests.get(
            f"{_DART_BASE}/company.json",
            params={"crtfc_key": api_key, "corp_code": corp_code},
            timeout=15,
        )
        d = r.json()
        if d.get("status") == "000":
            return d.get("corp_name")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 차트
# ─────────────────────────────────────────────────────────────────────────────

_BAND_COLORS = {
    "per": ["#5b8dee", "#3bc9a0", "#ffc107", "#ff7043", "#ab47bc"],
    "pbr": ["#5b8dee", "#3bc9a0", "#ffc107", "#ff7043"],
}


def plot_valuation_band(ticker: str, name: str,
                        price_df: pd.DataFrame,
                        fin_df: pd.DataFrame,
                        band_df: pd.DataFrame,
                        show: bool = True) -> go.Figure:
    """PER/PBR 밴드 + 주가 + 재무 요약 복합 차트."""
    has_eps = not fin_df.empty and fin_df["eps"].notna().any()
    has_bps = not fin_df.empty and fin_df["bps"].notna().any()
    has_fin = not fin_df.empty

    rows    = 1 + (1 if has_eps else 0) + (1 if has_bps else 0) + (1 if has_fin else 0)
    heights = []
    titles  = []

    heights.append(0.40); titles.append(f"{name} ({ticker}) — 주가")
    if has_eps:
        heights.append(0.20); titles.append("PER 밴드")
    if has_bps:
        heights.append(0.20); titles.append("PBR 밴드")
    if has_fin:
        heights.append(0.20); titles.append("연간 재무 추이")

    # 높이 정규화
    s = sum(heights)
    heights = [h / s for h in heights]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=titles,
        row_heights=heights,
    )

    cur_row = 1

    # ── 주가 ─────────────────────────────────────────────────────────────────
    if not price_df.empty:
        fig.add_trace(go.Scatter(
            x=price_df.index, y=price_df["Close"],
            fill="tozeroy",
            fillcolor="rgba(69,123,157,0.08)",
            line=dict(color="#457b9d", width=1.8),
            name="주가",
            hovertemplate="%{x|%Y-%m-%d}  %{y:,.0f}원<extra></extra>",
        ), row=cur_row, col=1)
    cur_row += 1

    # ── PER 밴드 ─────────────────────────────────────────────────────────────
    if has_eps:
        per_multiples = [5, 10, 15, 20, 25]
        band_lines = build_band_lines(fin_df, price_df, per_multiples, mode="per")

        for m, color in zip(per_multiples, _BAND_COLORS["per"]):
            line = band_lines.get(m)
            if line is not None and not line.empty:
                fig.add_trace(go.Scatter(
                    x=line.index, y=line.values,
                    mode="lines",
                    line=dict(color=color, width=1.2, dash="dot"),
                    name=f"PER {m}배",
                    hovertemplate=f"PER {m}배  %{{y:,.0f}}원<extra></extra>",
                ), row=cur_row, col=1)
                # 주가도 같이 표시 (실제 PER 파악용)
        if not price_df.empty:
            fig.add_trace(go.Scatter(
                x=price_df.index, y=price_df["Close"],
                line=dict(color="#e2e8f0", width=1.5),
                name="주가",
                showlegend=False,
                hovertemplate="%{x|%Y-%m-%d}  %{y:,.0f}원<extra></extra>",
            ), row=cur_row, col=1)
        cur_row += 1

    # ── PBR 밴드 ─────────────────────────────────────────────────────────────
    if has_bps:
        pbr_multiples = [0.5, 1.0, 1.5, 2.0]
        band_lines_pbr = build_band_lines(fin_df, price_df, pbr_multiples, mode="pbr")

        for m, color in zip(pbr_multiples, _BAND_COLORS["pbr"]):
            line = band_lines_pbr.get(m)
            if line is not None and not line.empty:
                fig.add_trace(go.Scatter(
                    x=line.index, y=line.values,
                    mode="lines",
                    line=dict(color=color, width=1.2, dash="dot"),
                    name=f"PBR {m}배",
                    hovertemplate=f"PBR {m}배  %{{y:,.0f}}원<extra></extra>",
                ), row=cur_row, col=1)
        if not price_df.empty:
            fig.add_trace(go.Scatter(
                x=price_df.index, y=price_df["Close"],
                line=dict(color="#e2e8f0", width=1.5),
                name="주가",
                showlegend=False,
                hovertemplate="%{x|%Y-%m-%d}  %{y:,.0f}원<extra></extra>",
            ), row=cur_row, col=1)
        cur_row += 1

    # ── 재무 추이 ─────────────────────────────────────────────────────────────
    if has_fin:
        yr = fin_df["year"].astype(str)

        def _bar_vals(col: str, divisor: float = 1e8):
            return (fin_df[col].fillna(0) / divisor).tolist()

        def _unit_label(col: str) -> str:
            mx = fin_df[col].dropna().abs().max() if fin_df[col].notna().any() else 0
            if mx >= 1e12: return "조원"
            return "억원"

        if fin_df["revenue"].notna().any():
            fig.add_trace(go.Bar(
                x=yr, y=_bar_vals("revenue"),
                name=f"매출({_unit_label('revenue')})", marker_color="#457b9d",
                opacity=0.8,
            ), row=cur_row, col=1)
        if fin_df["op_income"].notna().any():
            fig.add_trace(go.Bar(
                x=yr, y=_bar_vals("op_income"),
                name=f"영업이익({_unit_label('op_income')})", marker_color="#2dc653",
                opacity=0.8,
            ), row=cur_row, col=1)
        if fin_df["net_income"].notna().any():
            fig.add_trace(go.Bar(
                x=yr, y=_bar_vals("net_income"),
                name=f"순이익({_unit_label('net_income')})", marker_color="#f4a261",
                opacity=0.8,
            ), row=cur_row, col=1)

    fig.update_layout(
        height=900,
        template="plotly_dark",
        barmode="group",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(t=80, b=30, l=10, r=10),
        title=dict(
            text=f"{name} — 기본적 분석 (DART 기반)",
            font=dict(size=17),
        ),
        hovermode="x unified",
    )

    if show:
        fig.show()
    return fig


def plot_screener_result(results: list[dict], show: bool = True) -> go.Figure:
    """스크리너 결과 — 버블 차트 (PER vs PBR, 버블=점수)."""
    if not results:
        return go.Figure()

    xs, ys, sizes, texts, colors, hovers = [], [], [], [], [], []
    grade_color = {
        "강력매수": "#1a6b3a", "매수": "#2dc653",
        "중립": "#718096", "주의": "#f4a261", "매도": "#c0392b",
    }

    for r in results:
        per = r.get("cur_per")
        pbr = r.get("cur_pbr")
        if per is None or pbr is None:
            continue
        if per <= 0 or per > 200 or pbr <= 0 or pbr > 20:
            continue

        xs.append(per)
        ys.append(pbr)
        sizes.append(max(10, r["score"] * 0.6))
        texts.append(r.get("name", r["ticker"]))
        colors.append(grade_color.get(r["grade"], "#718096"))
        hovers.append(
            f"<b>{r.get('name', r['ticker'])} ({r['ticker']})</b><br>"
            f"PER: {per:.1f}배  PBR: {pbr:.2f}배<br>"
            f"점수: {r['score']} ({r['grade']})<br>"
            f"현재가: {r['cur_price']:,.0f}원"
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        marker=dict(size=sizes, color=colors, opacity=0.8,
                    line=dict(color="rgba(255,255,255,0.3)", width=1)),
        text=texts,
        textposition="top center",
        textfont=dict(size=9, color="rgba(220,220,220,0.9)"),
        hovertext=hovers,
        hoverinfo="text",
    ))

    # 기준선
    fig.add_hline(y=1.0, line_dash="dash", line_color="rgba(255,255,255,0.2)",
                  annotation_text="PBR 1배")
    fig.add_vline(x=10,  line_dash="dash", line_color="rgba(255,255,255,0.2)",
                  annotation_text="PER 10배")

    fig.update_layout(
        height=520,
        template="plotly_dark",
        title=dict(text="저평가 스크리너 — PER vs PBR (버블 크기: 저평가 점수)",
                   font=dict(size=15)),
        xaxis=dict(title="PER (배)", range=[0, max(xs) * 1.15] if xs else [0, 40]),
        yaxis=dict(title="PBR (배)", range=[0, max(ys) * 1.15] if ys else [0, 5]),
        margin=dict(t=60, b=40),
    )

    if show:
        fig.show()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 기본 KOSPI 대표 종목 리스트 (스크리너 기본값)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TICKERS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005380",  # 현대차
    "035420",  # NAVER
    "000270",  # 기아
    "068270",  # 셀트리온
    "105560",  # KB금융
    "055550",  # 신한지주
    "032830",  # 삼성생명
    "086790",  # 하나금융지주
    "012330",  # 현대모비스
    "028260",  # 삼성물산
    "096770",  # SK이노베이션
    "003550",  # LG
    "009150",  # 삼성전기
    "011200",  # HMM
    "034730",  # SK
    "015760",  # 한국전력
    "030200",  # KT
    "017670",  # SK텔레콤
]
