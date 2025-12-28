#!/bin/bash
# ========================================
# SagesseDuChrist - Setup Script for Linux/macOS
# ========================================

set -e  # Exit on error

echo ""
echo "========================================"
echo "SagesseDuChrist - Video Generator Setup"
echo "========================================"
echo ""

# Check Python version
echo "[1/8] Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.10-3.12"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.10"
MAX_VERSION="3.13"

if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]] || \
   [[ "$(printf '%s\n' "$MAX_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$PYTHON_VERSION" ]]; then
    echo "ERROR: Python version must be between 3.10 and 3.12"
    echo "Current version: $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python version OK: $PYTHON_VERSION"
echo ""

# Check FFmpeg
echo "[2/8] Checking FFmpeg installation..."
if ! command -v ffmpeg &> /dev/null; then
    echo "WARNING: FFmpeg not found"
    echo "Please install FFmpeg:"
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "  sudo apt install ffmpeg"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  brew install ffmpeg"
    fi
    echo ""
    read -p "Press Enter to continue..."
else
    echo "✓ FFmpeg found"
    echo ""
fi

# Create virtual environment
echo "[3/8] Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists"
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "[4/8] Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "[5/8] Upgrading pip..."
pip install --upgrade pip
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "[6/8] Installing dependencies..."
echo ""
echo "Do you have an NVIDIA GPU and want CUDA support?"
echo "  1. Yes - Install with CUDA 12.1 (Recommended for NVIDIA GPUs)"
echo "  2. No  - Install CPU version only"
echo ""
read -p "Enter your choice (1 or 2): " gpu_choice

if [ "$gpu_choice" == "1" ]; then
    echo ""
    echo "Installing PyTorch with CUDA 12.1 support..."
    echo "This may take 10-15 minutes..."
    echo ""
    pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install PyTorch with CUDA"
        exit 1
    fi
    echo "✓ PyTorch with CUDA 12.1 installed"
    echo ""
    echo "Installing remaining dependencies (versions exactes testées)..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies"
        exit 1
    fi
    echo "✓ All dependencies installed with CUDA support"
    echo ""
    echo "Verifying CUDA installation..."
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"
    echo ""
else
    echo ""
    echo "Installing CPU version (versions exactes testées)..."
    echo "This may take 5-10 minutes..."
    echo ""
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies"
        exit 1
    fi
    echo "✓ Dependencies installed (CPU version)"
    echo ""
fi

# Create directory structure
echo "[7/8] Creating directory structure..."
mkdir -p videos_db/videos_db_light
mkdir -p videos_db/videos_db_dark
mkdir -p background_songs
mkdir -p working_dir
mkdir -p working_dir_audio_srt
mkdir -p working_dir_simple
mkdir -p working_dir_shorts
mkdir -p working_dir_full_local

# Create .gitkeep files
touch videos_db/.gitkeep
touch videos_db/videos_db_light/.gitkeep
touch videos_db/videos_db_dark/.gitkeep
touch background_songs/.gitkeep
touch working_dir/.gitkeep
touch working_dir_audio_srt/.gitkeep
touch working_dir_simple/.gitkeep
touch working_dir_shorts/.gitkeep
touch working_dir_full_local/.gitkeep

echo "✓ Directory structure created"
echo ""

# Create .env file if not exists
echo "[8/8] Setting up environment variables..."
if [ ! -f .env ]; then
    cp env.example .env 2>/dev/null || true
    echo "✓ .env file created from template"
    echo ""
    echo "IMPORTANT: Edit .env file and add your API keys:"
    echo "  - ELEVENLABS_API_KEY"
    echo "  - ELEVENLABS_VOICE_ID"
    echo ""
else
    echo ".env file already exists"
    echo ""
fi

# Summary
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Installation Summary:"
if [ "$gpu_choice" == "1" ]; then
    echo "  ✓ Python environment with CUDA 12.1 support"
    echo "  ✓ PyTorch GPU acceleration enabled"
else
    echo "  ✓ Python environment (CPU version)"
    echo "  ℹ To enable GPU later, see INSTALLATION_GUIDE.md"
fi
echo "  ✓ All dependencies installed"
echo "  ✓ Directory structure created"
echo "  ✓ Environment variables template created"
echo ""
echo "Next steps:"
echo "  1. Edit .env file and add your API keys:"
echo "     - ELEVENLABS_API_KEY (REQUIRED)"
echo "     - ELEVENLABS_VOICE_ID (REQUIRED)"
echo ""
echo "  2. Install Montserrat fonts (see INSTALLATION_GUIDE.md)"
echo ""
echo "  3. Add resources:"
echo "     - Background videos to videos_db/videos_db_light/"
echo "     - Background music to background_songs/"
echo ""
echo "  4. Test the installation:"
echo "     python -c \"import torch, whisper, requests; print('All imports OK')\""
echo ""
echo "  5. Run your first video:"
echo "     python Video_Generator_Full_Light_Intelligent_Final.py"
echo ""
echo "To activate the virtual environment later:"
echo "  source venv/bin/activate"
echo ""
echo "For detailed documentation, see:"
echo "  - README.md (Getting started)"
echo "  - INSTALLATION_GUIDE.md (Complete guide)"
echo "  - QUICK_START.md (Quick reference)"
echo "  - VERSIONS.md (Version details)"
echo ""

