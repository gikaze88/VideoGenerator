"""
Pipeline "audio_srt" : audio et SRT fournis, pas de TTS.
Équivalent de video_gen_audio_srt.py (réécrit sans working_dir fixe).

La vidéo de fond est optionnelle :
  - fournie → détection portrait/paysage, SRT adapté, boucle de la vidéo
  - absente → assemblage depuis videos_db (paysage, comme pipeline_full)
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
    regroup_srt_by_word_count,
)
from backend.services.pipelines.shared.video import (
    loop_video_to_duration,
    generate_background_from_videos_db,
    generate_final_video_standard,
    generate_final_video_with_overlays,
)
from backend.services.pipelines.shared.utils import (
    extract_title_and_script,
    clean_script,
    get_media_duration,
    is_portrait_video,
    log,
    slug_from_title,
)


def run_pipeline_audio_srt(
    script_text: str,
    audio_file: Path,
    srt_file: Path,
    work_dir: Path,
    output_dir: Path,
    log_file: Path,
    background_video: Path | None = None,
    video_mode: str = "dark",
) -> Path:
    """
    Pipeline audio+srt : utilise l'audio et le SRT fournis (pas de TTS).

    Si background_video est fourni : détecte le format (portrait/paysage),
    adapte le SRT (3 mots/ligne si 9:16), et boucle la vidéo sur la durée audio.
    Sinon : assemble la vidéo de fond depuis videos_db (paysage).

    Retourne le chemin de la vidéo finale.
    """
    log("🚀 Pipeline AUDIO+SRT démarré", log_file)

    # ── Étape 1 : Nettoyage du script (pour détection versets + prières) ──────
    log("\n📝 Étape 1/6 : Nettoyage du script...", log_file)
    title, script_body = extract_title_and_script(script_text)
    script_clean = clean_script(script_body)
    log(f"  Titre : {title}", log_file)

    clean_text_path = work_dir / "script_nettoye.txt"
    clean_text_path.write_text(script_clean, encoding="utf-8")

    # ── Étape 2 : Boost audio fourni ─────────────────────────────────────────
    log("\n🔊 Étape 2/6 : Boost de l'audio fourni...", log_file)
    boosted_audio = work_dir / "audio_boosted.mp3"
    boost_audio(audio_file, boosted_audio, log_file=log_file)

    # ── Détection du format (portrait / paysage) et adaptation du SRT ────────
    portrait_mode = False
    active_srt = srt_file  # SRT de travail (peut être remplacé si portrait)

    if background_video:
        portrait_mode = is_portrait_video(background_video)
        if portrait_mode:
            log("  📱 Vidéo de fond en mode PORTRAIT (9:16) → SRT à 3 mots/ligne", log_file)
            portrait_srt = work_dir / "subtitles_portrait.srt"
            regroup_srt_by_word_count(srt_file, portrait_srt, max_words=3, log_file=log_file)
            active_srt = portrait_srt
        else:
            log("  🖥️  Vidéo de fond en mode PAYSAGE (16:9)", log_file)
    else:
        log("  🖥️  Pas de vidéo de fond fournie → assemblage videos_db (paysage)", log_file)

    # ── Étape 3 : Détection transitions prière ────────────────────────────────
    log("\n🙏 Étape 3/6 : Détection des transitions de prière...", log_file)
    prayer_points = detect_prayer_transitions(active_srt, script_text=script_clean, log_file=log_file)

    if prayer_points:
        log(f"  {len(prayer_points)} transition(s) détectée(s)", log_file)
        boosted_with_pauses = work_dir / "audio_boosted_with_pauses.mp3"
        insert_silence_in_audio(
            boosted_audio, boosted_with_pauses, prayer_points,
            PRAYER_PAUSE_DURATION, work_dir, log_file,
        )
        adjusted_srt = work_dir / "subtitles_adjusted.srt"
        adjust_srt_with_pauses(active_srt, adjusted_srt, prayer_points, int(PRAYER_PAUSE_DURATION * 1000), log_file)
        boosted_audio = boosted_with_pauses
        final_srt = adjusted_srt
    else:
        log("  Aucune transition détectée", log_file)
        final_srt = active_srt

    # ── Étape 4 : Versets bibliques ───────────────────────────────────────────
    log("\n📖 Étape 4/6 : Détection des versets bibliques...", log_file)
    source_text = clean_text_path.read_text(encoding="utf-8")
    # Lazy import : évite les références stale avec uvicorn --reload
    from backend.services.pipelines.shared.bible import extract_verses_with_timestamps
    verses = extract_verses_with_timestamps(source_text, final_srt, log_file)

    # ── Étape 5 : Vidéo de fond ───────────────────────────────────────────────
    log("\n🎬 Étape 5/6 : Préparation de la vidéo de fond...", log_file)
    audio_duration = get_media_duration(boosted_audio)
    log(f"  Durée audio : {audio_duration:.1f}s", log_file)

    if background_video:
        bg_video = work_dir / "background_video_looped.mp4"
        loop_video_to_duration(background_video, audio_duration, bg_video, log_file)
    else:
        bg_video = work_dir / "background_video.mp4"
        generate_background_from_videos_db(audio_duration, bg_video, work_dir, log_file, video_mode=video_mode)

    bg_music = select_random_background_music()
    log(f"  Musique : {bg_music.name}", log_file)
    mixed_audio = work_dir / "mixed_audio.m4a"
    mix_audio_with_background(boosted_audio, bg_music, mixed_audio, log_file)

    # ── Étape 6 : Encodage final (les deux versions toujours) ────────────────
    log("\n🎥 Étape 6/6 : Encodage des vidéos finales...", log_file)
    shifted_srt = work_dir / "subtitles_shifted.srt"
    shift_srt_timing(final_srt, shifted_srt, VOICE_DELAY_SECONDS, log_file)

    main_output: Path | None = None
    slug = slug_from_title(title)

    if verses:
        from backend.services.pipelines.shared.bible import (
            shift_verses_timestamps, save_verses_metadata,
        )
        verses_shifted = shift_verses_timestamps(verses, VOICE_DELAY_SECONDS * 1000)
        metadata_path = work_dir / "bible_verses_metadata.json"
        save_verses_metadata(verses_shifted, metadata_path)

        overlay_video = output_dir / f"{slug}_overlay.mp4"
        generate_final_video_with_overlays(
            bg_video, mixed_audio, metadata_path, shifted_srt, overlay_video, log_file,
            portrait_mode=portrait_mode,
        )
        main_output = overlay_video

    standard_video = output_dir / f"{slug}_standard.mp4"
    generate_final_video_standard(bg_video, mixed_audio, shifted_srt, standard_video, log_file)
    if main_output is None:
        main_output = standard_video

    log(f"\n🎉 Pipeline AUDIO+SRT terminé → {main_output.name}", log_file)
    return main_output
