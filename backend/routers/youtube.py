"""
Routes API pour l'intégration YouTube.

Endpoints :
  GET  /api/youtube/auth-status     → vérifier si un token existe
  GET  /api/youtube/auth-url        → générer l'URL d'autorisation OAuth (à ouvrir côté frontend)
  GET  /api/youtube/oauth-callback  → callback Google (échange code ↔ token)
  POST /api/youtube/revoke          → révoquer le token (déconnexion)
  GET  /api/youtube/playlists       → lister les playlists de la chaîne
  POST /api/youtube/upload/{job_id} → uploader la vidéo d'un job sur YouTube
  GET  /api/youtube/job/{job_id}    → statut YouTube d'un job (video_id, lien)
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, HTTPException, UploadFile, Request, Response
from fastapi.concurrency import run_in_threadpool

from backend.config import YOUTUBE_TOKEN_PATH
from backend.database import get_connection
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


@router.get("/auth-url")
async def get_auth_url():
    """
    Génère l'URL d'autorisation OAuth 2.0.
    Le frontend doit ouvrir cette URL dans un nouvel onglet/fenêtre.
    """
    from backend.services.youtube import get_auth_url

    url = get_auth_url()
    return {"url": url}


@router.get("/oauth-callback")
async def oauth_callback(request: Request):
    """
    Callback appelé par Google avec ?code=...
    Échange le code contre un token, le sauvegarde, puis renvoie
    une petite page HTML qui se ferme automatiquement.
    """
    from backend.services.youtube import exchange_code

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Paramètre 'code' manquant")

    try:
        await run_in_threadpool(exchange_code, code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur OAuth YouTube : {e}")

    html = """
<!DOCTYPE html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <title>Connexion YouTube réussie</title>
    <style>
      body { background:#020617; color:#e5e7eb; font-family:system-ui; display:flex;
             align-items:center; justify-content:center; height:100vh; margin:0; }
      .card { padding:1.5rem 2rem; border-radius:0.75rem; background:#020617;
              border:1px solid #1f2937; box-shadow:0 20px 40px rgba(0,0,0,0.7); }
      h1 { font-size:1rem; margin:0 0 .5rem; }
      p { font-size:.85rem; margin:0; color:#9ca3af; }
    </style>
    <script>
      setTimeout(function() { window.close(); }, 2000);
    </script>
  </head>
  <body>
    <div class="card">
      <h1>Connexion YouTube réussie ✅</h1>
      <p>Vous pouvez revenir à l'application. Cette fenêtre va se fermer automatiquement.</p>
    </div>
  </body>
</html>
"""
    return Response(content=html, media_type="text/html")


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
      - filename     : nom du fichier mp4 à uploader (ex: quand_tu_te_sens_seul_overlay.mp4)
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
