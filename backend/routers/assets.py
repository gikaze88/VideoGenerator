"""
Routes API pour lister les assets disponibles (musiques et vidéos).
"""
from fastapi import APIRouter
from backend.config import BACKGROUND_SONGS_DIR, VIDEOS_DB_DIR, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
async def list_assets():
    """Retourne la liste des musiques de fond et vidéos disponibles."""
    songs = []
    if BACKGROUND_SONGS_DIR.exists():
        songs = [
            f.name for f in sorted(BACKGROUND_SONGS_DIR.iterdir())
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]

    videos = []
    if VIDEOS_DB_DIR.exists():
        videos = [
            f.name for f in sorted(VIDEOS_DB_DIR.iterdir())
            if f.suffix.lower() in VIDEO_EXTENSIONS
        ]

    return {
        "songs": songs,
        "songs_count": len(songs),
        "videos": videos,
        "videos_count": len(videos),
    }


@router.get("/health")
async def health_check():
    """Vérifie que les dossiers de ressources sont accessibles."""
    return {
        "videos_db": {
            "path": str(VIDEOS_DB_DIR),
            "exists": VIDEOS_DB_DIR.exists(),
            "count": sum(1 for f in VIDEOS_DB_DIR.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS)
            if VIDEOS_DB_DIR.exists() else 0,
        },
        "background_songs": {
            "path": str(BACKGROUND_SONGS_DIR),
            "exists": BACKGROUND_SONGS_DIR.exists(),
            "count": sum(1 for f in BACKGROUND_SONGS_DIR.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS)
            if BACKGROUND_SONGS_DIR.exists() else 0,
        },
    }
