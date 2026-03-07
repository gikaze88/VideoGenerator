"""
Utilitaires partagés entre tous les pipelines.
Logique extraite de video_gen_full.py / video_gen_simple.py / video_gen_audio_srt.py
"""
import re
import subprocess
from pathlib import Path


def extract_title_and_script(text: str) -> tuple[str, str]:
    """
    Sépare le titre et le corps du script depuis le texte brut.
    Format attendu :
        Titre: ...
        
        Transcript:
        <corps du script>
    Retourne (titre, corps_du_script).
    """
    match = re.search(r"Transcript:\s*(.*)", text, re.DOTALL)
    if not match:
        raise ValueError("'Transcript:' introuvable dans le texte fourni.")
    script_body = match.group(1).strip()
    title_section = text[: match.start()].strip()

    # Extraire la valeur après "Titre:" si présente
    title_match = re.search(r"Titre\s*:\s*(.+)", title_section, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else title_section
    return title, script_body


def clean_script(text: str) -> str:
    """
    Nettoie le script :
    - Supprime les timestamps inline (0:15)
    - Normalise les espaces
    - Ajoute un espace après les points majuscules
    """
    text = re.sub(r'\(\d{1,2}:\d{2}\)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'([a-zA-Z])\.([A-Z])', r'\1. \2', text)
    return text


def split_text_smart(text: str, max_length: int = 4900) -> list[str]:
    """
    Découpe le texte en chunks sans couper les phrases.
    """
    chunks = []
    while len(text) > max_length:
        split_index = text.rfind(".", 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(text[: split_index + 1].strip())
        text = text[split_index + 1:].strip()
    if text:
        chunks.append(text.strip())
    return chunks


def get_media_duration(path: str | Path) -> float:
    """Retourne la durée d'un fichier audio/vidéo en secondes via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return float(result.stdout.decode().strip())


def get_video_dimensions(path: str | Path) -> tuple[int, int]:
    """Retourne (width, height) d'une vidéo via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    raw = result.stdout.decode().strip()
    w, h = raw.split("x")
    return int(w), int(h)


def is_portrait_video(path: str | Path) -> bool:
    """Retourne True si la vidéo est en format portrait (hauteur > largeur, ratio ≈ 9:16)."""
    w, h = get_video_dimensions(path)
    return h > w


def escape_ffmpeg_path_windows(path: str | Path) -> str:
    """
    Échappe un chemin Windows pour l'utiliser dans un filtre FFmpeg subtitles=.
    Ex: C:\foo\bar.srt → C\:/foo/bar.srt
    """
    abs_path = str(Path(path).resolve())
    if len(abs_path) > 1 and abs_path[1] == ":":
        drive = abs_path[0]
        rest = abs_path[2:].replace("\\", "/")
        return drive + "\\:" + rest
    return abs_path.replace("\\", "/")


def log(message: str, log_file: Path | None = None):
    """Écrit un message dans le log file et l'affiche."""
    print(message, flush=True)
    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")
