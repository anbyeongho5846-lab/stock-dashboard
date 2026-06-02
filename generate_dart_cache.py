"""
DART 캐시 일괄 생성 스크립트 (corp codes + 재무 데이터)
로컬(한국 IP)에서 실행 → git commit → Streamlit Cloud에서 API 호출 없이 사용

사용법:
    python generate_dart_cache.py              # corp codes + DEFAULT 20종목
    python generate_dart_cache.py --all        # corp codes + 전체 상장사 (~4,000종목, 약 20분)
    python generate_dart_cache.py --fin-only   # 재무 데이터만 갱신 (corp codes 스킵)
    python generate_dart_cache.py --api-key YOUR_KEY
    python generate_dart_cache.py --tickers 005930 000660 035420
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
    parser.add_argument("--tickers",  "-t", nargs="+",
                        help="재무 데이터 수집 종목 (기본: DEFAULT_TICKERS)")
    parser.add_argument("--years",    "-y", type=int, default=6,
                        help="재무 데이터 연수 (기본 6)")
    parser.add_argument("--fin-only",       action="store_true",
                        help="재무 데이터만 갱신 (corp codes 스킵)")
    parser.add_argument("--all",            action="store_true",
                        help="전체 상장사 재무 데이터 수집 (~4,000종목, 약 20분)")
    parser.add_argument("--resume",         action="store_true",
                        help="--all 중단 후 이어서 수집 (캐시 있는 종목 건너뜀)")
    args = parser.parse_args()

    api_key = _load_api_key(args.api_key)
    if not api_key or api_key in ("[발급받은 키]", ""):
        print("[오류] DART API 키를 입력하세요.")
        print("  python generate_dart_cache.py --api-key YOUR_KEY")
        sys.exit(1)

    from dart_screener import (
        fetch_corp_codes, fetch_annual_financials,
        _CORP_CACHE_PATH, _CORP_NAME_PATH, _FIN_CACHE_PATH,
        DEFAULT_TICKERS, DartNetworkError, _load_fin_cache,
    )

    # ── 1. Corp codes + corp names ────────────────────────────────────────────
    if not args.fin_only:
        print("① Corp codes + 회사명 다운로드 중...")
        try:
            mapping = fetch_corp_codes(api_key, force_refresh=True)
            name_exists = _CORP_NAME_PATH.exists()
            print(f"   완료: {len(mapping):,}개 기업")
            print(f"   저장: {_CORP_CACHE_PATH.name}"
                  + (f", {_CORP_NAME_PATH.name}" if name_exists else ""))
        except DartNetworkError as e:
            print(f"   [오류] {e}")
            sys.exit(1)
    else:
        mapping = fetch_corp_codes(api_key)

    # ── 2. 재무 데이터 수집 대상 결정 ─────────────────────────────────────────
    if args.all:
        # 전체 상장사 (corp_codes에 있는 모든 종목)
        tickers = sorted(mapping.keys())
        print(f"\n② 전체 상장사 재무 데이터 수집 ({len(tickers):,}개 종목, {args.years}년치)")
        print("   예상 소요 시간: 약 15~25분")
        print("   중단 후 --resume 옵션으로 이어서 수집 가능\n")
    elif args.tickers:
        tickers = args.tickers
        print(f"\n② 재무 데이터 수집 ({len(tickers)}개 종목, {args.years}년치)...")
    else:
        tickers = DEFAULT_TICKERS
        print(f"\n② 재무 데이터 수집 (기본 {len(tickers)}개 종목, {args.years}년치)...")

    # ── 3. 재무 데이터 수집 ───────────────────────────────────────────────────
    existing_cache = _load_fin_cache()
    ok_cnt = skip_cnt = fail_cnt = 0
    checkpoint_interval = 50  # N종목마다 중간 저장

    for i, tk in enumerate(tickers, 1):
        tk = tk.strip().upper()
        cc = mapping.get(tk)
        if not cc:
            fail_cnt += 1
            if not args.all:
                print(f"   [{i:4d}/{len(tickers)}] {tk}: corp_code 없음")
            continue

        # --resume: 이미 캐시가 있으면 건너뜀
        if args.resume and tk in existing_cache:
            skip_cnt += 1
            continue

        label = f"[{i:4d}/{len(tickers):4d}] {tk}"
        if not args.all or i % 100 == 0 or i <= 5:
            print(f"   {label} 수집 중...", end=" ", flush=True)
        elif i % 10 == 0:
            # 10종목마다 진행률 한 줄 출력
            pct = i / len(tickers) * 100
            print(f"\r   진행: {i}/{len(tickers)} ({pct:.0f}%) "
                  f"완료:{ok_cnt} 실패:{fail_cnt}  ", end="", flush=True)

        try:
            df = fetch_annual_financials(
                api_key, cc, years=args.years, ticker=tk, force_refresh=True
            )
            if df.empty:
                fail_cnt += 1
                if not args.all or i % 100 == 0:
                    print("데이터 없음")
            else:
                ok_cnt += 1
                if not args.all or i % 100 == 0 or i <= 5:
                    eps_list = df["eps"].dropna().tolist()
                    print(f"완료 ({len(df)}년치  EPS:{eps_list[-1] if eps_list else 'N/A'})")
        except DartNetworkError as e:
            print(f"\n[DART 연결 오류] {e}")
            sys.exit(1)
        except Exception as e:
            fail_cnt += 1
            if not args.all:
                print(f"오류: {e}")

        # 중간 저장 (--all 일 때만)
        if args.all and i % checkpoint_interval == 0:
            from dart_screener import _load_fin_cache as _lfc
            cur = _lfc()
            print(f"\n   [체크포인트] {i}종목 처리 / 캐시 {len(cur)}개 저장됨")

        time.sleep(0.15)

    # ── 4. 결과 요약 ──────────────────────────────────────────────────────────
    if args.all:
        print()  # 개행
    final_cache = _load_fin_cache()
    print(f"\n{'='*60}")
    print(f"  수집 완료: {ok_cnt:,}개  실패/없음: {fail_cnt:,}개  스킵: {skip_cnt:,}개")
    print(f"  캐시 총 종목 수: {len(final_cache):,}개")
    print(f"  저장 위치: {_FIN_CACHE_PATH.name}  "
          f"({_FIN_CACHE_PATH.stat().st_size / 1024:.0f} KB)")
    print(f"{'='*60}")
    print()
    print("다음 단계 — GitHub에 커밋:")
    print("  git add dart_corp_codes.json dart_corp_names.json dart_fin_cache.json")
    print("  git commit -m \"Update DART cache\"")
    print("  git push")


if __name__ == "__main__":
    main()
