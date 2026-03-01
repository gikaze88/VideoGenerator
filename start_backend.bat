@echo off
echo ========================================
echo  SagesseDuChrist - Backend FastAPI
echo ========================================
echo.
echo Demarrage du serveur sur http://0.0.0.0:8000
echo Accessible depuis votre telephone via http://[IP-PC]:8000
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
