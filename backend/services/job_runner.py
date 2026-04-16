"""
Gestionnaire de jobs : file d'attente unique, exécution dans un thread de fond.
"""
import json
import traceback
import uuid
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from backend.config import OUTPUTS_DIR
from backend.database import get_connection


# Un seul worker à la fois (usage personnel)
_executor = ThreadPoolExecutor(max_workers=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(style: str) -> str:
    """Crée un job en DB avec statut pending, retourne son ID."""
    job_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO jobs (id, style, status, created_at)
               VALUES (?, ?, 'pending', ?)""",
            (job_id, style, _now()),
        )
        conn.commit()
    return job_id


def submit_job(job_id: str, style: str, script_text: str, extra_files: dict[str, bytes] = None):
    """
    Prépare le dossier du job et le soumet à l'executor.
    extra_files: {"background_video.mp4": bytes, "audio.mp3": bytes, "subtitles.srt": bytes}
    """
    job_dir = OUTPUTS_DIR / job_id
    work_dir = job_dir / "working"
    work_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)

    log_file = job_dir / "pipeline.log"

    # Sauvegarder les fichiers uploadés
    if extra_files:
        for filename, content in extra_files.items():
            (work_dir / filename).write_bytes(content)

    # Sauvegarder le texte du script
    (work_dir / "script_video.txt").write_text(script_text, encoding="utf-8")

    # Mettre à jour le statut
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='pending', log_file=? WHERE id=?",
            (str(log_file), job_id),
        )
        conn.commit()

    _executor.submit(_run_job, job_id, style, script_text, work_dir, job_dir, log_file, extra_files or {})


def _run_job(job_id: str, style: str, script_text: str, work_dir: Path, job_dir: Path, log_file: Path, extra_files: dict):
    """Exécute réellement le pipeline dans le thread de fond."""
    # Marquer comme running
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?",
            (_now(), job_id),
        )
        conn.commit()

    try:
        final_video = _dispatch_pipeline(style, script_text, work_dir, job_dir, log_file, extra_files)

        # Copier la vidéo finale à la racine du dossier job
        dest = job_dir / final_video.name
        if final_video != dest:
            shutil.copy2(final_video, dest)

        title = _extract_title(script_text)

        with get_connection() as conn:
            conn.execute(
                """UPDATE jobs
                   SET status='completed', completed_at=?, output_video_path=?, title=?
                   WHERE id=?""",
                (_now(), str(dest), title, job_id),
            )
            conn.commit()

        # Auto-upload YouTube si des métadonnées ont été fournies
        _try_youtube_upload(job_id, job_dir, work_dir, log_file)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n❌ ERREUR FATALE:\n{error_msg}\n")
        with get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', completed_at=?, error_message=? WHERE id=?",
                (_now(), str(exc), job_id),
            )
            conn.commit()


def _dispatch_pipeline(style: str, script_text: str, work_dir: Path, job_dir: Path, log_file: Path, extra_files: dict) -> Path:
    """Appelle le bon pipeline selon le style."""
    if style == "full":
        from backend.services.pipelines.pipeline_full import run_pipeline_full
        return run_pipeline_full(script_text, work_dir, job_dir, log_file)

    elif style == "simple":
        bg_video = work_dir / "background_video.mp4"
        if not bg_video.exists():
            raise FileNotFoundError("background_video.mp4 manquant pour le style 'simple'")
        from backend.services.pipelines.pipeline_simple import run_pipeline_simple
        return run_pipeline_simple(script_text, bg_video, work_dir, job_dir, log_file)

    elif style == "audio_srt":
        # Chercher le fichier audio et SRT dans work_dir
        audio_files = list(work_dir.glob("*.mp3")) + list(work_dir.glob("*.wav")) + list(work_dir.glob("*.m4a"))
        srt_files = list(work_dir.glob("*.srt"))
        if not audio_files:
            raise FileNotFoundError("Aucun fichier audio .mp3/.wav/.m4a trouvé pour le style 'audio_srt'")
        if not srt_files:
            raise FileNotFoundError("Aucun fichier .srt trouvé pour le style 'audio_srt'")
        # Vidéo de fond optionnelle : si fournie, portrait/paysage sera détecté
        bg_video = work_dir / "background_video.mp4"
        bg_video_arg = bg_video if bg_video.exists() else None
        from backend.services.pipelines.pipeline_audio_srt import run_pipeline_audio_srt
        return run_pipeline_audio_srt(
            script_text, audio_files[0], srt_files[0], work_dir, job_dir, log_file,
            background_video=bg_video_arg,
        )

    else:
        raise ValueError(f"Style inconnu: {style}")


def _try_youtube_upload(job_id: str, job_dir: Path, work_dir: Path, log_file: Path):
    """
    Tente l'auto-upload YouTube si youtube_metadata est présent en DB.
    Choisit la vidéo avec overlays en priorité, sinon la standard.
    Ne lève jamais d'exception (le job reste completed même si l'upload échoue).
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT youtube_metadata FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()

    if not row or not row["youtube_metadata"]:
        return

    try:
        meta = json.loads(row["youtube_metadata"])
    except (json.JSONDecodeError, TypeError):
        return

    from backend.services.youtube import is_authenticated, upload_video

    if not is_authenticated():
        _log_to_file(log_file, "\n⚠️  Auto-upload YouTube ignoré : non authentifié")
        with get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET youtube_status = 'skipped' WHERE id = ?", (job_id,)
            )
            conn.commit()
        return

    # Choisir la vidéo : overlay en priorité, sinon standard, sinon output principal
    mp4_files = sorted(job_dir.glob("*.mp4"), key=lambda f: f.name)
    overlay = next((f for f in mp4_files if "overlay" in f.name), None)
    standard = next((f for f in mp4_files if "standard" in f.name), None)
    video_path = overlay or standard or (mp4_files[0] if mp4_files else None)

    if not video_path:
        _log_to_file(log_file, "\n⚠️  Auto-upload YouTube ignoré : aucune vidéo trouvée")
        return

    # Miniature
    thumb_files = list(work_dir.glob("yt_thumbnail.*"))
    thumbnail_path = thumb_files[0] if thumb_files else None

    tags_list = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]

    _log_to_file(log_file, f"\n📤 Auto-upload YouTube → {video_path.name}")

    try:
        video_id = upload_video(
            video_path=video_path,
            title=meta["title"],
            description=meta.get("description", ""),
            tags=tags_list,
            privacy=meta.get("privacy", "private"),
            category_id=meta.get("category_id", "27"),
            thumbnail_path=thumbnail_path,
            playlist_id=meta.get("playlist_id") or None,
            language=meta.get("language", "fr"),
            license=meta.get("license", "youtube"),
            embeddable=meta.get("embeddable", True),
            log_callback=lambda msg: _log_to_file(log_file, msg),
        )
        with get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET youtube_video_id = ?, youtube_status = 'uploaded' WHERE id = ?",
                (video_id, job_id),
            )
            conn.commit()
        _log_to_file(log_file, f"  ✅ YouTube upload terminé → https://youtu.be/{video_id}")
    except Exception as e:
        _log_to_file(log_file, f"  ❌ YouTube upload échoué : {e}")
        with get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET youtube_status = 'failed' WHERE id = ?", (job_id,)
            )
            conn.commit()


def _log_to_file(log_file: Path, msg: str):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _extract_title(script_text: str) -> str:
    """Extrait le titre depuis le texte du script."""
    import re
    m = re.search(r"Titre\s*:\s*(.+)", script_text, re.IGNORECASE)
    return m.group(1).strip() if m else "Sans titre"


def get_job(job_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_all_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> bool:
    """Supprime un job et son dossier de sortie."""
    job_dir = OUTPUTS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    with get_connection() as conn:
        result = conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
        return result.rowcount > 0


def get_job_logs(job_id: str, from_line: int = 0) -> tuple[list[str], bool]:
    """Retourne les logs d'un job depuis la ligne from_line. (lignes, is_running)"""
    job = get_job(job_id)
    if not job or not job.get("log_file"):
        return [], False

    log_path = Path(job["log_file"])
    if not log_path.exists():
        return [], job["status"] == "running"

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[from_line:], job["status"] == "running"
