"""
Routes API pour la gestion des jobs.
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.database import get_connection
from backend.services.job_runner import (
    create_job,
    submit_job,
    get_job,
    get_all_jobs,
    delete_job,
    get_job_logs,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("")
async def create_new_job(
    style: str = Form(...),
    script_text: str = Form(...),
    background_video: Optional[UploadFile] = File(None),
    audio_file: Optional[UploadFile] = File(None),
    srt_file: Optional[UploadFile] = File(None),
    # YouTube params (tous optionnels — si présents, auto-upload après pipeline)
    yt_title: str = Form(""),
    yt_description: str = Form(""),
    yt_tags: str = Form(""),
    yt_privacy: str = Form("private"),
    yt_category_id: str = Form("27"),
    yt_playlist_id: str = Form(""),
    yt_language: str = Form("fr"),
    yt_license: str = Form("youtube"),
    yt_embeddable: str = Form("true"),
    yt_thumbnail: Optional[UploadFile] = File(None),
    video_mode: str = Form("dark"),
    boost_audio: str = Form("false"),
):
    if style not in ("full", "simple", "audio_srt"):
        raise HTTPException(status_code=400, detail=f"Style invalide: {style}")

    if style == "simple" and not background_video:
        raise HTTPException(status_code=400, detail="background_video requis pour le style 'simple'")

    if style == "audio_srt" and (not audio_file or not srt_file):
        raise HTTPException(status_code=400, detail="audio_file et srt_file requis pour le style 'audio_srt'")

    extra_files: dict[str, bytes] = {}

    if background_video:
        content = await background_video.read()
        extra_files["background_video.mp4"] = content

    if audio_file:
        suffix = Path(audio_file.filename or "audio.mp3").suffix or ".mp3"
        content = await audio_file.read()
        extra_files[f"voice_audio{suffix}"] = content

    if srt_file:
        content = await srt_file.read()
        extra_files["subtitles.srt"] = content

    # Sauvegarder la miniature YouTube si fournie
    if yt_thumbnail and yt_thumbnail.filename:
        suffix = Path(yt_thumbnail.filename).suffix or ".jpg"
        thumb_content = await yt_thumbnail.read()
        extra_files[f"yt_thumbnail{suffix}"] = thumb_content

    # Construire les métadonnées YouTube (seulement si un titre YouTube est fourni)
    yt_metadata = None
    if yt_title.strip():
        yt_metadata = {
            "title": yt_title.strip(),
            "description": yt_description,
            "tags": yt_tags,
            "privacy": yt_privacy,
            "category_id": yt_category_id,
            "playlist_id": yt_playlist_id,
            "language": yt_language,
            "license": yt_license,
            "embeddable": yt_embeddable.lower() == "true",
        }

    job_id = create_job(style)

    if yt_metadata:
        with get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET youtube_metadata = ? WHERE id = ?",
                (json.dumps(yt_metadata, ensure_ascii=False), job_id),
            )
            conn.commit()

    validated_mode = video_mode if video_mode in ("dark", "light") else "dark"
    submit_job(job_id, style, script_text, extra_files, video_mode=validated_mode, boost_audio=boost_audio.lower() == "true")

    return {"job_id": job_id, "status": "pending"}


@router.get("")
async def list_jobs():
    """Liste tous les jobs triés par date décroissante."""
    return get_all_jobs()


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    """Retourne le statut et les métadonnées d'un job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return job


@router.get("/{job_id}/logs")
async def stream_job_logs(job_id: str, from_line: int = 0):
    """
    Retourne les lignes de log d'un job depuis from_line.
    Utile pour le polling progressif depuis le frontend.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    lines, is_running = get_job_logs(job_id, from_line)
    return {
        "job_id": job_id,
        "lines": lines,
        "total_lines": from_line + len(lines),
        "is_running": is_running,
    }


@router.get("/{job_id}/files")
async def list_job_files(job_id: str):
    """Liste les vidéos MP4 disponibles pour un job terminé."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="La vidéo n'est pas encore prête")

    job_dir = Path(job["output_video_path"]).parent
    files = sorted(
        [f.name for f in job_dir.glob("*.mp4") if f.is_file()],
        key=lambda n: (0 if "overlay" in n else 1, n),
    )
    return {"files": files}


@router.get("/{job_id}/download")
async def download_video(job_id: str, filename: str | None = None):
    """Télécharge une vidéo d'un job terminé. Sans filename, retourne la vidéo principale."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="La vidéo n'est pas encore prête")

    if filename:
        job_dir = Path(job["output_video_path"]).parent
        video_path = job_dir / filename
        if not video_path.exists() or video_path.suffix != ".mp4":
            raise HTTPException(status_code=404, detail="Fichier vidéo introuvable")
    else:
        video_path = Path(job["output_video_path"])
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Fichier vidéo introuvable")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=video_path.name,
    )


@router.delete("/{job_id}")
async def remove_job(job_id: str):
    """Supprime un job et ses fichiers associés."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    if job["status"] == "running":
        raise HTTPException(status_code=400, detail="Impossible de supprimer un job en cours")

    deleted = delete_job(job_id)
    return {"deleted": deleted}
