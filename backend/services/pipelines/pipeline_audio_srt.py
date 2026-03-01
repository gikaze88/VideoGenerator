"""
Pipeline "audio_srt" : audio et SRT fournis, pas de TTS.
Équivalent de video_gen_audio_srt.py (réécrit sans working_dir fixe).
"""
from pathlib import Path

from backend.config import PRAYER_PAUSE_DURATION, VOICE_DELAY_SECONDS
from backend.services.pipelines.shared.audio import (
    boost_audio,
    select_random_background_music,
    mix_audio_with_background,
    insert_silence_in_audio,
)
from backend.services.pipelines.shared.srt import (
    detect_prayer_transitions,
    adjust_srt_with_pauses,
    shift_srt_timing,
)
from backend.services.pipelines.shared.bible import (
    extract_verses_with_timestamps,
    save_verses_metadata,
    shift_verses_timestamps,
)
from backend.services.pipelines.shared.video import (
    generate_background_from_videos_db,
    generate_final_video_standard,
    generate_final_video_with_overlays,
)
from backend.services.pipelines.shared.utils import (
    extract_title_and_script,
    clean_script,
    get_media_duration,
    log,
)


def run_pipeline_audio_srt(
    script_text: str,
    audio_file: Path,
    srt_file: Path,
    work_dir: Path,
    output_dir: Path,
    log_file: Path,
) -> Path:
    """
    Pipeline audio+srt : pas de TTS, utilise l'audio et le SRT fournis.
    Retourne le chemin de la vidéo finale.
    """
    log("🚀 Pipeline AUDIO+SRT démarré", log_file)

    # ── Étape 1 : Nettoyage du script (pour la détection des versets) ─────────
    log("\n📝 Étape 1/6 : Nettoyage du script...", log_file)
    title, script_body = extract_title_and_script(script_text)
    script_clean = clean_script(script_body)
    log(f"  Titre : {title}", log_file)

    clean_text_path = work_dir / "script_nettoye.txt"
    clean_text_path.write_text(script_clean, encoding="utf-8")

    # ── Étape 2 : Boost audio fourni ────────────────────────────────────────
    log("\n🔊 Étape 2/6 : Boost de l'audio fourni...", log_file)
    boosted_audio = work_dir / "audio_boosted.mp3"
    boost_audio(audio_file, boosted_audio, log_file=log_file)

    # ── Étape 3 : Détection transitions prière sur le SRT fourni ────────────
    log("\n🙏 Étape 3/6 : Détection des transitions de prière...", log_file)
    prayer_points = detect_prayer_transitions(srt_file)

    if prayer_points:
        log(f"  {len(prayer_points)} transition(s) détectée(s)", log_file)
        boosted_with_pauses = work_dir / "audio_boosted_with_pauses.mp3"
        insert_silence_in_audio(
            boosted_audio, boosted_with_pauses, prayer_points,
            PRAYER_PAUSE_DURATION, work_dir, log_file
        )
        adjusted_srt = work_dir / "subtitles_adjusted.srt"
        adjust_srt_with_pauses(srt_file, adjusted_srt, prayer_points, int(PRAYER_PAUSE_DURATION * 1000), log_file)
        boosted_audio = boosted_with_pauses
        final_srt = adjusted_srt
    else:
        log("  Aucune transition détectée", log_file)
        final_srt = srt_file

    # ── Étape 4 : Versets bibliques ──────────────────────────────────────────
    log("\n📖 Étape 4/6 : Détection des versets bibliques...", log_file)
    source_text = clean_text_path.read_text(encoding="utf-8")
    verses = extract_verses_with_timestamps(source_text, final_srt, log_file)

    # ── Étape 5 : Assemblage vidéo de fond ──────────────────────────────────
    log("\n🎬 Étape 5/6 : Assemblage de la vidéo de fond...", log_file)
    audio_duration = get_media_duration(boosted_audio)
    log(f"  Durée audio : {audio_duration:.1f}s", log_file)

    background_video = work_dir / "background_video.mp4"
    generate_background_from_videos_db(audio_duration, background_video, work_dir, log_file)

    bg_music = select_random_background_music()
    log(f"  Musique : {bg_music.name}", log_file)
    mixed_audio = work_dir / "mixed_audio.m4a"
    mix_audio_with_background(boosted_audio, bg_music, mixed_audio, log_file)

    # ── Étape 6 : Encodage final ─────────────────────────────────────────────
    log("\n🎥 Étape 6/6 : Encodage de la vidéo finale...", log_file)
    shifted_srt = work_dir / "subtitles_shifted.srt"
    shift_srt_timing(final_srt, shifted_srt, VOICE_DELAY_SECONDS, log_file)

    if verses:
        verses_shifted = shift_verses_timestamps(verses, VOICE_DELAY_SECONDS * 1000)
        metadata_path = work_dir / "bible_verses_metadata.json"
        save_verses_metadata(verses_shifted, metadata_path)

        final_video = output_dir / "final_video_with_overlays.mp4"
        success = generate_final_video_with_overlays(
            background_video, mixed_audio, metadata_path, shifted_srt, final_video, log_file
        )
    else:
        final_video = output_dir / "final_video_standard.mp4"
        success = generate_final_video_standard(
            background_video, mixed_audio, shifted_srt, final_video, log_file
        )

    if not success:
        raise RuntimeError("Échec de l'encodage de la vidéo finale")

    log(f"\n🎉 Pipeline AUDIO+SRT terminé → {final_video.name}", log_file)
    return final_video
