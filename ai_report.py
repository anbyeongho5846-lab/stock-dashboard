"""
AI 종목 리포트 — Google Gemini API로 차트·지표·뉴스를 종합 요약.

공개 앱 비용 방어: 호출부(views/stock.py)에서 버튼 클릭 시에만, 종목별 6시간
캐시로 호출한다. REST 직접 호출이라 추가 패키지가 필요 없다(requests).
"""

import json
import time

import requests

# 무료 티어 모델(2026-10 기준). 3.6-flash는 안정적이고 빠름.
# (최신 3.8-flash는 과부하(503)가 잦아 데모엔 3.6-flash 권장)
GEMINI_MODEL = "gemini-3.6-flash"
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
        "- 5~6문장으로, 아래 내용을 모두 담되 번호는 쓰지 말고 자연스럽게 이어 쓸 것:\n"
        "  (가) 기술적 흐름 — 이동평균 배열·RSI·MACD\n"
        "  (나) 수급·뉴스 분위기\n"
        "  (다) 매수 관점 — 진입을 고려할 때 참고할 점(예: 어느 이동평균선이 지지/저항이 될지, "
        "RSI로 본 과열·과매도 여부, 분할매수로 접근할 구간)\n"
        "  (라) 리스크·주의 요인 — 데이터에서 읽히는 하락·조정 위험(예: 단기 이평선 이탈, "
        "RSI 과열 접근, 뉴스 부정 비중, MACD 약화)\n"
        "  (마) 한 줄 종합\n"
        "- (다) 매수 관점과 (라) 리스크는 각각 최소 한 문장씩 분명히 쓸 것.\n"
        "- 지지선·저항선·리스크는 반드시 '데이터'의 수치(현재가·이동평균·RSI·MACD·뉴스감성)에서 "
        "끌어낼 것. 데이터에 없는 가격대·목표가·사건·재무수치는 절대 지어내지 말 것.\n"
        "- '반드시 매수/매도'·수익 보장 같은 단정은 금지. '~로 보입니다', '~ 가능성이 있습니다', "
        "'유의가 필요합니다' 같은 신중한 표현을 쓸 것.\n"
        "- 전문용어는 짧게 풀어 초보자도 이해할 수 있게.\n"
        "- 면책 문구는 넣지 말 것(화면에서 별도 표시함)."
    )


def generate_stock_report(
    ticker: str,
    name: str,
    data: dict,
    api_key: str,
    model: str = GEMINI_MODEL,
    timeout: int = 30,
) -> str:
    """Gemini로 리포트 텍스트 생성. 실패 시 사용자용 안내 문자열 반환."""
    if not api_key:
        return ""
    body = {
        "contents": [{"parts": [{"text": _build_prompt(ticker, name, data)}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1024,
            # thinking 모델의 사고 토큰이 답변 예산·시간을 잠식하지 않도록 끈다
            # (요약 작업엔 불필요 → 더 빠르고 응답이 잘림 없이 나옴)
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    url = _ENDPOINT.format(model=model)

    # 과부하(503)·타임아웃 시 1회 재시도
    resp = None
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.exceptions.Timeout:
            if attempt == 0:
                continue
            return "⚠️ 응답이 지연됩니다. 잠시 후 다시 시도해 주세요."
        except Exception as e:
            return f"⚠️ 리포트를 생성하지 못했습니다: {type(e).__name__}"
        if resp.status_code == 503 and attempt == 0:
            time.sleep(1.5)
            continue
        break

    if resp is None:
        return "⚠️ 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요."
    if resp.status_code != 200:
        code = resp.status_code
        if code in (401, 403):
            return "⚠️ Gemini API 키가 올바르지 않거나 권한이 없습니다. 키를 확인해 주세요."
        if code == 429:
            return "⚠️ 요청이 많아 잠시 후 다시 시도해 주세요. (무료 한도 초과)"
        if code == 503:
            return "⚠️ AI 모델이 일시적으로 혼잡합니다. 잠시 후 다시 눌러 주세요."
        return f"⚠️ 리포트 생성 실패 (HTTP {code})."

    try:
        j = resp.json()
    except Exception:
        return "⚠️ 응답을 해석하지 못했습니다."

    cands = j.get("candidates", [])
    if not cands:
        return "⚠️ 리포트 생성 결과가 비어 있습니다. (안전 필터 또는 빈 응답)"
    parts = cands[0].get("content", {}).get("parts", [])
    text = " ".join(p.get("text", "") for p in parts).strip()
    return text or "⚠️ 리포트 내용을 받지 못했습니다."
