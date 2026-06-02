"""
DART 기업 고유번호 캐시 생성 스크립트
로컬(한국 IP)에서 한 번만 실행하면 dart_corp_codes.json이 생성됩니다.
생성된 파일을 git commit → push 하면 Streamlit Cloud에서도 사용 가능합니다.

사용법:
    python generate_dart_cache.py
    python generate_dart_cache.py --api-key YOUR_KEY
"""

import argparse
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="DART corp code 캐시 생성")
    parser.add_argument(
        "--api-key", "-k",
        help="DART API 키 (미입력 시 .streamlit/secrets.toml에서 읽음)",
    )
    args = parser.parse_args()

    # API 키 결정
    api_key = args.api_key
    if not api_key:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # pip install tomli
            except ImportError:
                tomllib = None

        secrets_path = __import__("pathlib").Path(__file__).parent / ".streamlit" / "secrets.toml"
        if tomllib and secrets_path.exists():
            with open(secrets_path, "rb") as f:
                secrets = tomllib.load(f)
            api_key = secrets.get("dart", {}).get("api_key", "")

    if not api_key or api_key in ("[발급받은 키]", ""):
        print("[오류] DART API 키를 입력하세요.")
        print("  python generate_dart_cache.py --api-key YOUR_DART_API_KEY")
        print("  또는 .streamlit/secrets.toml 에 [dart] api_key = '...' 설정")
        sys.exit(1)

    print("DART corpCode.xml 다운로드 중... (수십 초 소요)")
    from dart_screener import fetch_corp_codes, _CORP_CACHE_PATH, DartNetworkError

    try:
        mapping = fetch_corp_codes(api_key, force_refresh=True)
    except DartNetworkError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    print(f"[완료] {len(mapping):,}개 기업 코드 저장 → {_CORP_CACHE_PATH}")
    print()
    print("다음 단계:")
    print("  git add dart_corp_codes.json")
    print("  git commit -m \"Add DART corp codes cache\"")
    print("  git push")


if __name__ == "__main__":
    main()
