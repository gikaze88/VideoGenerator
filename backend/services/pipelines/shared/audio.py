"""
Génération audio ElevenLabs, normalisation, merge, boost, mix.
Logique extraite de video_gen_full.py / video_gen_simple.py
"""
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

import requests

from backend.config import (
    AUDIO_EXTENSIONS,
    AUDIO_BOOST_DB,
    BACKGROUND_SONGS_DIR,
    BG_MUSIC_VOLUME,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    TTS_CHUNK_MAX_CHARS,
    VOICE_DELAY_SECONDS,
)
from backend.services.pipelines.shared.utils import (
    get_media_duration,
    log,
    split_text_smart,
)


def generate_audio_chunks(text: str, work_dir: Path, log_file: Path) -> list[Path]:
    """
    Envoie le texte à ElevenLabs par chunks, normalise chaque morceau.
    Retourne la liste des fichiers audio normalisés.
    """
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        raise ValueError("ELEVENLABS_API_KEY et ELEVENLABS_VOICE_ID doivent être définis dans .env")

    api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    chunks = split_text_smart(text, TTS_CHUNK_MAX_CHARS)
    audio_files = []

    for i, chunk in enumerate(chunks, 1):
        log(f"🎙️  Génération audio chunk {i}/{len(chunks)}...", log_file)
        raw_path = work_dir / f"audio_part_{i}.mp3"
        norm_path = work_dir / f"audio_part_{i}_norm.mp3"

        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": chunk,
            "model_id": "eleven_multilingual_v1",
            "voice_settings": {
                "speed": 1.0,
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        max_retries = 3
        response = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    api_url, headers=headers, json=payload, timeout=300
                )
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    wait = attempt * 15
                    log(f"  ⏳ Timeout chunk {i} (tentative {attempt}/{max_retries}), nouvelle tentative dans {wait}s...", log_file)
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"ElevenLabs timeout après {max_retries} tentatives pour le chunk {i} "
                        f"({len(chunk)} chars). Le texte est peut-être trop long ou ElevenLabs est surchargé."
                    )

        if response.status_code != 200:
            try:
                error_detail = response.json()
            except Exception:
                error_detail = response.text
            raise RuntimeError(
                f"ElevenLabs erreur {response.status_code}: {error_detail}"
            )

        raw_path.write_bytes(response.content)
        log(f"  ✅ Audio chunk {i} téléchargé", log_file)

        normalize_audio(raw_path, norm_path, log_file)
        audio_files.append(norm_path)

    return audio_files


def normalize_audio(input_file: Path, output_file: Path, log_file: Path | None = None):
    """Normalise le volume audio avec FFmpeg loudnorm (I=-23 LUFS)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-af", "loudnorm=I=-23:TP=-2:LRA=11",
        str(output_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg normalize error:\n{result.stderr[-500:]}")
    log(f"  ✅ Audio normalisé : {output_file.name}", log_file)


def merge_audio_files(audio_files: list[Path], output: Path, work_dir: Path, log_file: Path | None = None):
    """Fusionne plusieurs fichiers MP3 en un seul."""
    list_file = work_dir / "file_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for part in audio_files:
            abs_path = str(part.resolve()).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-ar", "44100",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge error:\n{result.stderr[-500:]}")
    log(f"✅ Audios fusionnés → {output.name}", log_file)


def boost_audio(input_file: Path, output_file: Path, boost_db: int = AUDIO_BOOST_DB, log_file: Path | None = None):
    """Booste le volume audio de boost_db décibels."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-af", f"volume={boost_db}dB",
        str(output_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg boost error:\n{result.stderr[-500:]}")
    log(f"✅ Audio boosté +{boost_db}dB → {output_file.name}", log_file)


def select_random_background_music() -> Path:
    """Sélectionne aléatoirement un fichier dans background_songs/."""
    if not BACKGROUND_SONGS_DIR.exists():
        raise FileNotFoundError(f"Dossier background_songs introuvable : {BACKGROUND_SONGS_DIR}")
    songs = [
        f for f in BACKGROUND_SONGS_DIR.iterdir()
        if f.suffix.lower() in AUDIO_EXTENSIONS
    ]
    if not songs:
        raise FileNotFoundError("Aucun fichier audio dans background_songs/")
    chosen = random.choice(songs)
    return chosen


def mix_audio_with_background(
    voice_audio: Path,
    bg_music: Path,
    output: Path,
    log_file: Path | None = None,
    voice_delay: int = VOICE_DELAY_SECONDS,
    bg_volume: float = BG_MUSIC_VOLUME,
):
    """
    Mixe la voix (avec délai de voice_delay secondes) et la musique de fond.
    La musique est en boucle et à bg_volume * 100%.
    Durée totale = durée voix + 4s (2s avant + 2s après).
    """
    voice_duration = get_media_duration(voice_audio)
    total_duration = voice_duration + 4

    delay_ms = voice_delay * 1000
    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_audio),
        "-stream_loop", "-1", "-i", str(bg_music),
        "-filter_complex",
        f"[0:a]adelay={delay_ms}|{delay_ms}[a0];"
        f"[1:a]volume={bg_volume}[a1];"
        f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition=3",
        "-t", str(total_duration),
        "-c:a", "aac",
        "-b:a", "192k",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mix error:\n{result.stderr[-500:]}")
    log(f"✅ Audio mixé → {output.name} ({total_duration:.1f}s)", log_file)


def insert_silence_in_audio(
    audio_path: Path,
    output_path: Path,
    pause_points_ms: list[int],
    pause_duration: float,
    work_dir: Path,
    log_file: Path | None = None,
):
    """
    Insère des silences dans l'audio aux points spécifiés (en ms).
    Si aucun point, copie simplement l'audio.
    """
    if not pause_points_ms:
        shutil.copy2(audio_path, output_path)
        log("ℹ️  Aucune pause — audio copié tel quel", log_file)
        return

    sorted_pauses = sorted(pause_points_ms)
    log(f"🔄 Insertion de {len(sorted_pauses)} pause(s) de {pause_duration}s...", log_file)

    silence_file = work_dir / "silence_temp.mp3"
    cmd_silence = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(pause_duration),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(silence_file),
    ]
    subprocess.run(cmd_silence, check=True, capture_output=True)

    segments = []
    prev_time = 0.0

    for i, pause_ms in enumerate(sorted_pauses):
        pause_s = pause_ms / 1000.0
        duration = pause_s - prev_time
        seg_file = work_dir / f"segment_{i}.mp3"

        cmd_seg = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-ss", str(prev_time),
            "-t", str(duration),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(seg_file),
        ]
        subprocess.run(cmd_seg, check=True, capture_output=True)
        segments.append(seg_file)
        segments.append(silence_file)
        prev_time = pause_s

    last_seg = work_dir / "segment_last.mp3"
    cmd_last = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-ss", str(prev_time),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(last_seg),
    ]
    subprocess.run(cmd_last, check=True, capture_output=True)
    segments.append(last_seg)

    concat_list = work_dir / "concat_audio_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{seg.resolve()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_path),
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat error:\n{result.stderr[-500:]}")

    # Nettoyage
    silence_file.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)
    for seg in segments:
        if seg.exists() and seg != silence_file:
            seg.unlink(missing_ok=True)

    log(f"✅ Audio avec {len(sorted_pauses)} pause(s) → {output_path.name}", log_file)
