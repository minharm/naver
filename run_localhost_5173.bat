@echo off
chcp 65001 >nul
echo 네이버 블로그 글 자동작성 프로그램을 실행합니다.
echo 접속 주소: http://localhost:5173
streamlit run app.py --server.port 5173
pause
