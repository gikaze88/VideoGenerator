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


def _find_phrase_in_srt(phrase_words: list[str], subtitles: list[dict]) -> int | None:
    """
    Cherche une liste de mots dans les sous-titres avec une fenêtre glissante de 2.
    Retourne l'index du sous-titre qui contient la fin de la phrase (couverture >= 70 %).
    """
    if not phrase_words:
        return None

    def norm(text: str) -> set[str]:
        return set(re.sub(r"[^a-zàâäéèêëîïôùûüç]", " ", text.lower()).split())

    phrase_set = norm(" ".join(phrase_words))
    if not phrase_set:
        return None

    for i, sub in enumerate(subtitles):
        window = sub["text"]
        if i + 1 < len(subtitles):
            window += " " + subtitles[i + 1]["text"]
        window_set = norm(window)
        coverage = len(phrase_set & window_set) / len(phrase_set)
        if coverage >= 0.7:
            # Determine if the phrase ends in the next subtitle
            if i + 1 < len(subtitles):
                next_set = norm(subtitles[i + 1]["text"])
                if phrase_words[-1].lower() in next_set:
                    return i + 1
            return i

    return None


# Transition patterns — ordered from most specific to least specific.
# No negative lookahead: actual context filtering is done by the callers.
_PRAYER_TRIGGER_PATTERNS = [
    r'maintenant[,\s;:]+prions\b',
    r'prions\s+(?:le\s+)?seigneur\b',
    r'prions\s+(?:notre\s+)?dieu\b',
    r'alors[,\s]+prions\b',
    r'prions[,\s]+maintenant\b',
    r'prions[,\s]+ensemble\b',
]


def detect_prayer_transitions(
    srt_path: Path,
    script_text: str | None = None,
    log_file: Path | None = None,
) -> list[int]:
    """
    Détecte les phrases de transition vers la prière.

    Stratégie :
      1. Si script_text fourni (méthode principale) : recherche dans le texte source
         avant TTS, insensible au regroupement Whisper. Une garde sur les frontières
         de phrases évite les faux positifs (ex : "pendant que nous prions ensemble"
         est ignoré car il n'est pas en début de phrase). Le timestamp est ensuite
         localisé dans le SRT par matching de mots sur une fenêtre de 2 sous-titres.
      2. Fallback SRT : fenêtre glissante de 2 sous-titres adjacents avec une garde
         sur les contextes subordonnés pour le pattern "prions ensemble".

    Retourne une liste de timestamps (en ms) en fin de phrase de transition.
    """
    subtitles = parse_srt_file(srt_path)
    if not subtitles:
        return []

    points: list[int] = []

    if script_text:
        # ── Méthode 1 : détection dans le texte source ────────────────────────
        text_lower = script_text.lower()
        for pat in _PRAYER_TRIGGER_PATTERNS:
            for m in re.finditer(pat, text_lower):
                # Accepter uniquement si la phrase est en début de "phrase"
                # (après une ponctuation finale ou un saut de ligne, ou en tout début)
                before = script_text[max(0, m.start() - 80):m.start()].rstrip()
                at_boundary = m.start() < 50 or bool(re.search(r'[.!?:\n]\s*$', before))
                if not at_boundary:
                    log(f"  ⏩ Ignoré (non-frontière) : '{m.group()}'", log_file)
                    continue

                phrase_words = re.sub(
                    r"[^a-zàâäéèêëîïôùûüç\s]", "", m.group().lower()
                ).split()
                sub_idx = _find_phrase_in_srt(phrase_words, subtitles)
                if sub_idx is not None:
                    t = subtitles[sub_idx]["end_time"]
                    if not any(abs(t - p) < 2000 for p in points):
                        points.append(t)
                        log(
                            f"  🙏 Transition prière (script) : '{m.group()}' → {t / 1000:.2f}s",
                            log_file,
                        )
                else:
                    log(
                        f"  ⚠️  Transition '{m.group()}' détectée dans le script "
                        f"mais non localisée dans le SRT",
                        log_file,
                    )

    if not points:
        # ── Méthode 2 : fallback SRT avec fenêtre glissante de 2 sous-titres ─
        if script_text:
            log("  🔍 Fallback SRT (fenêtre glissante)...", log_file)
        for i, sub in enumerate(subtitles):
            window_text = sub["text"]
            if i + 1 < len(subtitles):
                window_text += " " + subtitles[i + 1]["text"]
            text_lower = window_text.lower()
            for pat in _PRAYER_TRIGGER_PATTERNS:
                m = re.search(pat, text_lower)
                if not m:
                    continue
                # Pour "prions ensemble", rejeter si précédé d'un contexte subordonné
                if "ensemble" in pat:
                    before_match = text_lower[: m.start()].rstrip()
                    if re.search(r'\b(que|pendant|afin|pour)\b\s*\w*\s*$', before_match):
                        continue
                t = sub["end_time"]
                if not any(abs(t - p) < 2000 for p in points):
                    points.append(t)
                    log(
                        f"  🙏 Transition prière (SRT) : '{window_text.strip()[:60]}' → {t / 1000:.2f}s",
                        log_file,
                    )
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
