"""
AI 종목 리포트 — Google Gemini API로 차트·지표·뉴스를 종합 요약.

공개 앱 비용 방어: 호출부(views/stock.py)에서 버튼 클릭 시에만, 종목별 6시간
캐시로 호출한다. REST 직접 호출이라 추가 패키지가 필요 없다(requests).
"""

import json

import requests

# 무료 티어 권장 모델(2026-10 기준). 더 저렴하게: "gemini-3.5-flash-lite"
GEMINI_MODEL = "gemini-3.8-flash"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 투자자문이 아님을 명시하는 면책 문구 (호출부에서 리포트와 함께 표시)
DISCLAIMER = (
    "본 리포트는 공개 데이터를 AI가 요약한 참고 자료이며, 투자 권유나 자문이 아닙니다. "
    "투자 판단과 책임은 본인에게 있습니다."
)


def _build_prompt(ticker: str, name: str, data: dict) -> str:
    facts = json.dumps(data, ensure_ascii=False, indent=1)
    return (
        "당신은 한국 주식 애널리스트입니다. 아래 '데이터'에 있는 수치만 근거로 "
        f"'{name}({ticker})' 종목의 간결한 한국어 리포트를 작성하세요.\n\n"
        f"[데이터]\n{facts}\n\n"
        "[작성 규칙]\n"
        "- 총 4~5문장. 순서: ① 기술적 흐름(이동평균 배열·RSI·MACD) "
        "② 수급/뉴스 분위기 ③ 종합 관점.\n"
        "- 데이터에 없는 수치나 사실은 절대 지어내지 말 것.\n"
        "- '반드시 매수/매도' 같은 단정 대신 '~로 보입니다', '관망이 필요해 보입니다' 같은 신중한 표현.\n"
        "- 전문용어는 짧게 풀어 초보자도 이해할 수 있게.\n"
        "- 면책 문구는 넣지 말 것(화면에서 별도 표시함)."
    )


def generate_stock_report(
    ticker: str,
    name: str,
    data: dict,
    api_key: str,
    model: str = GEMINI_MODEL,
    timeout: int = 20,
) -> str:
    """Gemini로 리포트 텍스트 생성. 실패 시 사용자용 안내 문자열 반환."""
    if not api_key:
        return ""
    body = {
        "contents": [{"parts": [{"text": _build_prompt(ticker, name, data)}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.post(
            _ENDPOINT.format(model=model), headers=headers, json=body, timeout=timeout
        )
        r.raise_for_status()
        j = r.json()
    except requests.exceptions.HTTPError:
        code = getattr(r, "status_code", "?")
        if code in (401, 403):
            return "⚠️ Gemini API 키가 올바르지 않거나 권한이 없습니다. 키를 확인해 주세요."
        if code == 429:
            return "⚠️ 요청이 많아 잠시 후 다시 시도해 주세요. (무료 한도 초과)"
        return f"⚠️ 리포트 생성 실패 (HTTP {code})."
    except Exception as e:
        return f"⚠️ 리포트를 생성하지 못했습니다: {type(e).__name__}"

    cands = j.get("candidates", [])
    if not cands:
        return "⚠️ 리포트 생성 결과가 비어 있습니다. (안전 필터 또는 빈 응답)"
    parts = cands[0].get("content", {}).get("parts", [])
    text = " ".join(p.get("text", "") for p in parts).strip()
    return text or "⚠️ 리포트 내용을 받지 못했습니다."
