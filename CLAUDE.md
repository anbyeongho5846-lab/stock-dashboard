# 주식 분석 대시보드 — 프로젝트 현황

## 앱 접속 URL
https://stock-dashboard-xsn49fz4eyx8qgcv6i3lcp.streamlit.app

## 기술 스택
- **프론트/백엔드**: Streamlit 1.57.0
- **데이터**: pykrx(국내, Naver엔드포인트), yfinance(미국 + 국내 fallback)
- **네이버 스크래핑**: ranking.py, sector.py (requests + pd.read_html)
- **포트폴리오 DB**: Supabase (PostgreSQL) — `portfolio` 테이블
- **배포**: Streamlit Community Cloud (GitHub 자동 배포)
- **저장소**: https://github.com/anbyeongho5846-lab/stock-dashboard

## 파일 구조
```
stock_analyzer/
├── app.py                  # 메인 Streamlit 앱 (11개 페이지 + 라우팅)
├── analyzer.py             # 종목 분석 (캔들차트 + 기술지표)
├── backtester.py           # 백테스팅
├── compare.py              # 전략 비교
├── optimizer.py            # MA 최적화
├── fundamental.py          # 기업 기본 분석 (yfinance/pykrx)
├── dart_screener.py        # DART 기본적 분석 스크리너 (EPS/BPS/PER/PBR 밴드)
├── ownership.py            # 투자자 동향
├── ranking.py              # 시장 현황 (네이버 스크래핑)
├── sector.py               # 섹터/테마 (네이버 스크래핑)
├── scanner.py              # 종목 스캐너
├── virtual_portfolio.py    # 가상 투자 (Supabase 저장)
├── kr_tickers.json         # 국내 종목 DB (KOSPI+KOSDAQ 3,957개)
├── dart_corp_codes.json    # DART 고유번호 캐시 (자동생성, 7일 TTL)
├── requirements.txt        # Python 패키지
├── runtime.txt             # python-3.11 (클라우드 버전 고정)
└── .streamlit/
    ├── config.toml         # 다크테마 설정
    └── secrets.toml        # 로컬 시크릿 (gitignore)
```

## 현재 페이지 목록 (app.py 라우팅)
| 페이지 | 함수 | 데이터 소스 |
|---|---|---|
| 🏠 시장 현황 | show_market() | 네이버 스크래핑 (30분 캐시) |
| 📈 종목 분석 | show_analyzer() | pykrx → yfinance .KS fallback |
| 🔄 백테스팅 | show_backtest() | yfinance |
| ⚖️ 전략 비교 | show_compare() | yfinance |
| 🔍 MA 최적화 | show_optimizer() | yfinance |
| 🏢 기업 분석 | show_fundamental() | pykrx → yfinance .KS fallback |
| 👥 투자자 동향 | show_ownership() | pykrx |
| 🗂️ 섹터/테마 | show_sector() | 네이버 스크래핑 (30분 캐시) |
| 📡 종목 스캐너 | show_scanner() | yfinance |
| 📊 DART 스크리너 | show_dart_screener() | Open DART API + yfinance |
| 💰 가상 투자 | show_virtual_portfolio() | Supabase + yfinance |

## 중요 설정값 (app.py)
```python
# 네이버 스크래핑 캐시 — 30분 (IP차단 방지)
@st.cache_data(ttl=1800)
def cached_rankings(market):  # ranking.py
def cached_sector(type_):     # sector.py

# 주가 캐시 — 1시간
@st.cache_data(ttl=3600)
def cached_stock(...)         # analyzer.py
def cached_fundamental(...)   # fundamental.py
```

## 한국 주식 데이터 조회 전략
```python
# pykrx가 클라우드에서 차단되는 경우 yfinance .KS/.KQ로 자동 fallback
# analyzer.py / fundamental.py / virtual_portfolio.py 모두 동일 패턴:
try:
    df = krx.get_market_ohlcv_by_date(...)  # pykrx (로컬)
    if not df.empty: return df
except:
    pass
# fallback
for suffix in [".KS", ".KQ"]:
    df = yf.download(f"{ticker}{suffix}", ...)
    if not df.empty: return df
```

## Streamlit Cloud 시크릿 설정
```toml
# share.streamlit.io → Settings → Secrets
[supabase]
url = "https://xxxx.supabase.co"
key = "eyJhbGciOi..."

[dart]
api_key = "..."   # https://opendart.fss.or.kr 에서 발급
```

## DART 스크리너 캐시 구조
- `dart_corp_codes.json`: DART 고유번호 매핑 (7일 TTL, 자동 갱신)
  - key: 종목코드(6자리), value: DART corp_code(8자리)
- Streamlit `@st.cache_data(ttl=3600)`: 재무/주가 데이터 1시간 캐시

## DART API 엔드포인트 (dart_screener.py)
- `corpCode.xml` — 전체 기업 고유번호 (ZIP 다운로드)
- `fnlttSinglAcntAll.json` — 단일회사 전체 재무제표 (연결/별도)
  - `fs_div=CFS` 우선, 없으면 `OFS` fallback
  - `reprt_code=11011` 사업보고서만 사용
  - 1회 호출로 당기/전기/전전기 3년치 추출 (thstrm/frmtrm/bfefrmtrm)
- `company.json` — 기업명 조회

## Supabase 테이블 구조
```sql
CREATE TABLE portfolio (
  id      TEXT PRIMARY KEY DEFAULT 'default',
  data    JSONB NOT NULL,
  updated TIMESTAMPTZ DEFAULT NOW()
);
```

## 코드 배포 방법
```powershell
cd C:\Users\USER\stock_analyzer
git add .
git commit -m "수정 내용"
git push
# 2~3분 후 Streamlit Cloud 자동 배포
```

## 알려진 이슈 / 제약사항
- **네이버 IP 차단**: 클라우드(미국) 서버에서 네이버 금융 과다 요청 시 일시 차단
  → 해결: 캐시 30분, UptimeRobot 비활성화
- **pykrx KRX API**: 클라우드에서 KRX 인증 실패 (PER/PBR 등 일부 데이터 미제공)
  → 해결: yfinance .KS fallback
- **국내 기업 재무 데이터**: yfinance .KS로 제한적 제공 (정확한 분기 EPS/BPS 없음)
  → 예정: Open DART API 연동으로 해결

## 다음 작업 (Next Task)
**DART 스크리너 배포 후 개선 아이디어**
- 분기 데이터 지원 (reprt_code 11012/11013/11014)
- 배당수익률 필터 추가 (DART 배당 API)
- 시가총액 구간 필터 (대형주/중형주/소형주)
- PDF 리포트 다운로드
