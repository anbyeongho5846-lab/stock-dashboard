@echo off
title 주식 분석 대시보드 서버
cd /d C:\Users\USER\stock_analyzer

:loop
echo [%date% %time%] Streamlit 시작 중...
streamlit run app.py --server.port 8501 --server.headless true
echo [%date% %time%] 프로세스 종료됨. 10초 후 재시작...
timeout /t 10 /nobreak >nul
goto loop
