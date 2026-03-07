"""
Génération et manipulation des fichiers SRT.
Logique extraite de video_gen_full.py / video_gen_simple.py / video_gen_audio_srt.py
"""
import re
import sys
import subprocess
from pathlib import Path

from backend.config import SUBS_GENERATOR_DIR
from backend.services.pipelines.shared.utils import log


def generate_srt(audio_file: Path, output_srt: Path, log_file: Path | None = None) -> Path:
    """
    Génère un fichier SRT via le module subs_generator/srt_generator.py (Whisper).
    """
    log("🔄 Génération SRT avec Whisper...", log_file)

    subs_dir = str(SUBS_GENERATOR_DIR)
    sys.path.insert(0, subs_dir)
    try:
        from srt_generator import generate_srt as _generate_srt  # type: ignore
        result_path = _generate_srt(str(audio_file), str(output_srt))
        log(f"✅ SRT généré → {output_srt.name}", log_file)
        return Path(result_path)
    except Exception as e:
        raise RuntimeError(f"Erreur génération SRT: {e}") from e
    finally:
        if subs_dir in sys.path:
            sys.path.remove(subs_dir)


def parse_srt_file(srt_path: Path) -> list[dict]:
    """Parse un fichier SRT et retourne une liste de sous-titres."""
    content = srt_path.read_text(encoding="utf-8")
    pattern = (
        r'(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> '
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\n((?:.*\n?)+?)(?=\n\d+\n|\Z)'
    )
    subtitles = []
    for match in re.finditer(pattern, content, re.MULTILINE):
        start_h, start_m, start_s, start_ms = map(int, match.groups()[1:5])
        end_h, end_m, end_s, end_ms = map(int, match.groups()[5:9])
        subtitles.append({
            "index": int(match.group(1)),
            "start_time": (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms,
            "end_time": (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms,
            "text": match.group(10).strip(),
        })
    return subtitles


def ms_to_timecode(total_ms: int) -> str:
    """Convertit des millisecondes en format SRT HH:MM:SS,mmm."""
    h = total_ms // (3600 * 1000)
    m = (total_ms % (3600 * 1000)) // (60 * 1000)
    s = (total_ms % (60 * 1000)) // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(subtitles: list[dict], output_path: Path):
    """Écrit une liste de sous-titres dans un fichier SRT."""
    with open(output_path, "w", encoding="utf-8") as f:
        for sub in subtitles:
            f.write(f"{sub['index']}\n")
            f.write(f"{ms_to_timecode(sub['start_time'])} --> {ms_to_timecode(sub['end_time'])}\n")
            f.write(f"{sub['text']}\n\n")


def shift_srt_timing(input_srt: Path, output_srt: Path, delay_seconds: float = 2, log_file: Path | None = None):
    """Décale tous les timecodes SRT de delay_seconds secondes."""
    content = input_srt.read_text(encoding="utf-8")
    delay_ms = int(delay_seconds * 1000)
    pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})'

    def shift(match):
        start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
        end_h, end_m, end_s, end_ms = map(int, match.groups()[4:])
        start_total = (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms + delay_ms
        end_total = (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms + delay_ms
        return f"{ms_to_timecode(start_total)} --> {ms_to_timecode(end_total)}"

    shifted = re.sub(pattern, shift, content)
    output_srt.write_text(shifted, encoding="utf-8")
    log(f"✅ SRT décalé +{delay_seconds}s → {output_srt.name}", log_file)


def detect_prayer_transitions(srt_path: Path) -> list[int]:
    """
    Détecte les phrases de transition vers la prière dans le SRT.
    Retourne une liste de timestamps (en ms) en fin de chaque sous-titre de transition.
    """
    subtitles = parse_srt_file(srt_path)
    patterns = [
        r'maintenant[,\s]+prions(?![,\s]*\w)',
        r'maintenant[,\s]+prions[,\s]+le[,\s]+seigneur(?![,\s]*\w)',
        r'maintenant[,\s]+prions[,\s]+dieu(?![,\s]*\w)',
        r'prions[,\s]+ensemble(?![,\s]*\w)',
        r'prions[,\s]+maintenant(?![,\s]*\w)',
        r'alors[,\s]+prions(?![,\s]*\w)',
    ]
    points = []
    for sub in subtitles:
        text_lower = sub["text"].lower()
        for pat in patterns:
            if re.search(pat, text_lower):
                points.append(sub["end_time"])
                break
    return points


def regroup_srt_by_word_count(
    srt_path: Path,
    output_srt: Path,
    max_words: int = 3,
    log_file: Path | None = None,
):
    """
    Post-traitement SRT : regroupe ou découpe les segments pour respecter max_words mots par sous-titre.
    Utilisé notamment en mode portrait (9:16) où on passe de 5 à 3 mots max.
    Le timing est interpolé proportionnellement au nombre de mots.
    """
    subtitles = parse_srt_file(srt_path)
    result = []
    new_index = 1

    for sub in subtitles:
        words = sub["text"].split()
        if len(words) <= max_words:
            result.append({
                "index": new_index,
                "start_time": sub["start_time"],
                "end_time": sub["end_time"],
                "text": sub["text"],
            })
            new_index += 1
        else:
            # Découpe le segment en sous-segments de max_words mots avec timing interpolé
            total_words = len(words)
            duration = sub["end_time"] - sub["start_time"]
            ms_per_word = duration / total_words
            offset = sub["start_time"]

            for i in range(0, total_words, max_words):
                chunk_words = words[i:i + max_words]
                chunk_start = offset + int(i * ms_per_word)
                chunk_end = offset + int(min((i + max_words), total_words) * ms_per_word)
                result.append({
                    "index": new_index,
                    "start_time": chunk_start,
                    "end_time": chunk_end,
                    "text": " ".join(chunk_words),
                })
                new_index += 1

    write_srt(result, output_srt)
    log(f"✅ SRT regroupé ({max_words} mots max) → {output_srt.name}", log_file)


def adjust_srt_with_pauses(
    srt_path: Path,
    output_srt: Path,
    pause_points_ms: list[int],
    pause_duration_ms: int = 3000,
    log_file: Path | None = None,
):
    """Ajuste les timings SRT en ajoutant des pauses aux points spécifiés."""
    subtitles = parse_srt_file(srt_path)
    sorted_pauses = sorted(pause_points_ms)
    adjusted = []
    for sub in subtitles:
        n_pauses = sum(1 for p in sorted_pauses if p <= sub["start_time"])
        delay = n_pauses * pause_duration_ms
        adjusted.append({
            "index": sub["index"],
            "start_time": sub["start_time"] + delay,
            "end_time": sub["end_time"] + delay,
            "text": sub["text"],
        })
    write_srt(adjusted, output_srt)
    log(f"✅ SRT ajusté avec {len(sorted_pauses)} pause(s) → {output_srt.name}", log_file)
