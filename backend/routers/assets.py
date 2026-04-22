"""
Routes API pour lister les assets disponibles (musiques et vidéos).
"""
from fastapi import APIRouter
from backend.config import BACKGROUND_SONGS_DIR, VIDEOS_DB_DIR, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _count_videos(directory):
    """Compte les fichiers vidéo dans un dossier (non récursif)."""
    if not directory.exists():
        return 0
    return sum(1 for f in directory.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS)


@router.get("")
async def list_assets():
    """Retourne la liste des musiques de fond et vidéos disponibles."""
    songs = []
    if BACKGROUND_SONGS_DIR.exists():
        songs = [
            f.name for f in sorted(BACKGROUND_SONGS_DIR.iterdir())
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]

    dark_dir = VIDEOS_DB_DIR / "videos_db_dark"
    light_dir = VIDEOS_DB_DIR / "videos_db_light"

    return {
        "songs": songs,
        "songs_count": len(songs),
        "videos_dark_count": _count_videos(dark_dir),
        "videos_light_count": _count_videos(light_dir),
    }


@router.get("/health")
async def health_check():
    """Vérifie que les dossiers de ressources sont accessibles."""
    dark_dir = VIDEOS_DB_DIR / "videos_db_dark"
    light_dir = VIDEOS_DB_DIR / "videos_db_light"
    return {
        "videos_db_dark": {
            "path": str(dark_dir),
            "exists": dark_dir.exists(),
            "count": _count_videos(dark_dir),
        },
        "videos_db_light": {
            "path": str(light_dir),
            "exists": light_dir.exists(),
            "count": _count_videos(light_dir),
        },
        "background_songs": {
            "path": str(BACKGROUND_SONGS_DIR),
            "exists": BACKGROUND_SONGS_DIR.exists(),
            "count": sum(1 for f in BACKGROUND_SONGS_DIR.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS)
            if BACKGROUND_SONGS_DIR.exists() else 0,
        },
    }
