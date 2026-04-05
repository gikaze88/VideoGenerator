"""
Pipeline "simple" : ElevenLabs TTS + vidéo unique bouclée.
Équivalent de video_gen_simple.py (réécrit sans working_dir fixe).
Génère toujours les deux versions (avec et sans overlays).
"""
from pathlib import Path

from backend.config import PRAYER_PAUSE_DURATION, VOICE_DELAY_SECONDS
from backend.services.pipelines.shared.audio import (
    generate_audio_chunks,
    merge_audio_files,
    boost_audio,
    select_random_background_music,
    mix_audio_with_background,
    insert_silence_in_audio,
)
from backend.services.pipelines.shared.srt import (
    generate_srt,
    detect_prayer_transitions,
    adjust_srt_with_pauses,
    shift_srt_timing,
    regroup_srt_by_word_count,
)
from backend.services.pipelines.shared.video import (
    loop_video_to_duration,
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


def run_pipeline_simple(
    script_text: str,
    background_video_source: Path,
    work_dir: Path,
    output_dir: Path,
    log_file: Path,
) -> Path:
    """
    Pipeline simple : boucle une vidéo fournie, génère TTS, produit les deux versions.
    Retourne le chemin de la vidéo finale principale (avec overlays si versets détectés).
    """
    log("🚀 Pipeline SIMPLE démarré", log_file)

    portrait_mode = is_portrait_video(background_video_source)
    if portrait_mode:
        log("  📱 Vidéo de fond en mode PORTRAIT (9:16)", log_file)

    # ── Étape 1 : Extraction et nettoyage du script ───────────────────────────
    log("\n📝 Étape 1/7 : Extraction du script...", log_file)
    title, script_body = extract_title_and_script(script_text)
    script_clean = clean_script(script_body)
    log(f"  Titre : {title}", log_file)

    clean_text_path = work_dir / "script_nettoye.txt"
    clean_text_path.write_text(script_clean, encoding="utf-8")

    # ── Étape 2 : Génération audio ElevenLabs ────────────────────────────────
    log("\n🎙️  Étape 2/7 : Génération audio (ElevenLabs)...", log_file)
    audio_parts = generate_audio_chunks(script_clean, work_dir, log_file)

    merged_audio = work_dir / "full_audio.mp3"
    merge_audio_files(audio_parts, merged_audio, work_dir, log_file)

    boosted_audio = work_dir / "full_audio_boosted.mp3"
    boost_audio(merged_audio, boosted_audio, log_file=log_file)

    # ── Étape 3 : Génération SRT (Whisper) ──────────────────────────────────
    log("\n📝 Étape 3/7 : Génération des sous-titres (Whisper)...", log_file)
    raw_srt = work_dir / "final_subtitles.srt"
    generate_srt(boosted_audio, raw_srt, log_file)

    # Réduction à 3 mots/sous-titre si la vidéo de fond est en portrait (9:16)
    if portrait_mode:
        log("  📱 Format portrait détecté → regroupement SRT à 3 mots/sous-titre", log_file)
        portrait_srt = work_dir / "final_subtitles_portrait.srt"
        regroup_srt_by_word_count(raw_srt, portrait_srt, max_words=3, log_file=log_file)
        raw_srt = portrait_srt
    else:
        log("  🖥️  Format paysage → SRT à 5 mots/sous-titre (défaut Whisper)", log_file)

    # ── Étape 4 : Transitions prière ────────────────────────────────────────
    log("\n🙏 Étape 4/7 : Détection des transitions de prière...", log_file)
    prayer_points = detect_prayer_transitions(raw_srt, script_text=script_clean, log_file=log_file)

    if prayer_points:
        log(f"  {len(prayer_points)} transition(s) détectée(s)", log_file)
        boosted_with_pauses = work_dir / "full_audio_boosted_with_pauses.mp3"
        insert_silence_in_audio(
            boosted_audio, boosted_with_pauses, prayer_points,
            PRAYER_PAUSE_DURATION, work_dir, log_file
        )
        adjusted_srt = work_dir / "final_subtitles_adjusted.srt"
        adjust_srt_with_pauses(raw_srt, adjusted_srt, prayer_points, int(PRAYER_PAUSE_DURATION * 1000), log_file)
        boosted_audio = boosted_with_pauses
        final_srt = adjusted_srt
    else:
        log("  Aucune transition détectée", log_file)
        final_srt = raw_srt

    # ── Étape 5 : Versets bibliques ──────────────────────────────────────────
    log("\n📖 Étape 5/7 : Détection des versets bibliques...", log_file)
    source_text = clean_text_path.read_text(encoding="utf-8")
    from backend.services.pipelines.shared.bible import extract_verses_with_timestamps
    verses = extract_verses_with_timestamps(source_text, final_srt, log_file)

    # ── Étape 6 : Préparation vidéo de fond (boucle) ─────────────────────────
    log("\n🎬 Étape 6/7 : Préparation de la vidéo de fond (boucle)...", log_file)
    audio_duration = get_media_duration(boosted_audio)
    log(f"  Durée audio : {audio_duration:.1f}s", log_file)

    background_video = work_dir / "background_video_looped.mp4"
    loop_video_to_duration(background_video_source, audio_duration, background_video, log_file)

    bg_music = select_random_background_music()
    log(f"  Musique : {bg_music.name}", log_file)
    mixed_audio = work_dir / "mixed_audio.m4a"
    mix_audio_with_background(boosted_audio, bg_music, mixed_audio, log_file)

    # ── Étape 7 : Encodage final (les deux versions toujours) ────────────────
    log("\n🎥 Étape 7/7 : Encodage des vidéos finales...", log_file)
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
            background_video, mixed_audio, metadata_path, shifted_srt, overlay_video, log_file,
            portrait_mode=portrait_mode,
        )
        main_output = overlay_video

    standard_video = output_dir / f"{slug}_standard.mp4"
    generate_final_video_standard(background_video, mixed_audio, shifted_srt, standard_video, log_file)
    if main_output is None:
        main_output = standard_video

    log(f"\n🎉 Pipeline SIMPLE terminé → {main_output.name}", log_file)
    return main_output
