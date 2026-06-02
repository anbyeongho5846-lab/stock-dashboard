"""
DART 캐시 일괄 생성 스크립트
- 인메모리로 누적한 뒤 체크포인트마다 일괄 저장 → 데이터 유실 방지
- 로컬(한국 IP)에서 실행 → git commit → Streamlit Cloud에서 API 없이 사용

사용법:
    python generate_dart_cache.py              # DEFAULT 20종목
    python generate_dart_cache.py --all        # 전체 상장사 (~3,967종목, 약 20분)
    python generate_dart_cache.py --fin-only   # 재무 데이터만 (corp codes 스킵)
    python generate_dart_cache.py --tickers 005930 000660 001500
"""

import argparse
import json
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_api_key(cli_key):
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


def _save(cache: dict, path) -> None:
    """인메모리 캐시를 파일에 안전하게 저장 (temp → rename)."""
    import os
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(cache, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(tmp, path)          # atomic rename
    except Exception as e:
        print(f"\n[저장 오류] {e}")


def main():
    parser = argparse.ArgumentParser(description="DART 캐시 생성")
    parser.add_argument("--api-key",  "-k")
    parser.add_argument("--tickers",  "-t", nargs="+")
    parser.add_argument("--years",    "-y", type=int, default=6)
    parser.add_argument("--fin-only",       action="store_true")
    parser.add_argument("--all",            action="store_true")
    args = parser.parse_args()

    api_key = _load_api_key(args.api_key)
    if not api_key or api_key in ("[발급받은 키]", ""):
        print("[오류] DART API 키를 입력하세요.")
        print("  python generate_dart_cache.py --api-key YOUR_KEY")
        sys.exit(1)

    from dart_screener import (
        fetch_corp_codes, fetch_financials_for_year,
        _get_corp_name, _get_shares_outstanding,
        _FIN_CACHE_PATH, _CORP_CACHE_PATH, _CORP_NAME_PATH,
        DEFAULT_TICKERS, DartNetworkError,
    )

    # ── 1. Corp codes ─────────────────────────────────────────────────────────
    if not args.fin_only:
        print("① Corp codes + 회사명 다운로드 중...")
        try:
            mapping = fetch_corp_codes(api_key, force_refresh=True)
            print(f"   완료: {len(mapping):,}개  →  {_CORP_CACHE_PATH.name}")
        except DartNetworkError as e:
            print(f"   [오류] {e}")
            sys.exit(1)
    else:
        mapping = fetch_corp_codes(api_key)

    # ── 2. 재무 데이터 수집 대상 ───────────────────────────────────────────────
    if args.all:
        tickers = sorted(mapping.keys())
        print(f"\n② 전체 상장사 재무 데이터 ({len(tickers):,}개, {args.years}년치)")
        print("   예상 시간: 약 20~30분  |  중단 후 재실행하면 이어서 수집\n")
    elif args.tickers:
        tickers = args.tickers
        print(f"\n② 재무 데이터 ({len(tickers)}개 종목)...")
    else:
        tickers = DEFAULT_TICKERS
        print(f"\n② 재무 데이터 (기본 {len(tickers)}개 종목)...")

    # ── 3. 인메모리로 누적 ────────────────────────────────────────────────────
    # 기존 캐시 파일을 메모리에 로드 (이어서 수집 가능)
    mem_cache: dict = {}
    if _FIN_CACHE_PATH.exists():
        try:
            mem_cache = json.loads(_FIN_CACHE_PATH.read_text(encoding="utf-8"))
            print(f"   기존 캐시 {len(mem_cache)}개 종목 로드됨")
        except Exception:
            pass

    ok_cnt = skip_cnt = fail_cnt = 0
    CHECKPOINT = 100   # N종목마다 파일 저장

    for i, tk in enumerate(tickers, 1):
        tk = tk.strip().upper()
        cc = mapping.get(tk)
        if not cc:
            fail_cnt += 1
            continue

        # 이미 캐시에 있으면 건너뜀 (--tickers 로 지정한 경우엔 강제 갱신)
        if not args.tickers and tk in mem_cache:
            skip_cnt += 1
            continue

        # 진행 출력
        if args.all:
            if i % 50 == 0 or i <= 5:
                pct = i / len(tickers) * 100
                print(f"   [{i:4d}/{len(tickers):4d}] {pct:.0f}%  완료:{ok_cnt}  실패:{fail_cnt}  캐시:{len(mem_cache)}")
        else:
            print(f"   [{i:2d}/{len(tickers):2d}] {tk} 수집 중...", end=" ", flush=True)

        try:
            # DART API 호출 (save_cache=False → 파일 쓰기 안 함)
            rows = []
            cur_y = __import__("datetime").datetime.today().year
            for pivot in (cur_y - 1, cur_y - 4):
                r = fetch_financials_for_year(api_key, cc, pivot)
                rows.extend(r)
                time.sleep(0.12)

            if not rows:
                fail_cnt += 1
                if not args.all:
                    print("데이터 없음")
                continue

            import pandas as pd
            df = (
                pd.DataFrame(rows)
                .drop_duplicates(subset=["year"])
                .sort_values("year")
                .reset_index(drop=True)
            )
            cutoff = cur_y - args.years - 1
            df = df[df["year"] >= cutoff].reset_index(drop=True)

            # BPS 계산 (equity / shares)
            if "bps" not in df.columns:
                df["bps"] = None
            if "equity" in df.columns and df["bps"].isna().any():
                shares = _get_shares_outstanding(tk)
                if shares and shares > 0:
                    df["bps"] = df.apply(
                        lambda r: round(r["equity"] / shares, 2)
                        if (pd.isna(r.get("bps")) and r.get("equity") and r["equity"] > 0)
                        else r.get("bps"),
                        axis=1,
                    )

            if df.empty:
                fail_cnt += 1
                if not args.all:
                    print("빈 데이터")
                continue

            # 회사명
            corp_name = _get_corp_name(api_key, cc) or tk
            time.sleep(0.05)

            # 인메모리에 저장
            mem_cache[tk] = {
                "corp_name": corp_name,
                "updated":   __import__("datetime").datetime.today().strftime("%Y-%m-%d"),
                "financials": df.where(df.notna(), None).to_dict("records"),
            }
            ok_cnt += 1

            if not args.all:
                eps_list = df["eps"].dropna().tolist()
                print(f"완료 ({len(df)}년치  EPS:{eps_list[-1] if eps_list else 'N/A'})")

        except DartNetworkError as e:
            print(f"\n[DART 연결 오류] {e}")
            _save(mem_cache, _FIN_CACHE_PATH)
            sys.exit(1)
        except Exception as e:
            fail_cnt += 1
            if not args.all:
                print(f"오류: {e}")

        # 체크포인트 저장
        if i % CHECKPOINT == 0:
            _save(mem_cache, _FIN_CACHE_PATH)
            if args.all:
                print(f"\n   [저장] {i}종목 처리 완료 / 캐시 {len(mem_cache)}개 → {_FIN_CACHE_PATH.name}\n")

    # ── 4. 최종 저장 ──────────────────────────────────────────────────────────
    _save(mem_cache, _FIN_CACHE_PATH)

    print(f"\n{'='*58}")
    print(f"  수집 완료: {ok_cnt:,}개  스킵: {skip_cnt:,}개  실패: {fail_cnt:,}개")
    print(f"  캐시 총 종목: {len(mem_cache):,}개")
    sz = _FIN_CACHE_PATH.stat().st_size / 1024
    print(f"  파일: {_FIN_CACHE_PATH.name}  ({sz:.0f} KB)")
    print(f"{'='*58}")
    print()
    print("다음 단계:")
    print("  git add dart_corp_codes.json dart_corp_names.json dart_fin_cache.json")
    print("  git commit -m \"Update DART cache\"")
    print("  git push")


if __name__ == "__main__":
    main()
