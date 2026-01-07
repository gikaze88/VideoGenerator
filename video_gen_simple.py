import os
import re
import datetime
import subprocess
import ctypes.util
import shutil
import sys
import random
from datetime import timedelta, datetime
from dotenv import load_dotenv
import requests

# --- Monkey-patch for Windows (Whisper) ---
_orig_find_library = ctypes.util.find_library
def patched_find_library(name):
    result = _orig_find_library(name)
    if name == "c" and result is None:
        return "msvcrt"
    return result
ctypes.util.find_library = patched_find_library

# Charger l'environnement et clés API
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
API_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

# Définir le dossier de travail pour les fichiers d'entrée
WORKING_DIR = os.path.join(os.getcwd(), "working_dir_simple")

# Créer le dossier de sortie : exemple "Project_DDMMYYYY_HHMMSS"
OUTPUT_DIR = "Project_" + datetime.now().strftime("%d%m%Y_%H%M%S")
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

##############################
# PARTIE 1 – Préparation & génération audio
##############################

def extract_title_and_script(file_path, title_file, script_file):
    """Sépare le titre et le script brut depuis le fichier."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        match = re.search(r"Transcript:\s*(.*)", text, re.DOTALL)
        if match:
            script_text = match.group(1).strip()
            title_text = text[:match.start()].strip()
            with open(title_file, "w", encoding="utf-8") as f_title:
                f_title.write(title_text)
            with open(script_file, "w", encoding="utf-8") as f_script:
                f_script.write(script_text)
            print(f"✅ Titre sauvegardé dans {title_file}")
            print(f"✅ Script extrait sauvegardé dans {script_file}")
        else:
            print("❌ 'Transcript:' introuvable dans le texte.")
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction : {e}")

def clean_script(input_file, output_file):
    """Nettoie le script en supprimant timestamps et espaces superflus."""
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            script_text = f.read()
        script_text = re.sub(r'\(\d{1,2}:\d{2}\)', '', script_text)
        script_text = re.sub(r'\s+', ' ', script_text).strip()
        script_text = re.sub(r'([a-zA-Z])\.([A-Z])', r'\1. \2', script_text)
        with open(output_file, "w", encoding="utf-8") as f_out:
            f_out.write(script_text)
        print(f"✅ Script nettoyé sauvegardé dans {output_file}")
    except Exception as e:
        print(f"❌ Erreur lors du nettoyage : {e}")

def split_text_smart(text, max_length=4900):
    """Découpe intelligemment le texte par phrase afin d'éviter de casser une phrase."""
    chunks = []
    while len(text) > max_length:
        split_index = text.rfind(".", 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(text[:split_index+1].strip())
        text = text[split_index+1:].strip()
    chunks.append(text.strip())
    return chunks

def normalize_audio(input_file, output_file, target_i=-23):
    """
    Normalise the audio volume using FFmpeg's loudnorm filter.
    `target_i` is the integrated loudness target (e.g., -23 LUFS).
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-af", f"loudnorm=I={target_i}:TP=-2:LRA=11",
        output_file
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Audio normalisé sauvegardé dans {output_file}")

def generate_audio(text_chunks):
    """Génère et normalise des fichiers audio avec ElevenLabs pour chaque chunk."""
    audio_files = []
    for i, chunk in enumerate(text_chunks, 1):
        audio_filename = os.path.join(OUTPUT_DIR, f"audio_part_{i}.mp3")
        normalized_filename = os.path.join(OUTPUT_DIR, f"audio_part_{i}_norm.mp3")
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": chunk,
            "model_id": "eleven_multilingual_v1",
            "voice_settings": {
                "speed": 1.0,
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        response = requests.post(API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            with open(audio_filename, "wb") as af:
                af.write(response.content)
            print(f"✅ Audio généré : {audio_filename}")
            # Normalize the generated audio to have consistent volume
            normalize_audio(audio_filename, normalized_filename)
            audio_files.append(normalized_filename)
        else:
            print(f"❌ Erreur audio : {response.json()}")
    return audio_files

def process_audio_generation(input_script):
    """
    Exécute l'extraction, le nettoyage et la génération des audios.
    Renvoie la liste des fichiers audio générés.
    """
    title_file = os.path.join(OUTPUT_DIR, "title.txt")
    extrait_file = os.path.join(OUTPUT_DIR, "script_extrait.txt")
    netoye_file = os.path.join(OUTPUT_DIR, "script_nettoye.txt")
    
    extract_title_and_script(input_script, title_file, extrait_file)
    clean_script(extrait_file, netoye_file)
    
    with open(netoye_file, "r", encoding="utf-8") as f:
        script_text = f.read()
    chunks = split_text_smart(script_text, 4900)
    audio_files = generate_audio(chunks)
    print("✅ Génération audio terminée.")
    return audio_files

##############################
# PARTIE 2 – Génération du SRT avec Whisper
##############################

def get_audio_duration(audio_path):
    """Retourne la durée de l'audio en secondes."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout.decode().strip())

def generate_srt_with_srt_generator(audio_file, output_srt):
    """
    Génère le fichier SRT en utilisant le sous-module srt_generator directement.
    Ce module utilise Whisper avec des optimisations anti-hallucination.
    """
    print("🔄 Génération SRT avec le sous-module srt_generator...")
    
    # Importer le module srt_generator
    sys.path.insert(0, os.path.join(os.getcwd(), "subs_generator"))
    try:
        from srt_generator import generate_srt # type: ignore
        
        # Appeler directement la fonction generate_srt
        generated_srt_path = generate_srt(audio_file, output_srt)
        print(f"✅ Fichier SRT généré avec succès: {generated_srt_path}")
        
        return generated_srt_path
        
    except Exception as e:
        print(f"❌ Erreur lors de la génération SRT: {e}")
        raise
    finally:
        # Nettoyer le path ajouté
        if os.path.join(os.getcwd(), "subs_generator") in sys.path:
            sys.path.remove(os.path.join(os.getcwd(), "subs_generator"))

def select_random_background_music():
    """
    Sélectionne aléatoirement un fichier audio du dossier background_songs.
    """
    background_songs_dir = os.path.join(os.getcwd(), "background_songs")
    
    if not os.path.exists(background_songs_dir):
        raise FileNotFoundError(f"Le dossier background_songs n'existe pas : {background_songs_dir}")
    
    # Lister tous les fichiers audio (mp3, wav, m4a, etc.)
    audio_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.ogg']
    audio_files = []
    
    for file in os.listdir(background_songs_dir):
        if any(file.lower().endswith(ext) for ext in audio_extensions):
            audio_files.append(file)
    
    if not audio_files:
        raise FileNotFoundError(f"Aucun fichier audio trouvé dans {background_songs_dir}")
    
    # Sélection aléatoire
    selected_file = random.choice(audio_files)
    selected_path = os.path.join(background_songs_dir, selected_file)
    
    print(f"🎵 Musique de fond sélectionnée aléatoirement : {selected_file}")
    return selected_path

def shift_srt_timing(input_srt, output_srt, delay_seconds=2):
    """
    Décale tous les timecodes du fichier SRT de delay_seconds secondes.
    """
    with open(input_srt, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern pour matcher les timecodes SRT (HH:MM:SS,mmm --> HH:MM:SS,mmm)
    import re
    timecode_pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})'
    
    def shift_timecode(match):
        # Extraire les composants du timecode de début
        start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
        # Extraire les composants du timecode de fin
        end_h, end_m, end_s, end_ms = map(int, match.groups()[4:])
        
        # Convertir en millisecondes totales
        start_total_ms = (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms
        end_total_ms = (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms
        
        # Ajouter le délai
        delay_ms = delay_seconds * 1000
        start_total_ms += delay_ms
        end_total_ms += delay_ms
        
        # Reconvertir en format HH:MM:SS,mmm
        def ms_to_timecode(total_ms):
            hours = total_ms // (3600 * 1000)
            minutes = (total_ms % (3600 * 1000)) // (60 * 1000)
            seconds = (total_ms % (60 * 1000)) // 1000
            milliseconds = total_ms % 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
        start_tc = ms_to_timecode(start_total_ms)
        end_tc = ms_to_timecode(end_total_ms)
        
        return f"{start_tc} --> {end_tc}"
    
    # Remplacer tous les timecodes
    shifted_content = re.sub(timecode_pattern, shift_timecode, content)
    
    with open(output_srt, 'w', encoding='utf-8') as f:
        f.write(shifted_content)
    
    print(f"✅ Fichier SRT décalé de +{delay_seconds}s sauvegardé dans {output_srt}")


##############################
# PARTIE 3 – Génération vidéo avec FFmpeg
##############################

def merge_audio_files(audio_files, output):
    """Fusionne des fichiers audio avec insertion d'une pause entre chaque segment."""
    silence = os.path.join(OUTPUT_DIR, "silence.mp3")
    if not os.path.exists(silence):
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1", silence
        ]
        subprocess.run(cmd, check=True)
    merge_list = []
    for part in audio_files:
        abs_path = os.path.abspath(part).replace('\\', '/')
        merge_list.append(abs_path)
    list_file = os.path.join(OUTPUT_DIR, "file_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for item in merge_list:
            f.write(f"file '{item}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-ar", "44100",  # force sample rate
        "-c:a", "libmp3lame", "-q:a", "2",
        output
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Audios fusionnés dans {output}")

def boost_audio(input_file, output_file, boost_db=10):
    """
    Booste le volume de l'audio du fichier d'entrée par le nombre de décibels spécifié.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-af", f"volume={boost_db}dB",
        output_file
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Audio boosté de +{boost_db} dB sauvegardé dans {output_file}")

def prepare_background_video(target_duration, output_video):
    """
    Prépare la vidéo de fond en bouclant le fichier background_video.mp4 
    pour correspondre à la durée de l'audio principal + 4 secondes (2s avant + 2s après).
    """
    background_video_path = os.path.join(WORKING_DIR, "background_video.mp4")
    
    if not os.path.exists(background_video_path):
        raise FileNotFoundError(f"Le fichier background_video.mp4 n'existe pas dans : {WORKING_DIR}")
    
    # Ajouter 4 secondes à la durée cible (2s avant + 2s après)
    extended_duration = target_duration + 4
    print(f"🔄 Préparation vidéo de fond pour une durée de {extended_duration:.1f} secondes (audio: {target_duration:.1f}s + 4s de marge)")
    
    # Obtenir la durée de la vidéo de fond originale
    original_duration = get_audio_duration(background_video_path)
    print(f"📊 Durée vidéo originale : {original_duration:.1f}s")
    
    # Calculer le nombre de boucles nécessaires
    loop_count = int(extended_duration / original_duration) + 1
    print(f"🔁 Nombre de boucles nécessaires : {loop_count}")
    
    # Boucler la vidéo et la couper à la durée exacte
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", str(loop_count),
        "-i", background_video_path,
        "-t", str(extended_duration),
        "-c", "copy",
        output_video
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Vidéo de fond préparée avec succès: {output_video}")
        
        # Vérifier la durée de la vidéo générée
        actual_duration = get_audio_duration(output_video)
        print(f"📊 Durée vidéo finale : {actual_duration:.1f}s (cible : {extended_duration:.1f}s)")
        
        return output_video
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors de la préparation de la vidéo de fond: {e}")
        raise

def mix_audio_with_background_delayed(voice_audio, bg_music, output, voice_delay_seconds=2):
    """
    Mixe l'audio principal boosté avec la musique d'ambiance.
    L'audio principal est retardé de voice_delay_seconds secondes.
    La musique d'ambiance démarre immédiatement et couvre toute la durée.
    """
    # Calculer la durée totale nécessaire (durée de l'audio vocal + 2s avant + 2s après)
    voice_duration = get_audio_duration(voice_audio)
    total_duration = voice_duration + 4  # 2s avant + 2s après = 4s au total
    
    cmd = [
        "ffmpeg", "-y",
        "-i", voice_audio,
        "-stream_loop", "-1", "-i", bg_music,
        "-filter_complex", f"[0:a]adelay={voice_delay_seconds * 1000}|{voice_delay_seconds * 1000}[a0];[1:a]volume=0.2[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=3",
        "-t", str(total_duration),
        "-c:a", "aac",
        "-b:a", "192k",
        output
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Audio mixé avec délai de {voice_delay_seconds}s généré : {output} (durée: {total_duration:.1f}s)")

def generate_final_video(video_input, audio_input, subtitle_file, output):
    """
    Génère la vidéo finale en incrustant des sous-titres décalés.
    La vidéo est ré-encodée en gardant une haute qualité (preset veryslow, CRF 15)
    et le son est mappé correctement.
    """
    # Créer un fichier SRT décalé de 2 secondes
    shifted_srt = subtitle_file.replace('.srt', '_shifted.srt')
    shift_srt_timing(subtitle_file, shifted_srt, delay_seconds=2)
    
    abs_sub = os.path.abspath(shifted_srt)
    # Handle Windows path for FFmpeg subtitle filter
    if len(abs_sub) > 1 and abs_sub[1] == ':':
        # For Windows: C:\path -> C\:/path (escape colon, then replace remaining backslashes)
        drive_letter = abs_sub[0]
        path_remainder = abs_sub[2:].replace('\\', '/')  # Convert backslashes to forward slashes
        abs_sub = drive_letter + '\\:' + path_remainder
    else:
        # For non-Windows paths, just convert backslashes
        abs_sub = abs_sub.replace('\\', '/')
    vf_filter = ("drawtext=text='La Sagesse Du Christ':fontfile='C\\:/Windows/Fonts/montserrat-regular.ttf':fontsize=24:fontcolor=white:x=50:y=50:shadowcolor=black:shadowx=2:shadowy=2,"
                 "subtitles=filename='{}':force_style='FontName=Montserrat ExtraLight,FontSize=18,"
                 "OutlineColour=&H000000&,BorderStyle=1,Outline=1,Alignment=10,MarginV=0,MarginL=0,MarginR=0'").format(abs_sub)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_input,
        "-i", audio_input,
        "-vf", vf_filter,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryslow",
        "-crf", "15",
        "-c:a", "aac",
        "-b:a", "192k",
        output
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Vidéo finale générée : {output}")


##############################
# FONCTIONS INTELLIGENTES - DÉTECTION DES TRANSITIONS
##############################

def parse_srt_file(srt_path):
    """
    Parse un fichier SRT et retourne une liste de sous-titres avec leurs informations.
    """
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern pour matcher un bloc de sous-titre complet
    subtitle_pattern = r'(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})\n((?:.*\n?)+?)(?=\n\d+\n|\Z)'
    
    subtitles = []
    for match in re.finditer(subtitle_pattern, content, re.MULTILINE):
        index = int(match.group(1))
        start_h, start_m, start_s, start_ms = map(int, match.groups()[1:5])
        end_h, end_m, end_s, end_ms = map(int, match.groups()[5:9])
        text = match.group(10).strip()
        
        # Convertir en millisecondes
        start_time = (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms
        end_time = (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms
        
        subtitles.append({
            'index': index,
            'start_time': start_time,
            'end_time': end_time,
            'text': text
        })
    
    return subtitles

def detect_prayer_transitions(srt_path):
    """Détecte les phrases de transition vers la prière"""
    
    subtitles = parse_srt_file(srt_path)
    
    # ✅ PATTERNS CORRIGÉS - Tous les anciens patterns + correction pour éviter débordement
    transition_patterns = [
        r'maintenant[,\s]+prions(?![,\s]*\w)',                      # "Maintenant prions" (s'arrête ici)
        r'maintenant[,\s]+prions[,\s]+le[,\s]+seigneur(?![,\s]*\w)',  # "Maintenant prions le Seigneur"
        r'maintenant[,\s]+prions[,\s]+dieu(?![,\s]*\w)',            # "Maintenant prions Dieu"
        r'prions[,\s]+ensemble(?![,\s]*\w)',                        # "Prions ensemble"
        r'prions[,\s]+maintenant(?![,\s]*\w)',                      # "Prions maintenant"
        r'alors[,\s]+prions(?![,\s]*\w)',                           # "Alors prions"
    ]
    
    transition_points = []
    
    for subtitle in subtitles:
        text_lower = subtitle['text'].lower()
        
        for pattern in transition_patterns:
            if re.search(pattern, text_lower):
                print(f"🔍 Transition détectée : '{subtitle['text']}' à {subtitle['end_time']/1000:.2f}s")
                transition_points.append(subtitle['end_time'])
                break
    
    return transition_points

def ms_to_timecode(total_ms):
    """Convertit des millisecondes en format timecode HH:MM:SS,mmm"""
    hours = total_ms // (3600 * 1000)
    minutes = (total_ms % (3600 * 1000)) // (60 * 1000)
    seconds = (total_ms % (60 * 1000)) // 1000
    milliseconds = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def adjust_srt_with_pauses(srt_path, output_srt, pause_points, pause_duration_ms=3000):
    """
    Ajuste les timings du SRT en ajoutant des pauses aux points spécifiés.
    pause_points: liste des timestamps (en ms) après lesquels ajouter des pauses.
    """
    subtitles = parse_srt_file(srt_path)
    
    # Trier les points de pause
    sorted_pauses = sorted(pause_points)
    
    # Calculer le décalage cumulatif pour chaque sous-titre
    adjusted_subtitles = []
    cumulative_delay = 0
    
    for subtitle in subtitles:
        # Vérifier combien de pauses sont avant ce sous-titre
        pauses_before = sum(1 for pause in sorted_pauses if pause <= subtitle['start_time'])
        cumulative_delay = pauses_before * pause_duration_ms
        
        adjusted_subtitles.append({
            'index': subtitle['index'],
            'start_time': subtitle['start_time'] + cumulative_delay,
            'end_time': subtitle['end_time'] + cumulative_delay,
            'text': subtitle['text']
        })
    
    # Écrire le nouveau fichier SRT
    with open(output_srt, 'w', encoding='utf-8') as f:
        for sub in adjusted_subtitles:
            f.write(f"{sub['index']}\n")
            f.write(f"{ms_to_timecode(sub['start_time'])} --> {ms_to_timecode(sub['end_time'])}\n")
            f.write(f"{sub['text']}\n\n")
    
    print(f"✅ Fichier SRT ajusté avec {len(sorted_pauses)} pause(s) sauvegardé dans {output_srt}")

def insert_silence_in_audio(audio_path, output_path, pause_points, pause_duration=3.0):
    """
    Insère des silences dans l'audio aux points spécifiés.
    pause_points: liste des timestamps (en ms) où insérer les pauses.
    pause_duration: durée du silence en secondes.
    """
    if not pause_points:
        # Pas de transitions détectées, copier simplement l'audio
        shutil.copy2(audio_path, output_path)
        print("✅ Aucune transition détectée, audio copié sans modification")
        return
    
    # Trier les points de pause
    sorted_pauses = sorted(pause_points)
    
    print(f"🔄 Insertion de {len(sorted_pauses)} pause(s) de {pause_duration}s dans l'audio...")
    
    # Créer un fichier de silence temporaire
    silence_file = os.path.join(OUTPUT_DIR, "silence_temp.mp3")
    cmd_silence = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(pause_duration),
        "-c:a", "libmp3lame", "-q:a", "2",
        silence_file
    ]
    subprocess.run(cmd_silence, check=True, capture_output=True)
    
    # Découper l'audio en segments et insérer les silences
    segments = []
    prev_time = 0
    
    for i, pause_time_ms in enumerate(sorted_pauses):
        pause_time_s = pause_time_ms / 1000.0
        
        # Extraire le segment avant la pause
        segment_file = os.path.join(OUTPUT_DIR, f"segment_{i}.mp3")
        duration = pause_time_s - prev_time
        
        cmd_segment = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", str(prev_time),
            "-t", str(duration),
            "-c:a", "libmp3lame", "-q:a", "2",
            segment_file
        ]
        subprocess.run(cmd_segment, check=True, capture_output=True)
        segments.append(segment_file)
        segments.append(silence_file)
        
        prev_time = pause_time_s
        print(f"  ✓ Segment {i+1} extrait (0:{prev_time-duration:.2f} -> 0:{pause_time_s:.2f}) + pause de {pause_duration}s")
    
    # Extraire le dernier segment (après la dernière pause)
    last_segment_file = os.path.join(OUTPUT_DIR, f"segment_last.mp3")
    cmd_last = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ss", str(prev_time),
        "-c:a", "libmp3lame", "-q:a", "2",
        last_segment_file
    ]
    subprocess.run(cmd_last, check=True, capture_output=True)
    segments.append(last_segment_file)
    
    # Concaténer tous les segments
    concat_list_file = os.path.join(OUTPUT_DIR, "concat_audio_list.txt")
    with open(concat_list_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            f.write(f"file '{os.path.abspath(segment)}'\n")
    
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_file,
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ]
    subprocess.run(cmd_concat, check=True)
    
    # Nettoyer les fichiers temporaires
    os.remove(silence_file)
    os.remove(concat_list_file)
    for segment in segments:
        if os.path.exists(segment):
            os.remove(segment)
    
    print(f"✅ Audio avec {len(sorted_pauses)} pause(s) généré : {output_path}")

##############################
# MODULE NOUVEAU - AMÉLIORATION DU SRT AVEC TEXTE SOURCE
# APPROCHE ROBUSTE : Basée sur correct_srt_quotes.py testé et validé
##############################

# Dictionnaire des livres bibliques (français)

BIBLE_BOOKS = {
    # ========== ANCIEN TESTAMENT ==========
    
    # Pentateuque
    "genese": "GENÈSE", "génèse": "GENÈSE",
    "exode": "EXODE", 
    "levitique": "LÉVITIQUE", "lévitique": "LÉVITIQUE",
    "nombres": "NOMBRES", "nombre": "NOMBRES",
    "deuteronome": "DEUTÉRONOME", "deutéronome": "DEUTÉRONOME",
    
    # Livres historiques
    "josue": "JOSUÉ", "josué": "JOSUÉ",
    "juges": "JUGES", "juge": "JUGES",
    "ruth": "RUTH",
    
    # Samuel
    "samuel": "SAMUEL",
    "1 samuel": "1 SAMUEL", "un samuel": "1 SAMUEL", 
    "premier samuel": "1 SAMUEL", "première samuel": "1 SAMUEL",
    "2 samuel": "2 SAMUEL", "deux samuel": "2 SAMUEL",
    "deuxieme samuel": "2 SAMUEL", "deuxième samuel": "2 SAMUEL",
    "second samuel": "2 SAMUEL", "seconde samuel": "2 SAMUEL",
    
    # Rois
    "rois": "ROIS",
    "1 rois": "1 ROIS", "un rois": "1 ROIS",
    "premier rois": "1 ROIS", "première rois": "1 ROIS",
    "2 rois": "2 ROIS", "deux rois": "2 ROIS",
    "deuxieme rois": "2 ROIS", "deuxième rois": "2 ROIS",
    "second rois": "2 ROIS", "seconde rois": "2 ROIS",
    
    # Chroniques
    "chroniques": "CHRONIQUES", "chronique": "CHRONIQUES",
    "1 chroniques": "1 CHRONIQUES", "une chroniques": "1 CHRONIQUES",
    "premiere chroniques": "1 CHRONIQUES", "première chroniques": "1 CHRONIQUES",
    "2 chroniques": "2 CHRONIQUES", "deux chroniques": "2 CHRONIQUES",
    "deuxieme chroniques": "2 CHRONIQUES", "deuxième chroniques": "2 CHRONIQUES",
    
    # Retour d'exil
    "esdras": "ESDRAS",
    "nehemie": "NÉHÉMIE", "néhémie": "NÉHÉMIE",
    "esther": "ESTHER",
    
    # Livres poétiques
    "job": "JOB",
    "psaume": "PSAUMES", "psaumes": "PSAUMES",
    "proverbe": "PROVERBES", "proverbes": "PROVERBES",
    "ecclesiaste": "ECCLÉSIASTE", "ecclésiaste": "ECCLÉSIASTE",
    "cantique": "CANTIQUE DES CANTIQUES", "cantiques": "CANTIQUE DES CANTIQUES",
    "cantique des cantiques": "CANTIQUE DES CANTIQUES",
    
    # Grands prophètes
    "esaie": "ÉSAÏE", "ésaïe": "ÉSAÏE", "esaïe": "ÉSAÏE", "isaie": "ÉSAÏE", "isaïe": "ÉSAÏE",
    "jeremie": "JÉRÉMIE", "jérémie": "JÉRÉMIE",
    "lamentations": "LAMENTATIONS", "lamentation": "LAMENTATIONS",
    "ezechiel": "ÉZÉCHIEL", "ézéchiel": "ÉZÉCHIEL", "ezéchiel": "ÉZÉCHIEL",
    "daniel": "DANIEL",
    
    # Petits prophètes
    "osee": "OSÉE", "osée": "OSÉE",
    "joel": "JOËL", "joël": "JOËL",
    "amos": "AMOS",
    "abdias": "ABDIAS",
    "jonas": "JONAS",
    "michee": "MICHÉE", "michée": "MICHÉE",
    "nahum": "NAHUM",
    "habacuc": "HABACUC", "habakkuk": "HABACUC",
    "sophonie": "SOPHONIE",
    "aggee": "AGGÉE", "aggée": "AGGÉE",
    "zacharie": "ZACHARIE",
    "malachie": "MALACHIE",
    
    # ========== NOUVEAU TESTAMENT ==========
    
    # ===== ÉVANGILES =====
    "matthieu": "MATTHIEU",
    "marc": "MARC",
    "luc": "LUC",
    "jean": "JEAN",
    
    # ===== ACTES =====
    "actes": "ACTES", "acte": "ACTES",
    "actes des apotres": "ACTES", "actes des apôtres": "ACTES",
    
    # ===== ÉPÎTRES PAULINIENNES =====
    
    # Romains
    "romains": "ROMAINS", "romain": "ROMAINS",
    
    # Corinthiens
    "corinthiens": "CORINTHIENS", "corinthien": "CORINTHIENS",
    "1 corinthiens": "1 CORINTHIENS", "un corinthiens": "1 CORINTHIENS",
    "premier corinthiens": "1 CORINTHIENS", "premiere corinthiens": "1 CORINTHIENS",
    "première corinthiens": "1 CORINTHIENS",
    "2 corinthiens": "2 CORINTHIENS", "deux corinthiens": "2 CORINTHIENS",
    "deuxieme corinthiens": "2 CORINTHIENS", "deuxième corinthiens": "2 CORINTHIENS",
    "second corinthiens": "2 CORINTHIENS", "seconde corinthiens": "2 CORINTHIENS",
    
    # Galates
    "galates": "GALATES", "galate": "GALATES",
    
    # Éphésiens
    "ephesiens": "ÉPHÉSIENS", "éphésiens": "ÉPHÉSIENS",
    "ephesien": "ÉPHÉSIENS", "éphésien": "ÉPHÉSIENS",
    
    # Philippiens
    "philippiens": "PHILIPPIENS", "philippien": "PHILIPPIENS",
    
    # Colossiens
    "colossiens": "COLOSSIENS", "colossien": "COLOSSIENS",
    
    # Thessaloniciens
    "thessaloniciens": "THESSALONICIENS", "thessalonicien": "THESSALONICIENS",
    "1 thessaloniciens": "1 THESSALONICIENS", "un thessaloniciens": "1 THESSALONICIENS",
    "premier thessaloniciens": "1 THESSALONICIENS",
    "premiere thessaloniciens": "1 THESSALONICIENS",
    "première thessaloniciens": "1 THESSALONICIENS",
    "2 thessaloniciens": "2 THESSALONICIENS", "deux thessaloniciens": "2 THESSALONICIENS",
    "deuxieme thessaloniciens": "2 THESSALONICIENS",
    "deuxième thessaloniciens": "2 THESSALONICIENS",
    "second thessaloniciens": "2 THESSALONICIENS",
    
    # Timothée
    "timothee": "TIMOTHÉE", "timothée": "TIMOTHÉE",
    "1 timothee": "1 TIMOTHÉE", "1 timothée": "1 TIMOTHÉE",
    "un timothee": "1 TIMOTHÉE", "un timothée": "1 TIMOTHÉE",
    "premier timothee": "1 TIMOTHÉE", "première timothée": "1 TIMOTHÉE",
    "premiere timothee": "1 TIMOTHÉE",
    "2 timothee": "2 TIMOTHÉE", "2 timothée": "2 TIMOTHÉE",
    "deux timothee": "2 TIMOTHÉE", "deux timothée": "2 TIMOTHÉE",
    "deuxieme timothee": "2 TIMOTHÉE", "deuxième timothée": "2 TIMOTHÉE",
    "second timothee": "2 TIMOTHÉE",
    
    # Tite
    "tite": "TITE",
    
    # Philémon
    "philemon": "PHILÉMON", "philémon": "PHILÉMON",
    
    # ===== ÉPÎTRE AUX HÉBREUX =====
    "hebreux": "HÉBREUX", "hébreux": "HÉBREUX",
    "hebreu": "HÉBREUX", "hébreu": "HÉBREUX",
    
    # ===== ÉPÎTRES CATHOLIQUES =====
    
    # Jacques
    "jacques": "JACQUES",
    
    # Pierre
    "pierre": "PIERRE",
    "1 pierre": "1 PIERRE", "un pierre": "1 PIERRE",
    "premier pierre": "1 PIERRE", "premiere pierre": "1 PIERRE",
    "première pierre": "1 PIERRE",
    "2 pierre": "2 PIERRE", "deux pierre": "2 PIERRE",
    "deuxieme pierre": "2 PIERRE", "deuxième pierre": "2 PIERRE",
    "second pierre": "2 PIERRE", "seconde pierre": "2 PIERRE",
    
    # Jean (Épîtres)
    "1 jean": "1 JEAN", "un jean": "1 JEAN",
    "premier jean": "1 JEAN", "premiere jean": "1 JEAN", "première jean": "1 JEAN",
    "2 jean": "2 JEAN", "deux jean": "2 JEAN",
    "deuxieme jean": "2 JEAN", "deuxième jean": "2 JEAN",
    "second jean": "2 JEAN", "seconde jean": "2 JEAN",
    "3 jean": "3 JEAN", "trois jean": "3 JEAN",
    "troisieme jean": "3 JEAN", "troisième jean": "3 JEAN",
    
    # Jude
    "jude": "JUDE",
    
    # ===== APOCALYPSE =====
    "apocalypse": "APOCALYPSE",
    "revelation": "APOCALYPSE",  # Nom anglais parfois utilisé
}


#########################################################################################################
# New Fonction Added For Verses Detection: Begin
#########################################################################################################

def normalize_text_for_search(text):
    """Normalise le texte pour la recherche (minuscules, sans ponctuation)"""
    import re
    text = text.lower()
    # Enlever tous les caractères spéciaux sauf espaces
    text = re.sub(r'[«»"'',.\-:;!?]', '', text)
    # Normaliser les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def find_verse_in_srt(verse_normalized, subtitles, max_window=30):
    """
    Cherche un verset dans le SRT avec une fenêtre glissante.
    
    Args:
        verse_normalized: STRING (texte normalisé du verset)
        subtitles: Liste des sous-titres
        max_window: Taille max de la fenêtre
    """
    # ✅ LIGNE CORRECTE
    verse_words = set(verse_normalized.split())
    
    best_match = None
    best_coverage = 0
    
    for window_size in range(5, max_window + 1):
        for i in range(len(subtitles) - window_size + 1):
            window_subtitles = subtitles[i:i+window_size]
            combined_text = ' '.join([s['text'] for s in window_subtitles])
            combined_normalized = normalize_text_for_search(combined_text)
            
            combined_words = set(combined_normalized.split())
            common_words = combined_words & verse_words
            coverage = len(common_words) / len(verse_words) if verse_words else 0
            
            if coverage >= 0.80 and coverage > best_coverage:
                best_coverage = coverage
                best_match = {
                    'start_time': subtitles[i]['start_time'],
                    'end_time': subtitles[i + window_size - 1]['end_time'],
                    'subtitle_range': (i, i + window_size - 1),
                    'coverage': coverage
                }
    
    return best_match

def extract_reference_from_source(verse_text, source_text):
    """
    Extrait la référence biblique associée à un verset dans le texte source.
    
    ✅ SUPPORTE TOUS LES FORMATS POSSIBLES :
    - "Dans Psaume 34 verset 18"
    - "La Bible dit dans psaume vingt-trois un"
    - "Dans Matthieu chapitre six verset trente-et-un"
    - "Selon Jean trois seize"
    - "Premier Jean trois seize"
    - Et bien d'autres...
    
    Args:
        verse_text: Texte du verset à chercher
        source_text: Texte source complet
        
    Returns:
        Référence formatée (ex: "PSAUMES 34:18") ou "VERSET BIBLIQUE" si non trouvé
    """
    import re
    
    # Trouver la position du verset dans le source
    verse_start = verse_text[:50] if len(verse_text) > 50 else verse_text
    verse_pos = source_text.find(verse_start)
    
    if verse_pos == -1:
        verse_start = verse_text[:30]
        verse_pos = source_text.find(verse_start)
    
    if verse_pos == -1:
        return "VERSET BIBLIQUE"
    
    # Chercher dans les 500 caractères PRÉCÉDENTS le verset
    search_start = max(0, verse_pos - 500)
    search_text = source_text[search_start:verse_pos]
    
    # ========================================
    # PATTERNS EXHAUSTIFS (ordre important !)
    # ========================================
    ref_patterns = [
        # ===== FORMAT 1 : AVEC "VERSET" EXPLICITE =====
        
        # 1.1 "Dans Matthieu chapitre six verset trente-et-un"
        (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèê\-]+)\s+chapitres?\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'chapitre_verset'),
        
        # 1.2 "En Jean chapitre trois versets seize à dix-sept"
        (r'[Ee]n\s+([A-Za-zéèê\-]+)\s+chapitres?\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)(?:\s+à\s+([a-zéèê\-]+))?', 'chapitre_verset_range'),
        
        # 1.3 "Dans Matthieu au chapitre six verset trente-et-un"
        (r'[Dd]ans\s+([A-Za-zéèê\-]+)\s+au\s+chapitres?\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'au_chapitre_verset'),
        
        # 1.4 "En deux Corinthiens, un verset trois et quatre" (ordinal + article)
        (r'[Ee]n\s+([a-zéèê\-]+)\s+([A-Za-zéèê\-]+)\s*,?\s*(?:un|une)\s+versets?\s+([a-zéèê\-]+)(?:\s+et\s+([a-zéèê\-]+))?', 'ordinal_with_un'),
        
        # 1.5 "Dans Psaume trente-quatre verset dix-huit"
        (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'standard_dans'),
        
        # 1.6 "En Psaume cent-quarante-sept verset trois"
        (r'[Ee]n\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'standard_en'),
        
        # 1.7 "Et en Matthieu onze verset vingt-huit"
        (r'[Ee]t\s+en\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'standard_et_en'),
        
        # ===== FORMAT 2 : SANS "VERSET" (COMPACT) =====
        
        # 2.1 "La Bible dit dans psaume vingt-trois un :"
        (r'[Dd]ans\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)\s*:', 'inverse_format'),
        
        # 2.2 "Il est dit dans Matthieu six trente-et-un"
        (r'[Dd]it\s+dans\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)', 'dit_dans'),
        
        # 2.3 "Dans Matthieu six trente-et-un à trente-trois" (plage)
        (r'[Dd]ans\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)\s+à\s+([a-zéèê\-]+)', 'verse_range'),
        
        # 2.4 "Et dans Philippiens quatre dix-neuf"
        (r'[Ee]t\s+dans\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)', 'et_dans_format'),
        
        # 2.5 "Dans Matthieu six, verset trente-et-un" (avec virgule)
        (r'[Dd]ans\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s*,\s*(?:versets?\s+)?([a-zéèê\-]+)', 'avec_virgule'),
        
        # 2.6 "Psaume vingt-trois, un" (compact avec virgule)
        (r'([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s*,\s*([a-zéèê\-]+)', 'compact_virgule'),
        
        # ===== FORMAT 3 : AVEC "SELON" / "D'APRÈS" =====
        
        # 3.1 "Selon Matthieu six trente-et-un"
        (r'[Ss]elon\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)', 'selon'),
        
        # 3.2 "D'après Jean trois seize"
        (r"[Dd]'après\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)", 'daprès'),
        
        # ===== FORMAT 4 : ORDINAUX ÉCRITS =====
        
        # 4.1 "Dans premier Jean trois seize"
        (r'[Dd]ans\s+(?:le\s+)?(premier|première|deuxième|second|seconde|troisième)\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+(?:versets?\s+)?([a-zéèê\-]+)', 'ordinal_ecrit_dans'),
        
        # 4.2 "En première Corinthiens quinze un"
        (r'[Ee]n\s+(premier|première|deuxième|second|seconde|troisième)\s+([A-Za-zéèê\-]+)\s+([a-zéèê\-]+)\s+(?:versets?\s+)?([a-zéèê\-]+)', 'ordinal_ecrit_en'),
        
        # ===== FORMAT 5 : CHIFFRES ET NOTATION MODERNE =====
        
        # 5.1 "Dans Psaume 34 verset 18" (chiffres)
        (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèê]+)\s+(\d+)(?:,?\s*versets?\s*(\d+))?', 'digits_dans'),
        
        # 5.2 "En Matthieu 6:31-33" (notation moderne avec plage)
        (r'[Ee]n\s+([A-Za-zéèê]+)\s+(\d+):(\d+)(?:-(\d+))?', 'modern_notation'),
        
        # 5.3 "Selon Jean 3:16"
        (r'[Ss]elon\s+([A-Za-zéèê]+)\s+(\d+):(\d+)(?:-(\d+))?', 'selon_modern'),
    ]
    
    best_reference = None
    best_distance = float('inf')
    
    # ========================================
    # RECHERCHE DE LA RÉFÉRENCE LA PLUS PROCHE
    # ========================================
    for pattern, pattern_type in ref_patterns:
        matches = list(re.finditer(pattern, search_text, re.IGNORECASE))
        
        for match in matches:
            # Calculer la distance entre la référence et le verset
            ref_end_pos = match.end()
            distance = (verse_pos - search_start) - ref_end_pos
            
            # Prendre la référence LA PLUS PROCHE du verset
            if distance >= 0 and distance < best_distance:
                best_distance = distance
                
                # ===== TRAITEMENT SELON LE TYPE DE PATTERN =====
                
                if pattern_type == 'chapitre_verset':
                    # "Dans Matthieu chapitre six verset trente-et-un"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type == 'chapitre_verset_range':
                    # "En Jean chapitre trois versets seize à dix-sept"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_start = match.group(3)
                    verse_end = match.group(4) if len(match.groups()) >= 4 and match.group(4) else None
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    v_start = convert_french_number_to_digit(verse_start)
                    
                    if verse_end:
                        v_end = convert_french_number_to_digit(verse_end)
                        best_reference = f"{book_normalized} {chapter}:{v_start}-{v_end}"
                    else:
                        best_reference = f"{book_normalized} {chapter}:{v_start}"
                
                elif pattern_type == 'au_chapitre_verset':
                    # "Dans Matthieu au chapitre six verset trente-et-un"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type == 'ordinal_with_un':
                    # "En deux Corinthiens, un verset trois et quatre"
                    ordinal = match.group(1).lower()
                    book_raw = match.group(2).lower()
                    verse_raw = match.group(3)
                    verse_raw2 = match.group(4) if len(match.groups()) >= 4 and match.group(4) else None
                    
                    # Construire le nom du livre avec l'ordinal
                    book_full = f"{ordinal} {book_raw}"
                    book_normalized = BIBLE_BOOKS.get(book_full, BIBLE_BOOKS.get(book_raw, book_raw.upper()))
                    
                    # Le chapitre est 1 (le "un" avant "verset")
                    chapter = "1"
                    verse_num = convert_french_number_to_digit(verse_raw)
                    if verse_raw2:
                        verse_num += f"-{convert_french_number_to_digit(verse_raw2)}"
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type in ['standard_dans', 'standard_en', 'standard_et_en']:
                    # "Dans Psaume trente-quatre verset dix-huit"
                    # "En Psaume cent-quarante-sept verset trois"
                    # "Et en Matthieu onze verset vingt-huit"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type == 'inverse_format':
                    # "La Bible dit dans psaume vingt-trois un :"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type in ['dit_dans', 'selon', 'daprès']:
                    # "Il est dit dans / Selon / D'après Matthieu six trente-et-un"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type == 'verse_range':
                    # "Dans Matthieu six trente-et-un à trente-trois"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_start = match.group(3)
                    verse_end = match.group(4)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    v_start = convert_french_number_to_digit(verse_start)
                    v_end = convert_french_number_to_digit(verse_end)
                    
                    best_reference = f"{book_normalized} {chapter}:{v_start}-{v_end}"
                
                elif pattern_type == 'et_dans_format':
                    # "Et dans Philippiens quatre dix-neuf"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type in ['avec_virgule', 'compact_virgule']:
                    # "Dans Matthieu six, trente-et-un" ou "Psaume vingt-trois, un"
                    book_raw = match.group(1).lower()
                    chapter_raw = match.group(2)
                    verse_raw = match.group(3)
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type in ['ordinal_ecrit_dans', 'ordinal_ecrit_en']:
                    # "Dans premier Jean trois seize" ou "En première Corinthiens quinze un"
                    ordinal_text = match.group(1).lower()
                    book_raw = match.group(2).lower()
                    chapter_raw = match.group(3)
                    verse_raw = match.group(4)
                    
                    # Convertir l'ordinal écrit en chiffre
                    ordinal_map = {
                        'premier': '1', 'première': '1',
                        'deuxième': '2', 'second': '2', 'seconde': '2',
                        'troisième': '3'
                    }
                    ordinal_num = ordinal_map.get(ordinal_text, '1')
                    
                    # Construire le nom du livre
                    book_full = f"{ordinal_num} {book_raw}"
                    book_normalized = BIBLE_BOOKS.get(book_full, book_raw.upper())
                    
                    chapter = convert_french_number_to_digit(chapter_raw)
                    verse_num = convert_french_number_to_digit(verse_raw)
                    
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type == 'digits_dans':
                    # "Dans Psaume 34 verset 18" (chiffres)
                    book_raw = match.group(1).lower()
                    chapter = match.group(2)
                    verse_num = match.group(3) if match.group(3) else "1"
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    best_reference = f"{book_normalized} {chapter}:{verse_num}"
                
                elif pattern_type in ['modern_notation', 'selon_modern']:
                    # "En Jean 3:16" ou "Selon Matthieu 6:31-33"
                    book_raw = match.group(1).lower()
                    chapter = match.group(2)
                    verse_start = match.group(3)
                    verse_end = match.group(4) if len(match.groups()) >= 4 and match.group(4) else None
                    
                    book_normalized = BIBLE_BOOKS.get(book_raw, book_raw.upper())
                    
                    if verse_end:
                        best_reference = f"{book_normalized} {chapter}:{verse_start}-{verse_end}"
                    else:
                        best_reference = f"{book_normalized} {chapter}:{verse_start}"
    
    return best_reference if best_reference else "VERSET BIBLIQUE"

def convert_french_number_to_digit(text):
    """
    Convertit un nombre français en chiffres.
    
    ✅ COMPLET : Supporte les nombres de 0 à 200
    
    Exemples:
    - "trente-quatre" → "34"
    - "cent-quarante-sept" → "147"
    - "soixante-dix-huit" → "78"
    - "quatre-vingt-quinze" → "95"
    - "34" → "34" (déjà un chiffre)
    """
    # Si c'est déjà un chiffre, retourner tel quel
    if text.isdigit():
        return text
    
    # ✅ DICTIONNAIRE COMPLET DE 0 À 200
    french_numbers = {
        # 0-19
        "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
        "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
        "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
        "quinze": 15, "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19,
        
        # 20-29
        "vingt": 20, "vingt-et-un": 21, "vingt-et-une": 21,
        "vingt-deux": 22, "vingt-trois": 23, "vingt-quatre": 24, "vingt-cinq": 25,
        "vingt-six": 26, "vingt-sept": 27, "vingt-huit": 28, "vingt-neuf": 29,
        
        # 30-39
        "trente": 30, "trente-et-un": 31, "trente-et-une": 31,
        "trente-deux": 32, "trente-trois": 33, "trente-quatre": 34, "trente-cinq": 35,
        "trente-six": 36, "trente-sept": 37, "trente-huit": 38, "trente-neuf": 39,
        
        # 40-49
        "quarante": 40, "quarante-et-un": 41, "quarante-et-une": 41,
        "quarante-deux": 42, "quarante-trois": 43, "quarante-quatre": 44, "quarante-cinq": 45,
        "quarante-six": 46, "quarante-sept": 47, "quarante-huit": 48, "quarante-neuf": 49,
        
        # 50-59
        "cinquante": 50, "cinquante-et-un": 51, "cinquante-et-une": 51,
        "cinquante-deux": 52, "cinquante-trois": 53, "cinquante-quatre": 54, "cinquante-cinq": 55,
        "cinquante-six": 56, "cinquante-sept": 57, "cinquante-huit": 58, "cinquante-neuf": 59,
        
        # 60-69
        "soixante": 60, "soixante-et-un": 61, "soixante-et-une": 61,
        "soixante-deux": 62, "soixante-trois": 63, "soixante-quatre": 64, "soixante-cinq": 65,
        "soixante-six": 66, "soixante-sept": 67, "soixante-huit": 68, "soixante-neuf": 69,
        
        # 70-79 (système belge/suisse: septante)
        "septante": 70, "septante-et-un": 71, "septante-deux": 72, "septante-trois": 73,
        "septante-quatre": 74, "septante-cinq": 75, "septante-six": 76, "septante-sept": 77,
        "septante-huit": 78, "septante-neuf": 79,
        
        # 70-79 (système français: soixante-dix)
        "soixante-dix": 70, "soixante-et-onze": 71, "soixante-douze": 72, "soixante-treize": 73,
        "soixante-quatorze": 74, "soixante-quinze": 75, "soixante-seize": 76, "soixante-dix-sept": 77,
        "soixante-dix-huit": 78, "soixante-dix-neuf": 79,
        
        # 80-89 (système belge/suisse: huitante/octante)
        "huitante": 80, "octante": 80,
        "huitante-et-un": 81, "huitante-deux": 82, "huitante-trois": 83, "huitante-quatre": 84,
        "huitante-cinq": 85, "huitante-six": 86, "huitante-sept": 87, "huitante-huit": 88, "huitante-neuf": 89,
        
        # 80-89 (système français: quatre-vingt)
        "quatre-vingt": 80, "quatre-vingts": 80,
        "quatre-vingt-un": 81, "quatre-vingt-une": 81, "quatre-vingt-deux": 82, "quatre-vingt-trois": 83,
        "quatre-vingt-quatre": 84, "quatre-vingt-cinq": 85, "quatre-vingt-six": 86, "quatre-vingt-sept": 87,
        "quatre-vingt-huit": 88, "quatre-vingt-neuf": 89,
        
        # 90-99 (système belge/suisse: nonante)
        "nonante": 90, "nonante-et-un": 91, "nonante-deux": 92, "nonante-trois": 93,
        "nonante-quatre": 94, "nonante-cinq": 95, "nonante-six": 96, "nonante-sept": 97,
        "nonante-huit": 98, "nonante-neuf": 99,
        
        # 90-99 (système français: quatre-vingt-dix)
        "quatre-vingt-dix": 90, "quatre-vingt-onze": 91, "quatre-vingt-douze": 92, "quatre-vingt-treize": 93,
        "quatre-vingt-quatorze": 94, "quatre-vingt-quinze": 95, "quatre-vingt-seize": 96, "quatre-vingt-dix-sept": 97,
        "quatre-vingt-dix-huit": 98, "quatre-vingt-dix-neuf": 99,
        
        # 100-109
        "cent": 100, "cents": 100,
        "cent-un": 101, "cent-une": 101, "cent-deux": 102, "cent-trois": 103, "cent-quatre": 104,
        "cent-cinq": 105, "cent-six": 106, "cent-sept": 107, "cent-huit": 108, "cent-neuf": 109,
        
        # 110-119
        "cent-dix": 110, "cent-onze": 111, "cent-douze": 112, "cent-treize": 113, "cent-quatorze": 114,
        "cent-quinze": 115, "cent-seize": 116, "cent-dix-sept": 117, "cent-dix-huit": 118, "cent-dix-neuf": 119,
        
        # 120-129
        "cent-vingt": 120, "cent-vingt-et-un": 121, "cent-vingt-deux": 122, "cent-vingt-trois": 123,
        "cent-vingt-quatre": 124, "cent-vingt-cinq": 125, "cent-vingt-six": 126, "cent-vingt-sept": 127,
        "cent-vingt-huit": 128, "cent-vingt-neuf": 129,
        
        # 130-139
        "cent-trente": 130, "cent-trente-et-un": 131, "cent-trente-deux": 132, "cent-trente-trois": 133,
        "cent-trente-quatre": 134, "cent-trente-cinq": 135, "cent-trente-six": 136, "cent-trente-sept": 137,
        "cent-trente-huit": 138, "cent-trente-neuf": 139,
        
        # 140-149
        "cent-quarante": 140, "cent-quarante-et-un": 141, "cent-quarante-deux": 142, "cent-quarante-trois": 143,
        "cent-quarante-quatre": 144, "cent-quarante-cinq": 145, "cent-quarante-six": 146, "cent-quarante-sept": 147,
        "cent-quarante-huit": 148, "cent-quarante-neuf": 149,
        
        # 150
        "cent-cinquante": 150,
        
        # Cas spéciaux utiles pour la Bible
        "deux-cents": 200, "deux-cent": 200,
    }
    
    text = text.lower().strip()
    
    # Cas direct (nombre simple dans le dictionnaire)
    if text in french_numbers:
        return str(french_numbers[text])
    
    # Cas non trouvé : essayer de décomposer (fallback)
    # Remplacer espaces par tirets
    text_normalized = text.replace(" et ", "-").replace(" ", "-")
    
    if text_normalized in french_numbers:
        return str(french_numbers[text_normalized])
    
    # Si toujours pas trouvé, retourner "1" par défaut
    return "1"

def extract_verses_with_timestamps(source_text_path, srt_path):
    """
    ✅ FONCTION PRINCIPALE HYBRIDE
    
    Combine les forces des deux approches :
    1. Détecte les versets dans le texte source (100% fiable)
    2. Cherche chaque verset dans le SRT avec recherche exhaustive
    3. Retourne les métadonnées complètes avec timestamps
    
    Returns:
        Liste de dictionnaires avec :
        - reference: Référence formatée (ex: "PSAUMES 34:18")
        - text: Texte complet du verset
        - start_time_ms: Timestamp de début
        - end_time_ms: Timestamp de fin
        - start_time: Timecode formaté
        - end_time: Timecode formaté
    """
    import re
    
    print("\n" + "="*80)
    print("🎯 EXTRACTION DES VERSETS AVEC TIMESTAMPS (MÉTHODE HYBRIDE)")
    print("="*80)
    
    # ============================================================
    # ÉTAPE 1 : Détecter TOUS les versets dans le texte source
    # ============================================================
    print("\n📖 ÉTAPE 1/3 : Détection des versets dans le texte source...")
    
    with open(source_text_path, 'r', encoding='utf-8') as f:
        source_text = f.read()
    
    # Pattern pour extraire les versets (entre guillemets français ou anglais)
    verse_pattern = r'[«"]([^»"]{30,}?)[»"]'
    verse_matches = re.findall(verse_pattern, source_text)
    
    # Nettoyer les versets
    detected_verses = []
    for verse_text in verse_matches:
        verse_clean = verse_text.strip()
        # Filtrer les citations trop courtes (moins de 30 caractères)
        if len(verse_clean) >= 30:
            detected_verses.append(verse_clean)
    
    print(f"   ✅ {len(detected_verses)} verset(s) détecté(s) dans le source")
    for i, v in enumerate(detected_verses, 1):
        print(f"      #{i}: {v[:60]}...")
    
    # ============================================================
    # ÉTAPE 2 : Charger et parser le SRT
    # ============================================================
    print("\n📖 ÉTAPE 2/3 : Chargement du fichier SRT...")
    
    subtitles = parse_srt_file(srt_path)
    print(f"   ✅ {len(subtitles)} sous-titres chargés")
    
    # ============================================================
    # ÉTAPE 3 : Chercher chaque verset dans le SRT
    # ============================================================
    print("\n📖 ÉTAPE 3/3 : Recherche exhaustive des versets dans le SRT...")
    
    verses_with_timestamps = []
    
    for verse_idx, verse_source in enumerate(detected_verses, 1):
        print(f"\n   🔍 Verset #{verse_idx} : {verse_source[:60]}...")
        
        # Normaliser le texte du verset pour la recherche
        verse_normalized = normalize_text_for_search(verse_source)
        
        # Chercher ce verset dans le SRT
        best_match = find_verse_in_srt(verse_normalized, subtitles)
        
        if best_match:
            # Extraire la référence biblique associée
            reference = extract_reference_from_source(verse_source, source_text)
            
            verses_with_timestamps.append({
                'reference': reference,
                'text': verse_source,
                'start_time_ms': best_match['start_time'],
                'end_time_ms': best_match['end_time'],
                'start_time': ms_to_timecode(best_match['start_time']),
                'end_time': ms_to_timecode(best_match['end_time']),
                'coverage': best_match['coverage']
            })
            
            print(f"      ✅ Trouvé : {best_match['start_time']/1000:.2f}s → {best_match['end_time']/1000:.2f}s")
            print(f"      📊 Couverture : {best_match['coverage']*100:.1f}%")
            print(f"      📍 Référence : {reference}")
        else:
            print(f"      ❌ NON TROUVÉ dans le SRT")
    
    # ============================================================
    # RÉSUMÉ
    # ============================================================
    print(f"\n{'='*80}")
    print(f"✅ RÉSULTAT : {len(verses_with_timestamps)}/{len(detected_verses)} verset(s) trouvé(s)")
    print(f"{'='*80}\n")
    
    return verses_with_timestamps

def save_verses_metadata(linked_verses, output_path):
    """
    Sauvegarde les métadonnées des versets dans un fichier JSON.
    
    Ce fichier sera utilisé par la prochaine étape pour générer les overlays.
    """
    import json
    
    metadata = {
        "bible_verses": linked_verses,
        "total_verses": len(linked_verses),
        "generated_at": datetime.now().isoformat()
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Métadonnées sauvegardées : {output_path}")
    print(f"   Total versets : {len(linked_verses)}")
    
    return output_path

#########################################################################################################
# New Fonction Added For Verses Detection: End
#########################################################################################################


##############################
# PARTIE 4 – GÉNÉRATION DES OVERLAYS BIBLIQUES
##############################

def escape_ffmpeg_text(t):
    """
    Échappement pour drawtext dans filter_complex_script (Windows FFmpeg).
    
    Règles critiques:
    1. Remplacer les caractères UTF-8 par des séquences ASCII safe
    2. Point-virgule ; → \\; (sinon FFmpeg le voit comme séparateur de filtres)
    3. Deux-points : → \\: (séparateur d'arguments FFmpeg)
    4. Apostrophe ' → \\' (pour échapper dans le texte entre quotes)
    """
    # ÉTAPE 1: Remplacer les caractères accentués AVANT les échappements
    # Cela évite les problèmes d'encodage Windows
    accents_map = {
        'à': 'a', 'â': 'a', 'á': 'a', 'ä': 'a',
        'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
        'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
        'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o',
        'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c',
        'À': 'A', 'Â': 'A', 'Á': 'A', 'Ä': 'A',
        'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
        'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
        'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Ö': 'O',
        'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
        'Ç': 'C'
    }
    
    for accent, replacement in accents_map.items():
        t = t.replace(accent, replacement)
    
    # ÉTAPE 2: Échapper les caractères spéciaux FFmpeg
    t = t.replace(":", "\\:")      # deux-points
    t = t.replace(";", "\\;")      # point-virgule ⚠️ CRITIQUE
    t = t.replace("'", "\\'")      # apostrophe
    
    return t

def create_ffmpeg_drawtext_filter(verse_metadata, video_duration):
    """
    Crée un filtre FFmpeg drawtext pour afficher un verset biblique avec overlay.
    Version CORRIGÉE pour Windows.
    """
    start_ms = verse_metadata['start_time_ms']
    end_ms = verse_metadata['end_time_ms']
    reference = verse_metadata['reference']
    text = verse_metadata['text']
    
    # Convertir en secondes
    start_sec = start_ms / 1000.0
    end_sec = end_ms / 1000.0
    
    # Échapper le texte
    reference_escaped = escape_ffmpeg_text(reference)
    text_escaped = escape_ffmpeg_text(text)
    
    filters = []
    
    # 1. Overlay sombre (fond noir semi-transparent)
    overlay_filter = (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.75:t=fill:"
        f"enable=between(t\\,{start_sec}\\,{end_sec})"
    )
    filters.append(overlay_filter)
    
    # 2. Référence biblique (en haut, doré/jaune)
    # ATTENTION: 4 backslashes en Python = 2 dans le fichier = 1 pour FFmpeg
    reference_filter = (
        f"drawtext=fontfile=C\\\\\\\\:/Windows/Fonts/montserrat-bold.ttf:"
        f"text='{reference_escaped}':"
        f"fontcolor=gold:"
        f"fontsize=48:"
        f"x=(w-text_w)/2:"
        f"y=150:"
        f"shadowcolor=black@0.8:shadowx=3:shadowy=3:"
        f"enable=between(t\\,{start_sec}\\,{end_sec})"
    )
    filters.append(reference_filter)
    
    # 3. Texte du verset (centré, blanc)
    max_chars_per_line = 60
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars_per_line:
            current_line += (" " if current_line else "") + word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    # Limiter à 4 lignes maximum
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] += "..."
    
    # Créer un drawtext par ligne
    line_height = 50
    total_height = len(lines) * line_height
    start_y = (1080 - total_height) / 2
    
    for i, line in enumerate(lines):
        line_escaped = escape_ffmpeg_text(line)
        y_pos = start_y + (i * line_height)
        
        text_filter = (
            f"drawtext=fontfile=C\\\\\\\\:/Windows/Fonts/montserrat-regular.ttf:"
            f"text='{line_escaped}':"
            f"fontcolor=white:"
            f"fontsize=36:"
            f"x=(w-text_w)/2:"
            f"y={y_pos}:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
        filters.append(text_filter)
    
    return filters

def generate_video_with_bible_overlays(input_video, input_audio, metadata_json_path, 
                                       normal_srt_path, output_video):
    """
    VERSION FINALE CORRIGÉE
    - Timestamps directs du JSON (déjà corrects)
    - Branding permanent avec shadow pour lisibilité
    - Branding redessiné par-dessus chaque overlay
    """
    import json
    import subprocess
    import os
    import re
    
    print("\n" + "="*80)
    print("🎬 GÉNÉRATION VIDÉO - OVERLAYS BIBLIQUES (VERSION FINALE)")
    print("="*80)
    
    # Charger les métadonnées
    with open(metadata_json_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    verses = metadata['bible_verses']
    
    print(f"\n📖 {len(verses)} verset(s) à afficher")
    
    # ========== ÉTAPE 1: SRT MASQUÉ ==========
    print("\n🎭 Étape 1/3 : Masquage des sous-titres pendant les overlays...")
    
    masked_srt = os.path.join(os.path.dirname(output_video), "subtitles_masked.srt")
    
    with open(normal_srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()
    
    subtitle_pattern = r'(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})\n((?:.*\n?)+?)(?=\n\d+\n|\Z)'
    
    # Utiliser les timestamps DIRECTEMENT du JSON
    verse_times = []
    for verse in verses:
        start_ms = verse['start_time_ms']
        end_ms = verse['end_time_ms']
        verse_times.append((start_ms, end_ms))
        
        print(f"\n  📖 {verse['reference']}")
        print(f"     Timestamps JSON : {start_ms}ms → {end_ms}ms")
        print(f"     Overlay affiché : {start_ms/1000:.2f}s → {end_ms/1000:.2f}s")
    
    def srt_time_to_ms(h, m, s, ms):
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    
    kept_subtitles = []
    masked_count = 0
    
    for match in re.finditer(subtitle_pattern, srt_content, re.MULTILINE):
        sub_start = srt_time_to_ms(*match.groups()[1:5])
        sub_end = srt_time_to_ms(*match.groups()[5:9])
        
        is_masked = False
        for verse_start, verse_end in verse_times:
            if not (sub_end < verse_start or sub_start > verse_end):
                is_masked = True
                masked_count += 1
                break
        
        if not is_masked:
            kept_subtitles.append(match.group(0))
    
    with open(masked_srt, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(kept_subtitles))
    
    print(f"\n✅ SRT masqué créé")
    print(f"   Sous-titres conservés : {len(kept_subtitles)}")
    print(f"   Sous-titres masqués   : {masked_count}")
    
    # ========== ÉTAPE 2: VIDÉO + SOUS-TITRES ==========
    print("\n📝 Étape 2/3 : Application des sous-titres...")
    
    video_with_subs = os.path.join(os.path.dirname(output_video), "temp_with_subs.mp4")
    
    abs_srt = os.path.abspath(masked_srt)
    srt_for_vf = abs_srt.replace('\\', '/').replace(':', '\\:')
    
    cmd_subs = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", f"subtitles='{srt_for_vf}':force_style='FontName=Montserrat ExtraLight,FontSize=18,OutlineColour=&H000000&,BorderStyle=1,Outline=1,Alignment=10,MarginV=0,MarginL=0,MarginR=0'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-an",
        video_with_subs
    ]
    
    try:
        subprocess.run(cmd_subs, check=True, capture_output=True, text=True)
        print("✅ Sous-titres appliqués")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur sous-titres: {e.stderr[-1000:]}")
        return
    
    # ========== ÉTAPE 3: OVERLAYS BIBLIQUES ==========
    print("\n🎨 Étape 3/3 : Génération des overlays bibliques...")
    
    filters = []
    text_files = []
    
    # ✅ BRANDING PERMANENT avec SHADOW pour lisibilité
    branding_file = os.path.join(os.path.dirname(output_video), "branding.txt")
    with open(branding_file, 'w', encoding='utf-8') as f:
        f.write("La Sagesse Du Christ")
    text_files.append(branding_file)
    
    branding_escaped = branding_file.replace('\\', '/').replace(':', '\\:')
    
    # ✅ Branding permanent avec shadow pour meilleure lisibilité
    filters.append(
        f"drawtext=textfile='{branding_escaped}':"
        f"fontsize=24:fontcolor=white@0.9:x=20:y=20:"
        f"shadowcolor=black@0.8:shadowx=2:shadowy=2"
        # Visible tout au long SAUF pendant les overlays (sera redessiné par-dessus)
    )
    
    print("✅ Branding permanent ajouté (avec shadow pour lisibilité)")
    
    # ========== OVERLAYS DES VERSETS ==========
    for i, verse in enumerate(verses, 1):
        # TIMESTAMPS DIRECTS - AUCUN OFFSET AJOUTÉ
        start_sec = verse['start_time_ms'] / 1000.0
        end_sec = verse['end_time_ms'] / 1000.0
        
        reference = verse['reference']
        text = verse['text']
        
        print(f"\n  🎬 Verset #{i}: {reference}")
        print(f"     Overlay: {start_sec:.2f}s → {end_sec:.2f}s")
        
        # ASSOMBRISSEMENT LÉGER DE LA VIDÉO (réduit la luminosité pour créer une ambiance)
        # Applique un assombrissement subtil sur toute la vidéo pendant l'overlay
        filters.append(
            f"eq=brightness=-0.10:contrast=0.85:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
        
        # FOND SOMBRE (noir/gris, plus transparent pour laisser voir les couleurs)
        # Zone référence : fond noir semi-transparent (75% opaque) pour garder le côté sombre
        filters.append(
            f"drawbox=x=0:y=0:w=iw:h=200:color=black@0.70:t=fill:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
        # Zone texte : fond très transparent (30% opaque) pour laisser voir l'arrière-plan assombri
        filters.append(
            f"drawbox=x=0:y=200:w=iw:h=880:color=black@0.25:t=fill:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
        
        # RÉFÉRENCE BIBLIQUE
        ref_file = os.path.join(os.path.dirname(output_video), f"verse_{i}_ref.txt")
        with open(ref_file, 'w', encoding='utf-8') as f:
            f.write(reference)
        text_files.append(ref_file)
        
        ref_file_escaped = ref_file.replace('\\', '/').replace(':', '\\:')
        
        filters.append(
            f"drawtext=textfile='{ref_file_escaped}':"
            f"fontsize=60:fontcolor=white:x=(w-text_w)/2:y=90:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
        
        # TEXTE DU VERSET - Division en lignes
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if not current_line:
                current_line = word
            else:
                test_line = current_line + " " + word
                if len(test_line) <= 50:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
        
        if current_line:
            lines.append(current_line)
        
        if len(lines) > 8:
            lines = lines[:8]
            lines[-1] += "..."
        
        print(f"     Lignes de texte: {len(lines)}")
        
        y_positions = [280, 340, 400, 460, 520, 580, 640, 700]
        
        for j, line in enumerate(lines):
            y_pos = y_positions[j]
            
            line_file = os.path.join(os.path.dirname(output_video), f"verse_{i}_line_{j}.txt")
            with open(line_file, 'w', encoding='utf-8') as f:
                f.write(line)
            text_files.append(line_file)
            
            line_file_escaped = line_file.replace('\\', '/').replace(':', '\\:')
            
            filters.append(
                f"drawtext=textfile='{line_file_escaped}':"
                f"fontsize=38:fontcolor=white:x=(w-text_w)/2:y={y_pos}:"
                f"shadowcolor=black@0.8:shadowx=2:shadowy=2:"
                f"enable=between(t\\,{start_sec}\\,{end_sec})"
            )
        
        # ✅ BRANDING REDESSINÉ PAR-DESSUS CET OVERLAY
        # Ceci assure que le branding est toujours visible même pendant l'overlay
        filters.append(
            f"drawtext=textfile='{branding_escaped}':"
            f"fontsize=24:fontcolor=white@0.9:x=20:y=20:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:"
            f"enable=between(t\\,{start_sec}\\,{end_sec})"
        )
    
    # Assembler tous les filtres
    filter_vf = ",".join(filters)
    
    print(f"\n{'='*70}")
    print(f"Total filtres FFmpeg : {len(filters)}")
    print(f"{'='*70}")
    
    # ========== ENCODAGE FINAL ==========
    print(f"\n🎥 Encodage final...")
    
    cmd_final = [
        "ffmpeg", "-y",
        "-i", video_with_subs,
        "-i", input_audio,
        "-vf", filter_vf,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        output_video
    ]
    
    try:
        subprocess.run(cmd_final, check=True, capture_output=True, text=True)
        
        print(f"\n{'='*80}")
        print("✅ SUCCÈS - VIDÉO FINALE GÉNÉRÉE!")
        print(f"{'='*80}")
        print(f"📹 Fichier: {output_video}")
        print(f"📖 Versets avec overlays: {len(verses)}")
        print(f"✅ Timestamps directs du JSON")
        print(f"✅ Branding PERMANENT avec shadow")
        print(f"✅ Branding TOUJOURS visible (même sur overlays)")
        print(f"{'='*80}\n")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ERREUR FFmpeg:")
        print(e.stderr[-2000:])
        return
    
    # ========== NETTOYAGE ==========
    print("🧹 Nettoyage des fichiers temporaires...")
    
    if os.path.exists(video_with_subs):
        os.remove(video_with_subs)
    if os.path.exists(masked_srt):
        os.remove(masked_srt)
    
    for text_file in text_files:
        if os.path.exists(text_file):
            os.remove(text_file)
    
    print("✅ Nettoyage terminé\n")
    
    print("="*80)
    print("🎉 GÉNÉRATION TERMINÉE AVEC SUCCÈS!")
    print("="*80)

def generate_final_video_standard(video_input, audio_input, subtitle_file, output):
    """
    Génère la vidéo finale en mode STANDARD (sans overlays bibliques).
    
    - Incruste les sous-titres
    - Ajoute le branding permanent
    - Combine vidéo + audio
    """
    print("\n🎬 Génération de la vidéo finale (MODE STANDARD)...")
    
    # Échapper le chemin du SRT pour FFmpeg (Windows)
    abs_sub = os.path.abspath(subtitle_file)
    
    # Handle Windows path
    if len(abs_sub) > 1 and abs_sub[1] == ':':
        drive_letter = abs_sub[0]
        path_remainder = abs_sub[2:].replace('\\', '/')
        abs_sub = drive_letter + '\\:' + path_remainder
    else:
        abs_sub = abs_sub.replace('\\', '/')
    
    # Créer le filtre vidéo : branding + sous-titres
    vf_filter = (
        "drawtext=text='La Sagesse Du Christ':"
        "fontfile='C\\:/Windows/Fonts/montserrat-regular.ttf':"
        "fontsize=24:fontcolor=white@0.9:x=20:y=20:"
        "shadowcolor=black@0.8:shadowx=2:shadowy=2,"
        f"subtitles=filename='{abs_sub}':"
        "force_style='FontName=Montserrat ExtraLight,FontSize=18,"
        "OutlineColour=&H000000&,BorderStyle=1,Outline=1,Alignment=10,"
        "MarginV=0,MarginL=0,MarginR=0'"
    )
    
    # Commande FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-i", video_input,
        "-i", audio_input,
        "-vf", vf_filter,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        output
    ]
    
    print("🎥 Encodage de la vidéo finale...")
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ Vidéo finale générée : {output}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERREUR FFmpeg:")
        print(e.stderr[-2000:])
        return False

##############################
# PIPELINE INTÉGRÉ
##############################

def main():
    """
    Pipeline complet pour générer une vidéo avec audio, sous-titres et vidéo de fond bouclée.
    Utilise une mini vidéo qui sera bouclée pour créer la vidéo de fond.
    """
    print("🚀 Démarrage du pipeline Video_Generator_Simple")
    print("🧠 Mode INTELLIGENT activé - Détection automatique des transitions de prière")
    print(f"📁 Dossier de travail: {WORKING_DIR}")
    print(f"📁 Dossier de sortie: {OUTPUT_DIR}")
    
    # PARTIE 1 – Génération audio
    input_script = os.path.join(WORKING_DIR, "script_video.txt")
    if not os.path.exists(input_script):
        print(f"❌ Le fichier script_video.txt n'existe pas dans : {WORKING_DIR}")
        return
    
    audio_parts = process_audio_generation(input_script)
    if not audio_parts:
        print("❌ Aucun fichier audio généré.")
        return
    
    # Merge audio parts
    merged_audio = os.path.join(OUTPUT_DIR, "full_audio.mp3")
    merge_audio_files(audio_parts, merged_audio)
    
    # Boost audio volume
    boosted_audio = os.path.join(OUTPUT_DIR, "full_audio_boosted.mp3")
    boost_audio(merged_audio, boosted_audio, boost_db=10)
    
    # PARTIE 2 – Génération du SRT avec le sous-module srt_generator
    final_srt = os.path.join(OUTPUT_DIR, "final_subtitles.srt")
    generate_srt_with_srt_generator(boosted_audio, final_srt)
    
    # PARTIE 2.5 – TRAITEMENT INTELLIGENT : Détection des transitions de prière
    print("\n🧠 TRAITEMENT INTELLIGENT - Analyse des transitions de prière...")
    transition_points = detect_prayer_transitions(final_srt)
    
    if transition_points:
        print(f"✅ {len(transition_points)} transition(s) détectée(s)")
        
        # Insérer les silences dans l'audio boosté
        boosted_audio_with_pauses = os.path.join(OUTPUT_DIR, "full_audio_boosted_with_pauses.mp3")
        insert_silence_in_audio(boosted_audio, boosted_audio_with_pauses, transition_points, pause_duration=3.0)
        
        # Ajuster le SRT avec les nouvelles pauses
        final_srt_adjusted = os.path.join(OUTPUT_DIR, "final_subtitles_adjusted.srt")
        adjust_srt_with_pauses(final_srt, final_srt_adjusted, transition_points, pause_duration_ms=3000)
        
        # Utiliser les fichiers ajustés pour la suite
        boosted_audio = boosted_audio_with_pauses
        final_srt = final_srt_adjusted
        print("🎯 Fichiers audio et SRT ajustés avec les pauses de méditation")
    else:
        print("ℹ️  Aucune transition détectée, pipeline standard utilisé")
    
    # PARTIE 2.6 – AMÉLIORATION DU SRT (correction guillemets bibliques)
    print("\n📖 ÉTAPE 2.6/7 : Amélioration du SRT (correction guillemets)...")
    source_text_path = os.path.join(OUTPUT_DIR, "script_nettoye.txt")
    
    # ✅ NOUVELLE FONCTION HYBRIDE (remplace les 3 anciennes fonctions)
    verses_with_timestamps = extract_verses_with_timestamps(source_text_path, final_srt)
    
    # PARTIE 3 – Génération vidéo avec vidéo bouclée
    audio_duration = get_audio_duration(boosted_audio)
    print(f"\n📊 Durée de l'audio final (avec pauses éventuelles): {audio_duration:.1f} secondes")
    background_video = os.path.join(OUTPUT_DIR, "background_video.mp4")
    prepare_background_video(audio_duration, background_video)
    
    background_music = select_random_background_music()
    mixed_audio = os.path.join(OUTPUT_DIR, "mixed_audio.m4a")
    mix_audio_with_background_delayed(boosted_audio, background_music, mixed_audio, voice_delay_seconds=2)
    
    # PARTIE 4 – Génération vidéo finale (avec ou sans overlays)
    
    # Créer SRT décalé de 2 secondes
    shifted_srt = os.path.join(OUTPUT_DIR, "subtitles_shifted.srt")
    shift_srt_timing(final_srt, shifted_srt, delay_seconds=2)
    
    if verses_with_timestamps:
        print("\\n🎨 ÉTAPE 4/7 : Génération vidéo finale avec overlays bibliques...")
        
        # ✅ AJUSTER LES TIMESTAMPS DES VERSETS POUR LE SHIFT (+2s)
        verses_shifted = []
        for verse in verses_with_timestamps:
            verse_shifted = verse.copy()
            verse_shifted['start_time_ms'] += 2000  # +2 secondes
            verse_shifted['end_time_ms'] += 2000
            verse_shifted['start_time'] = ms_to_timecode(verse_shifted['start_time_ms'])
            verse_shifted['end_time'] = ms_to_timecode(verse_shifted['end_time_ms'])
            verses_shifted.append(verse_shifted)
        
        # Sauvegarder les métadonnées
        metadata_path_final = os.path.join(OUTPUT_DIR, "bible_verses_metadata.json")
        save_verses_metadata(verses_shifted, metadata_path_final)
        
        # Générer la vidéo avec overlays
        final_video = os.path.join(OUTPUT_DIR, "final_video_with_overlays.mp4")
        generate_video_with_bible_overlays(
            background_video, 
            mixed_audio, 
            metadata_path_final,
            shifted_srt, 
            final_video
        )
        
        print("\\n" + "="*80)
        print("🎉 PIPELINE COMPLET TERMINÉ - MODE INTELLIGENT")
        print("="*80)
        print(f"🎬 Vidéo finale      : {final_video}")
        print(f"📖 Versets overlays  : {len(verses_shifted)}")
        print(f"⏸️  Pauses prière     : {len(transition_points) if transition_points else 0}")
        print(f"📁 Dossier sortie    : {OUTPUT_DIR}")
        print("="*80 + "\\n")
    
    else:
        # ✅ MODE STANDARD (sans overlays)
        print("\\n⚠️  Aucun verset biblique détecté")
        print("🎬 Génération en MODE STANDARD (sans overlays)...\\n")
        
        final_video = os.path.join(OUTPUT_DIR, "final_video_standard.mp4")
        
        success = generate_final_video_standard(
            background_video,
            mixed_audio,
            shifted_srt,
            final_video
        )
        
        if success:
            print("\\n" + "="*80)
            print("🎉 PIPELINE COMPLET TERMINÉ - MODE STANDARD")
            print("="*80)
            print(f"🎬 Vidéo finale      : {final_video}")
            print(f"📖 Mode             : Standard (sans overlays bibliques)")
            print(f"⏸️  Pauses prière     : {len(transition_points) if transition_points else 0}")
            print(f"📁 Dossier sortie    : {OUTPUT_DIR}")
            print("="*80 + "\\n")
        else:
            print("\\n❌ Échec de la génération de la vidéo finale")

if __name__ == "__main__":
    main()

