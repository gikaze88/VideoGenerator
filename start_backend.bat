@echo off
echo ========================================
echo  SagesseDuChrist - Backend FastAPI
echo ========================================
echo.

echo Verification du port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 "') do (
    echo Port 8000 occupe par PID %%a, liberation...
    taskkill /PID %%a /F >nul 2>&1
)

echo Demarrage du serveur sur http://0.0.0.0:8000
echo Accessible depuis votre telephone via http://[IP-PC]:8000
echo.
echo Documentation API : http://localhost:8000/docs
echo.

cd /d "%~dp0"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
