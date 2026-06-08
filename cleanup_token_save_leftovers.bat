@echo off
chcp 65001 >nul
echo 토큰 절약 모드 잔여 파일을 삭제합니다.
if exist modules\cost_control.py del /f /q modules\cost_control.py
if exist tests\test_cost_control.py del /f /q tests\test_cost_control.py
if exist __pycache__ rmdir /s /q __pycache__
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo 완료.
pause
