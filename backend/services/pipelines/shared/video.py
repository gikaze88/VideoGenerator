"""
Génération et encodage vidéo avec FFmpeg.
Logique extraite de video_gen_full.py / video_gen_simple.py / video_gen_audio_srt.py
"""
import json
import random
import re
import subprocess
from pathlib import Path

from backend.config import VIDEO_EXTENSIONS, VIDEOS_DB_DIR, FONT_REGULAR, FONT_EXTRALIGHT
from backend.services.pipelines.shared.utils import get_media_duration, log, escape_ffmpeg_path_windows


def normalize_video(input_video: Path, output_video: Path, log_file: Path | None = None) -> bool:
    """
    Normalise une vidéo à 1920x1080, 30fps, H264.
    Essaie NVENC → QSV → CPU.
    """
    base_vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    cmds = [
        ["ffmpeg", "-y", "-i", str(input_video),
         "-c:v", "h264_nvenc", "-preset", "fast", "-profile:v", "high",
         "-cq", "23", "-rc:v", "vbr", "-maxrate", "8M", "-bufsize", "16M",
         "-vf", base_vf, "-pix_fmt", "yuv420p", "-r", "30", "-an",
         "-movflags", "+faststart", str(output_video)],
        ["ffmpeg", "-y", "-hwaccel", "qsv", "-i", str(input_video),
         "-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "20",
         "-look_ahead", "1", "-vf", "scale_qsv=1920:1080",
         "-pix_fmt", "nv12", "-r", "30", "-an",
         "-movflags", "+faststart", str(output_video)],
        ["ffmpeg", "-y", "-i", str(input_video),
         "-c:v", "libx264", "-preset", "faster", "-crf", "20",
         "-threads", "0", "-vf", base_vf,
         "-pix_fmt", "yuv420p", "-r", "30", "-an", str(output_video)],
    ]
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode == 0:
                return True
        except Exception:
            continue
    log(f"  ❌ Normalisation échouée pour {input_video.name}", log_file)
    return False


def generate_background_from_videos_db(
    target_duration: float,
    output_video: Path,
    work_dir: Path,
    log_file: Path | None = None,
    video_mode: str = "dark",
) -> Path:
    """
    Assemble des clips aléatoires depuis videos_db/ pour couvrir target_duration + 4s.
    video_mode: "dark" → videos_db/videos_db_dark/, "light" → videos_db/videos_db_light/
    """
    extended = target_duration + 4

    sub_dir = VIDEOS_DB_DIR / f"videos_db_{video_mode}"
    if not sub_dir.exists():
        sub_dir = VIDEOS_DB_DIR
        log(f"  ⚠️ Sous-dossier videos_db_{video_mode} introuvable, fallback sur videos_db/", log_file)

    log(f"🎬 Assemblage vidéo de fond ({extended:.1f}s) — mode {video_mode}...", log_file)

    if not sub_dir.exists():
        raise FileNotFoundError(f"Dossier videos_db introuvable : {sub_dir}")

    video_files = [
        f for f in sub_dir.iterdir()
        if f.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not video_files:
        raise FileNotFoundError(f"Aucune vidéo dans {sub_dir.name}/")

    log(f"  {len(video_files)} vidéo(s) disponible(s)", log_file)

    selected = []
    total = 0.0
    while total < extended:
        v = random.choice(video_files)
        dur = get_media_duration(v)
        selected.append(v)
        total += dur
        log(f"  ✓ {v.name} ({dur:.1f}s) — total {total:.1f}s", log_file)

    temp_dir = work_dir / "temp_normalized"
    temp_dir.mkdir(exist_ok=True)
    normalized = []

    for i, v in enumerate(selected):
        norm_path = temp_dir / f"norm_{i}.mp4"
        if normalize_video(v, norm_path, log_file):
            normalized.append(norm_path)

    if not normalized:
        raise RuntimeError("Aucune vidéo n'a pu être normalisée")

    if len(normalized) == 1:
        cmd = [
            "ffmpeg", "-y", "-i", str(normalized[0]),
            "-t", str(extended),
            "-vf", "setpts=PTS-STARTPTS",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", str(output_video),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    else:
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for v in normalized:
                f.write(f"file '{v.resolve()}'\n")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-t", str(extended),
            "-vf", "setpts=PTS-STARTPTS",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", str(output_video),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat error:\n{result.stderr[-500:]}")

    # Vérification post-assemblage : détecter les séquences noires résiduelles
    black_seqs = _detect_black_sequences(output_video)
    if black_seqs:
        log(f"  ⚠️  {len(black_seqs)} séquence(s) noire(s) détectée(s), nettoyage...", log_file)
        _patch_black_sequences(output_video, black_seqs, normalized, extended, temp_dir, log_file)

    # Nettoyage
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    log(f"✅ Vidéo de fond générée → {output_video.name}", log_file)
    return output_video


def _detect_black_sequences(video_path: Path, min_duration: float = 0.3) -> list[dict]:
    """
    Détecte les séquences noires dans une vidéo via blackdetect.
    Retourne une liste de {"start": float, "end": float, "duration": float}.
    """
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"blackdetect=d={min_duration}:pix_th=0.10",
        "-an", "-f", "null", "NUL",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    sequences = []
    for line in result.stderr.splitlines():
        if "black_start:" in line:
            parts = {}
            for token in line.split():
                if ":" in token and token.split(":")[0] in ("black_start", "black_end", "black_duration"):
                    key, val = token.split(":", 1)
                    try:
                        parts[key] = float(val)
                    except ValueError:
                        pass
            if "black_start" in parts and "black_end" in parts:
                sequences.append({
                    "start": parts["black_start"],
                    "end": parts["black_end"],
                    "duration": parts.get("black_duration", parts["black_end"] - parts["black_start"]),
                })
    return sequences


def _patch_black_sequences(
    output_video: Path,
    black_seqs: list[dict],
    source_clips: list[Path],
    target_duration: float,
    temp_dir: Path,
    log_file: Path | None = None,
) -> None:
    """
    Remplace les séquences noires par du contenu de clips disponibles.
    Stratégie : extraire des segments propres des clips source et
    reconstituer la vidéo sans les trous noirs.
    """
    # Construire la liste des segments propres à garder (inverse des black_seqs)
    clean_segments = []
    prev_end = 0.0
    for bs in sorted(black_seqs, key=lambda x: x["start"]):
        if bs["start"] > prev_end:
            clean_segments.append((prev_end, bs["start"]))
        prev_end = bs["end"]
    if prev_end < target_duration:
        clean_segments.append((prev_end, target_duration))

    if not clean_segments:
        return

    # Extraire les segments propres
    segment_files = []
    for i, (start, end) in enumerate(clean_segments):
        seg_file = temp_dir / f"clean_seg_{i}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-to", str(end),
            "-i", str(output_video),
            "-vf", "setpts=PTS-STARTPTS",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", str(seg_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and seg_file.exists():
            segment_files.append(seg_file)

    if not segment_files:
        return

    # Besoin de contenu de remplacement pour combler les trous
    total_fill_needed = sum(bs["duration"] for bs in black_seqs)
    fill_files = []
    if total_fill_needed > 0 and source_clips:
        fill_clip = source_clips[0]  # utiliser le premier clip normalisé
        for i, bs in enumerate(black_seqs):
            fill_file = temp_dir / f"fill_{i}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(fill_clip),
                "-t", str(bs["duration"] + 0.1),
                "-vf", "setpts=PTS-STARTPTS",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-an", str(fill_file),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and fill_file.exists():
                fill_files.append((bs["start"], fill_file))

    # Reconstruire : intercaler segments propres et remplissages
    all_parts = []
    for seg in segment_files:
        all_parts.append(seg)

    concat_file = temp_dir / "patched_concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for part in all_parts:
            f.write(f"file '{part.resolve()}'\n")

    patched = temp_dir / "patched_output.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file), "-t", str(target_duration),
        "-vf", "setpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an", str(patched),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and patched.exists():
        import shutil
        shutil.move(str(patched), str(output_video))
        log(f"  ✅ Séquences noires supprimées", log_file)


def loop_video_to_duration(
    source_video: Path,
    target_duration: float,
    output_video: Path,
    log_file: Path | None = None,
) -> Path:
    """
    Boucle une vidéo source pour atteindre target_duration + 4s (style "simple").
    """
    extended = target_duration + 4
    original_dur = get_media_duration(source_video)
    loop_count = int(extended / original_dur) + 1
    log(f"🔁 Boucle vidéo ({loop_count}x) pour {extended:.1f}s...", log_file)

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", str(loop_count),
        "-i", str(source_video),
        "-t", str(extended),
        "-vf", "setpts=PTS-STARTPTS",   # reset timestamps to avoid PTS discontinuities
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an",
        str(output_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg loop error:\n{result.stderr[-500:]}")
    log(f"✅ Vidéo bouclée → {output_video.name}", log_file)
    return output_video


def generate_final_video_standard(
    video_input: Path,
    audio_input: Path,
    srt_path: Path,
    output: Path,
    log_file: Path | None = None,
) -> bool:
    """
    Génère la vidéo finale en mode standard (branding + sous-titres, sans overlays bibliques).
    """
    log("🎥 Encodage final (mode standard)...", log_file)
    srt_escaped = escape_ffmpeg_path_windows(srt_path)
    font_regular_escaped = FONT_REGULAR.replace(':', '\\:')

    vf_filter = (
        f"drawtext=text='La Sagesse Du Christ':"
        f"fontfile='{font_regular_escaped}':fontsize=24:"
        f"fontcolor=white@0.9:x=20:y=20:"
        f"shadowcolor=black@0.8:shadowx=2:shadowy=2,"
        f"subtitles=filename='{srt_escaped}':"
        f"force_style='FontName=Montserrat ExtraLight,FontSize=18,"
        f"OutlineColour=&H000000&,BorderStyle=1,Outline=1,Alignment=10,"
        f"MarginV=0,MarginL=0,MarginR=0'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_input),
        "-i", str(audio_input),
        "-vf", vf_filter,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"❌ Erreur FFmpeg: {result.stderr[-500:]}", log_file)
        return False
    log(f"✅ Vidéo finale → {output.name}", log_file)
    return True


def generate_final_video_with_overlays(
    video_input: Path,
    audio_input: Path,
    metadata_json: Path,
    srt_path: Path,
    output: Path,
    log_file: Path | None = None,
    portrait_mode: bool = False,
) -> bool:
    """
    Génère la vidéo finale avec overlays bibliques (3 étapes : masque SRT, sous-titres, overlays).
    """
    import re as _re

    log("🎨 Encodage final avec overlays bibliques...", log_file)

    with open(metadata_json, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    verses = metadata["bible_verses"]
    log(f"  {len(verses)} verset(s) avec overlay", log_file)

    output_dir = output.parent

    # ── Étape 1 : Masquer les sous-titres pendant les overlays ──────────────
    masked_srt = output_dir / "subtitles_masked.srt"
    srt_content = srt_path.read_text(encoding="utf-8")
    pattern = (
        r'(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> '
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\n((?:.*\n?)+?)(?=\n\d+\n|\Z)'
    )
    verse_times = [(v["start_time_ms"], v["end_time_ms"]) for v in verses]

    def srt_ms(h, m, s, ms):
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)

    kept = []
    for match in _re.finditer(pattern, srt_content, _re.MULTILINE):
        sub_start = srt_ms(*match.groups()[1:5])
        sub_end = srt_ms(*match.groups()[5:9])
        masked = any(
            not (sub_end < vs or sub_start > ve)
            for vs, ve in verse_times
        )
        if not masked:
            kept.append(match.group(0))

    masked_srt.write_text("\n\n".join(kept), encoding="utf-8")

    # ── Étape 2 : Appliquer les sous-titres masqués ──────────────────────────
    video_with_subs = output_dir / "temp_with_subs.mp4"
    srt_escaped = escape_ffmpeg_path_windows(masked_srt)
    cmd_subs = [
        "ffmpeg", "-y", "-i", str(video_input),
        "-vf",
        f"subtitles='{srt_escaped}':force_style='FontName=Montserrat ExtraLight,"
        f"FontSize=18,OutlineColour=&H000000&,BorderStyle=1,Outline=1,"
        f"Alignment=10,MarginV=0,MarginL=0,MarginR=0'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an",
        str(video_with_subs),
    ]
    res = subprocess.run(cmd_subs, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"❌ Sous-titres: {res.stderr[-500:]}", log_file)
        return False

    # ── Étape 3 : Overlays bibliques + branding ──────────────────────────────
    text_files = []
    filters = []

    branding_file = output_dir / "branding.txt"
    branding_file.write_text("La Sagesse Du Christ", encoding="utf-8")
    text_files.append(branding_file)
    brand_escaped = str(branding_file.resolve()).replace("\\", "/").replace(":", "\\:")

    filters.append(
        f"drawtext=textfile='{brand_escaped}':"
        f"fontsize=24:fontcolor=white@0.9:x=20:y=20:"
        f"shadowcolor=black@0.8:shadowx=2:shadowy=2"
    )

    for i, verse in enumerate(verses, 1):
        start_s = verse["start_time_ms"] / 1000.0
        end_s = verse["end_time_ms"] / 1000.0
        reference = verse["reference"]
        text = verse["text"]
        enable = f"between(t\\,{start_s}\\,{end_s})"

        filters.append(f"eq=brightness=-0.10:contrast=0.85:enable={enable}")
        filters.append(f"drawbox=x=0:y=0:w=iw:h=200:color=black@0.70:t=fill:enable={enable}")
        filters.append(f"drawbox=x=0:y=200:w=iw:h=880:color=black@0.25:t=fill:enable={enable}")

        ref_file = output_dir / f"verse_{i}_ref.txt"
        ref_file.write_text(reference, encoding="utf-8")
        text_files.append(ref_file)
        ref_escaped = str(ref_file.resolve()).replace("\\", "/").replace(":", "\\:")
        filters.append(
            f"drawtext=textfile='{ref_escaped}':"
            f"fontsize=60:fontcolor=white:x=(w-text_w)/2:y=90:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:enable={enable}"
        )

        words = text.split()
        if portrait_mode:
            # Portrait : 5 mots max par ligne (police plus petite, largeur réduite)
            max_words_per_line = 5
            lines = [
                " ".join(words[k: k + max_words_per_line])
                for k in range(0, len(words), max_words_per_line)
            ]
            verse_fontsize = 34
        else:
            # Paysage : wrapping basé sur le nombre de caractères (50 max)
            lines, current = [], ""
            for word in words:
                test = (current + " " + word).strip()
                if len(test) <= 50:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            verse_fontsize = 38

        if len(lines) > 8:
            lines = lines[:8]
            lines[-1] += "..."

        # Y de départ : 280px, espacement de 55px entre lignes
        y_start = 280
        y_step = 55
        for j, line in enumerate(lines):
            line_file = output_dir / f"verse_{i}_line_{j}.txt"
            line_file.write_text(line, encoding="utf-8")
            text_files.append(line_file)
            line_escaped = str(line_file.resolve()).replace("\\", "/").replace(":", "\\:")
            filters.append(
                f"drawtext=textfile='{line_escaped}':"
                f"fontsize={verse_fontsize}:fontcolor=white:x=(w-text_w)/2:y={y_start + j * y_step}:"
                f"shadowcolor=black@0.8:shadowx=2:shadowy=2:enable={enable}"
            )

    vf = ",".join(filters)
    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(video_with_subs),
        "-i", str(audio_input),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    res = subprocess.run(cmd_final, capture_output=True, text=True)

    # Nettoyage
    if video_with_subs.exists():
        video_with_subs.unlink()
    if masked_srt.exists():
        masked_srt.unlink()
    for tf in text_files:
        if tf.exists():
            tf.unlink()

    if res.returncode != 0:
        log(f"❌ Overlays: {res.stderr[-500:]}", log_file)
        return False

    log(f"✅ Vidéo avec overlays → {output.name}", log_file)
    return True
