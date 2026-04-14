@echo off
echo ========================================
echo  SagesseDuChrist - Frontend React (DEV)
echo ========================================
echo.

echo Verification du port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 "') do (
    echo Port 5173 occupe par PID %%a, liberation...
    taskkill /PID %%a /F >nul 2>&1
)

echo Demarrage du frontend sur http://localhost:5173
echo Accessible depuis votre telephone via http://[IP-PC]:5173
echo Le backend doit etre lance sur le port 8000.
echo.

cd /d "%~dp0\frontend"
npm run dev
pause
