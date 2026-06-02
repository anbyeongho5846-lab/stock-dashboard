"""
DART 캐시 일괄 생성 스크립트 (corp codes + 재무 데이터)
로컬(한국 IP)에서 한 번 실행 → git commit → Streamlit Cloud에서 API 호출 없이 사용

사용법:
    python generate_dart_cache.py
    python generate_dart_cache.py --api-key YOUR_KEY
    python generate_dart_cache.py --tickers 005930 000660 035420
    python generate_dart_cache.py --fin-only   # 재무 데이터만 갱신
"""

import argparse
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_api_key(cli_key: str | None) -> str:
    if cli_key:
        return cli_key
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        sp = __import__("pathlib").Path(__file__).parent / ".streamlit" / "secrets.toml"
        if sp.exists():
            with open(sp, "rb") as f:
                return tomllib.load(f).get("dart", {}).get("api_key", "")
    except Exception:
        pass
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="DART 캐시 생성")
    parser.add_argument("--api-key",  "-k", help="DART API 키")
    parser.add_argument("--tickers",  "-t", nargs="+", help="재무 데이터 수집 종목 (기본: DEFAULT_TICKERS)")
    parser.add_argument("--years",    "-y", type=int, default=6, help="재무 데이터 연수 (기본 6)")
    parser.add_argument("--fin-only",       action="store_true", help="재무 데이터만 갱신 (corp codes 스킵)")
    args = parser.parse_args()

    api_key = _load_api_key(args.api_key)
    if not api_key or api_key in ("[발급받은 키]", ""):
        print("[오류] DART API 키를 입력하세요.")
        print("  python generate_dart_cache.py --api-key YOUR_KEY")
        sys.exit(1)

    from dart_screener import (
        fetch_corp_codes, fetch_annual_financials, _get_corp_name,
        _CORP_CACHE_PATH, _FIN_CACHE_PATH,
        DEFAULT_TICKERS, DartNetworkError,
    )

    # ── 1. Corp codes ─────────────────────────────────────────────────────────
    if not args.fin_only:
        print("① Corp codes 다운로드 중...")
        try:
            mapping = fetch_corp_codes(api_key, force_refresh=True)
            print(f"   완료: {len(mapping):,}개 → {_CORP_CACHE_PATH.name}")
        except DartNetworkError as e:
            print(f"   [오류] {e}")
            sys.exit(1)

    # ── 2. 재무 데이터 ────────────────────────────────────────────────────────
    tickers = args.tickers or DEFAULT_TICKERS
    from dart_screener import fetch_corp_codes as _fc
    corp_map = _fc(api_key)

    print(f"\n② 재무 데이터 수집 ({len(tickers)}개 종목, {args.years}년치)...")
    ok_list, fail_list = [], []

    for i, tk in enumerate(tickers, 1):
        tk = tk.strip().upper()
        cc = corp_map.get(tk)
        if not cc:
            print(f"   [{i:2d}/{len(tickers)}] {tk}: corp_code 없음 — 건너뜀")
            fail_list.append(tk)
            continue

        print(f"   [{i:2d}/{len(tickers)}] {tk} 수집 중...", end=" ", flush=True)
        try:
            df = fetch_annual_financials(
                api_key, cc, years=args.years, ticker=tk, force_refresh=True
            )
            if df.empty:
                print("데이터 없음")
                fail_list.append(tk)
            else:
                print(f"완료 ({len(df)}년치, EPS: {df['eps'].dropna().tolist()})")
                ok_list.append(tk)
        except DartNetworkError as e:
            print(f"\n[DART 연결 오류] {e}")
            sys.exit(1)
        except Exception as e:
            print(f"오류: {e}")
            fail_list.append(tk)

        time.sleep(0.3)

    # ── 3. 결과 요약 ──────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  완료: {len(ok_list)}개 / 실패: {len(fail_list)}개")
    print(f"  저장 위치: {_FIN_CACHE_PATH.name}")
    if fail_list:
        print(f"  실패 목록: {', '.join(fail_list)}")
    print(f"{'='*55}")
    print()
    print("다음 단계 — GitHub에 커밋:")
    print("  git add dart_corp_codes.json dart_fin_cache.json")
    print("  git commit -m \"Update DART cache\"")
    print("  git push")


if __name__ == "__main__":
    main()
