"""
Routes API pour l'intégration YouTube.

Endpoints :
  GET  /api/youtube/auth-status   → vérifier si authentifié
  POST /api/youtube/auth          → déclencher le flux OAuth (ouvre le navigateur)
  POST /api/youtube/revoke        → révoquer le token (déconnexion)
  GET  /api/youtube/playlists     → lister les playlists de la chaîne
  POST /api/youtube/upload/{job_id} → uploader la vidéo d'un job sur YouTube
  GET  /api/youtube/job/{job_id}  → statut YouTube d'un job (video_id, lien)
"""
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.config import YOUTUBE_TOKEN_PATH
from backend.database import get_connection, row_to_dict
from backend.services.job_runner import get_job

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


# ── Helpers DB ────────────────────────────────────────────────────────────────

def _update_job_youtube(job_id: str, video_id: str, yt_status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET youtube_video_id = ?, youtube_status = ? WHERE id = ?",
            (video_id, yt_status, job_id),
        )
        conn.commit()


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/auth-status")
async def auth_status():
    """Vérifie si un token YouTube valide existe."""
    from backend.services.youtube import is_authenticated
    return {"authenticated": is_authenticated()}


@router.post("/auth")
async def authenticate():
    """
    Déclenche le flux OAuth 2.0.
    Ouvre le navigateur par défaut pour la connexion Google.
    Bloquant jusqu'à ce que l'utilisateur complète l'autorisation.
    """
    def _do_auth():
        from backend.services.youtube import get_credentials
        get_credentials()

    await run_in_threadpool(_do_auth)
    return {"authenticated": True, "message": "Authentification réussie"}


@router.post("/revoke")
async def revoke_token():
    """Supprime le token local (déconnexion YouTube)."""
    if YOUTUBE_TOKEN_PATH.exists():
        YOUTUBE_TOKEN_PATH.unlink()
    return {"revoked": True}


# ── Playlists ─────────────────────────────────────────────────────────────────

@router.get("/playlists")
async def list_playlists():
    """Retourne les playlists de la chaîne connectée."""
    from backend.services.youtube import is_authenticated, get_playlists

    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Non authentifié sur YouTube")

    playlists = await run_in_threadpool(get_playlists)
    return {"playlists": playlists}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload/{job_id}")
async def upload_job_to_youtube(
    job_id: str,
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy: str = Form("private"),
    category_id: str = Form("27"),
    playlist_id: str = Form(""),
    filename: str = Form(""),
    thumbnail: Optional[UploadFile] = File(None),
):
    """
    Upload la vidéo d'un job terminé vers YouTube.

    Paramètres (form-data) :
      - title        : titre de la vidéo YouTube
      - description  : description (peut être multiligne)
      - tags         : tags séparés par des virgules
      - privacy      : "private" | "unlisted" | "public"  (défaut: private)
      - category_id  : ID catégorie YouTube (27 = Education, 22 = People & Blogs)
      - playlist_id  : ID de playlist (optionnel)
      - filename     : nom du fichier mp4 à uploader (ex: final_video_with_overlays.mp4)
      - thumbnail    : fichier image à définir comme miniature (optionnel)
    """
    from backend.services.youtube import is_authenticated, upload_video

    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Non authentifié sur YouTube")

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="La vidéo n'est pas encore prête")

    # Résoudre le chemin de la vidéo
    job_dir = Path(job["output_video_path"]).parent
    if filename:
        video_path = job_dir / filename
    else:
        video_path = Path(job["output_video_path"])

    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier vidéo introuvable : {video_path.name}")

    # Sauvegarder la miniature temporairement si fournie
    thumbnail_path: Path | None = None
    if thumbnail and thumbnail.filename:
        suffix = Path(thumbnail.filename).suffix or ".jpg"
        thumbnail_path = job_dir / f"thumbnail{suffix}"
        thumbnail_path.write_bytes(await thumbnail.read())

    # Parser les tags (virgule-séparés, nettoyés)
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    logs: list[str] = []

    def _upload():
        return upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags_list,
            privacy=privacy,
            category_id=category_id,
            thumbnail_path=thumbnail_path,
            playlist_id=playlist_id if playlist_id else None,
            log_callback=logs.append,
        )

    try:
        video_id = await run_in_threadpool(_upload)
    except Exception as e:
        _update_job_youtube(job_id, "", "failed")
        raise HTTPException(status_code=500, detail=f"Erreur upload YouTube : {e}")
    finally:
        if thumbnail_path and thumbnail_path.exists():
            thumbnail_path.unlink(missing_ok=True)

    _update_job_youtube(job_id, video_id, "uploaded")

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "privacy": privacy,
        "logs": logs,
    }


# ── Statut YouTube d'un job ───────────────────────────────────────────────────

@router.get("/job/{job_id}")
async def youtube_job_status(job_id: str):
    """Retourne le statut YouTube (video_id, url) d'un job."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT youtube_video_id, youtube_status FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    video_id = row["youtube_video_id"]
    return {
        "youtube_video_id": video_id,
        "youtube_status": row["youtube_status"],
        "url": f"https://youtu.be/{video_id}" if video_id else None,
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit" if video_id else None,
    }
