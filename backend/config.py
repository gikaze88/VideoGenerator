"""
Configuration centrale de l'application.
Tous les chemins absolus sont définis ici — modifiez ce fichier selon votre environnement.
"""
import os
from pathlib import Path

# Racine du projet (dossier contenant backend/, frontend/, videos_db/, etc.)
PROJECT_ROOT = Path(__file__).parent.parent

# Ressources locales (restent sur le PC, jamais déplacées)
VIDEOS_DB_DIR = PROJECT_ROOT / "videos_db"
BACKGROUND_SONGS_DIR = PROJECT_ROOT / "background_songs"
SUBS_GENERATOR_DIR = PROJECT_ROOT / "subs_generator"

# Dossier de sortie de l'application (videos finales + working dirs)
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Base de données SQLite
DATABASE_PATH = PROJECT_ROOT / "backend" / "jobs.db"

# Polices Montserrat (Windows)
FONT_REGULAR = "C:/Windows/Fonts/montserrat-regular.ttf"
FONT_BOLD = "C:/Windows/Fonts/montserrat-bold.ttf"
FONT_EXTRALIGHT = "C:/Windows/Fonts/montserrat-extralight.ttf"

# Paramètres ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_API_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

# Extensions de fichiers supportées
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

# Paramètres du pipeline
VOICE_DELAY_SECONDS = 2       # Délai voix en secondes
PRAYER_PAUSE_DURATION = 3.0   # Durée des silences de prière en secondes
AUDIO_BOOST_DB = 10           # Boost audio en dB
BG_MUSIC_VOLUME = 0.2         # Volume musique de fond (0-1)
TTS_CHUNK_MAX_CHARS = 4900    # Taille max des chunks ElevenLabs
