@echo off
:: Streamlit 감시 스크립트 — 프로세스가 없으면 재시작
tasklist /FI "IMAGENAME eq streamlit.exe" 2>nul | find /I "streamlit.exe" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] streamlit 미실행 확인, 시작 중...
    start /b "" "C:\Users\USER\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe" run "C:\Users\USER\stock_analyzer\app.py" --server.port 8501 --server.headless true
) else (
    echo [%date% %time%] streamlit 정상 실행 중
)
