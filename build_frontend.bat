@echo off
echo ========================================
echo  Build Frontend React (production)
echo ========================================
echo.
cd frontend
npm run build
echo.
echo Build termine dans frontend/dist/
echo Le backend FastAPI servira automatiquement ce dossier.
pause
