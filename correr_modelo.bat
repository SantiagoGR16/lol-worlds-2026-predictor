@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set VPY=%USERPROFILE%\.lolpred\.venv\Scripts\python.exe
if not exist "%VPY%" ( echo Primero ejecuta instalar.bat & pause & exit /b 1 )
"%VPY%" scripts\run_pipeline.py --rapido
"%VPY%" scripts\predict_series.py
"%VPY%" -m pytest -q
pause
