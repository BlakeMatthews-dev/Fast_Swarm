@echo off
set "SCRIPT_DIR=%~dp0"

echo ========================================
echo Starting CoinSwarm FastAPI
echo ========================================

:: Launch dashboard
echo Opening: http://localhost:8000/dashboard
start http://localhost:8000/dashboard

:: Launch Swagger docs
echo Opening: http://localhost:8000/docs
start http://localhost:8000/docs

:: Start Server
echo Starting uvicorn...
:: Run from src directory so Fast_Swarm package imports work
cd /d "%SCRIPT_DIR%src"
:: Set PYTHONPATH to src directory so Fast_Swarm is importable
set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"
echo PYTHONPATH=%PYTHONPATH%
python -m uvicorn Fast_Swarm.Main:app --reload

pause
