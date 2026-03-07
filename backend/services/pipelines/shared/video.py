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
) -> Path:
    """
    Assemble des clips aléatoires depuis videos_db/ pour couvrir target_duration + 4s.
    """
    extended = target_duration + 4
    log(f"🎬 Assemblage vidéo de fond ({extended:.1f}s)...", log_file)

    if not VIDEOS_DB_DIR.exists():
        raise FileNotFoundError(f"Dossier videos_db introuvable : {VIDEOS_DB_DIR}")

    video_files = [
        f for f in VIDEOS_DB_DIR.iterdir()
        if f.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not video_files:
        raise FileNotFoundError("Aucune vidéo dans videos_db/")

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
            "-t", str(extended), "-c:v", "copy", "-an", str(output_video),
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
            "-c:v", "copy", "-an", str(output_video),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # Nettoyage
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    log(f"✅ Vidéo de fond générée → {output_video.name}", log_file)
    return output_video


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
        "-c", "copy",
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
        if len(lines) > 8:
            lines = lines[:8]
            lines[-1] += "..."

        y_positions = [280, 340, 400, 460, 520, 580, 640, 700]
        for j, line in enumerate(lines):
            line_file = output_dir / f"verse_{i}_line_{j}.txt"
            line_file.write_text(line, encoding="utf-8")
            text_files.append(line_file)
            line_escaped = str(line_file.resolve()).replace("\\", "/").replace(":", "\\:")
            filters.append(
                f"drawtext=textfile='{line_escaped}':"
                f"fontsize=38:fontcolor=white:x=(w-text_w)/2:y={y_positions[j]}:"
                f"shadowcolor=black@0.8:shadowx=2:shadowy=2:enable={enable}"
            )

        filters.append(
            f"drawtext=textfile='{brand_escaped}':"
            f"fontsize=24:fontcolor=white@0.9:x=20:y=20:"
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
