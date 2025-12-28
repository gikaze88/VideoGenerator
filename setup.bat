@echo off
REM ========================================
REM SagesseDuChrist - Setup Script for Windows
REM ========================================

echo.
echo ========================================
echo SagesseDuChrist - Video Generator Setup
echo ========================================
echo.

REM Check Python version
echo [1/8] Checking Python version
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.10-3.12
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,10) and sys.version_info < (3,13) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python version must be between 3.10 and 3.12
    python --version
    pause
    exit /b 1
)
echo ✓ Python version OK
echo.

REM Check FFmpeg
echo [2/8] Checking FFmpeg installation
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: FFmpeg not found
    echo Please install FFmpeg:
    echo   - Option 1: choco install ffmpeg
    echo   - Option 2: scoop install ffmpeg
    echo   - Option 3: Download from https://ffmpeg.org/download.html
    echo.
    pause
) else (
    echo ✓ FFmpeg found
    echo.
)

REM Create virtual environment
echo [3/8] Creating virtual environment
if exist venv (
    echo Virtual environment already exists
) else (
    python -m venv venv
    echo ✓ Virtual environment created
)
echo.

REM Activate virtual environment
echo [4/8] Activating virtual environment
call venv\Scripts\activate.bat
echo ✓ Virtual environment activated
echo.

REM Upgrade pip
echo [5/8] Upgrading pip
python -m pip install --upgrade pip
echo ✓ pip upgraded
echo.

REM Install dependencies
echo [6/8] Installing dependencies
echo.
echo Do you have an NVIDIA GPU and want CUDA support?
echo   1. Yes - Install with CUDA 12.1 (Recommended for NVIDIA GPUs)
echo   2. No  - Install CPU version only
echo.
set /p gpu_choice="Enter your choice (1 or 2): "

if "%gpu_choice%"=="1" (
    echo.
    echo Installing PyTorch with CUDA 12.1 support
    echo This may take 10-15 minutes
    echo.
    pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install PyTorch with CUDA
        pause
        exit /b 1
    )
    echo ✓ PyTorch with CUDA 12.1 installed
    echo.
    echo Installing remaining dependencies (versions exactes testees)
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo ✓ All dependencies installed with CUDA support
    echo.
    echo Verifying CUDA installation
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"
    echo.
) else (
    echo.
    echo Installing CPU version (versions exactes testees)
    echo This may take 5-10 minutes
    echo.
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo ✓ Dependencies installed (CPU version)
    echo.
)

REM Create directory structure
echo [7/8] Creating directory structure
if not exist videos_db mkdir videos_db
if not exist videos_db\videos_db_light mkdir videos_db\videos_db_light
if not exist videos_db\videos_db_dark mkdir videos_db\videos_db_dark
if not exist background_songs mkdir background_songs
if not exist working_dir mkdir working_dir
if not exist working_dir_audio_srt mkdir working_dir_audio_srt
if not exist working_dir_simple mkdir working_dir_simple
if not exist working_dir_shorts mkdir working_dir_shorts
if not exist working_dir_full_local mkdir working_dir_full_local

REM Create .gitkeep files
type nul > videos_db\.gitkeep
type nul > videos_db\videos_db_light\.gitkeep
type nul > videos_db\videos_db_dark\.gitkeep
type nul > background_songs\.gitkeep
type nul > working_dir\.gitkeep
type nul > working_dir_audio_srt\.gitkeep
type nul > working_dir_simple\.gitkeep
type nul > working_dir_shorts\.gitkeep
type nul > working_dir_full_local\.gitkeep

echo ✓ Directory structure created
echo.

REM Create .env file if not exists
echo [8/8] Setting up environment variables
if not exist .env (
    copy env.example .env >nul 2>&1
    echo ✓ .env file created from template
    echo.
    echo IMPORTANT: Edit .env file and add your API keys:
    echo   - ELEVENLABS_API_KEY
    echo   - ELEVENLABS_VOICE_ID
    echo.
) else (
    echo .env file already exists
    echo.
)

REM Summary
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Installation Summary:
if "%gpu_choice%"=="1" (
    echo   ✓ Python environment with CUDA 12.1 support
    echo   ✓ PyTorch GPU acceleration enabled
) else (
    echo   ✓ Python environment (CPU version)
    echo   ℹ To enable GPU later, see INSTALLATION_GUIDE.md
)
echo   ✓ All dependencies installed
echo   ✓ Directory structure created
echo   ✓ Environment variables template created
echo.
echo Next steps:
echo   1. Edit .env file and add your API keys:
echo      - ELEVENLABS_API_KEY (REQUIRED)
echo      - ELEVENLABS_VOICE_ID (REQUIRED)
echo.
echo   2. Install Montserrat fonts (see INSTALLATION_GUIDE.md)
echo.
echo   3. Add resources:
echo      - Background videos to videos_db/videos_db_light/
echo      - Background music to background_songs/
echo.
echo   4. Test the installation:
echo      python -c "import torch, whisper, requests; print('All imports OK')"
echo.
echo   5. Run your first video:
echo      python Video_Generator_Full_Light_Intelligent_Final.py
echo.
echo To activate the virtual environment later:
echo   venv\Scripts\activate
echo.
echo For detailed documentation, see:
echo   - README.md (Getting started)
echo   - INSTALLATION_GUIDE.md (Complete guide)
echo   - QUICK_START.md (Quick reference)
echo   - VERSIONS.md (Version details)
echo.
pause

