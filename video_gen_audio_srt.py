import os
import re
from datetime import datetime
import difflib
import sys
import random
import subprocess
import shutil

# Fix pour l'encodage Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Définir le dossier de travail pour les fichiers d'entrée
WORKING_DIR = os.path.join(os.getcwd(), "working_dir_audio_srt")

# Créer le dossier de sortie : exemple "Project_DDMMYYYY_HHMMSS"
OUTPUT_DIR = "Project_" + datetime.now().strftime("%d%m%Y_%H%M%S")
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

##############################
# FONCTIONS UTILITAIRES
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

def normalize_video(input_video, output_video):
    """
    Normalise une vidéo à 1920x1080, 30fps, H264.
    Utilise NVENC si disponible, sinon QSV, sinon CPU.
    """
    print(f"  🔄 Normalisation: {os.path.basename(input_video)}")
    
    # Commande NVENC (GPU NVIDIA)
    cmd_nvenc = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-c:v", "h264_nvenc",
        "-preset", "fast",
        "-profile:v", "high",
        "-cq", "23",
        "-rc:v", "vbr",
        "-maxrate", "8M",
        "-bufsize", "16M",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-an",
        "-movflags", "+faststart",
        output_video
    ]
    
    # Fallback Intel QSV
    cmd_qsv = [
        "ffmpeg", "-y",
        "-hwaccel", "qsv",
        "-i", input_video,
        "-c:v", "h264_qsv",
        "-preset", "faster",
        "-global_quality", "20",
        "-look_ahead", "1",
        "-vf", "scale_qsv=1920:1080:force_original_aspect_ratio=decrease",
        "-pix_fmt", "nv12",
        "-r", "30",
        "-an",
        "-movflags", "+faststart",
        output_video
    ]
    
    # Fallback CPU
    cmd_cpu = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "20",
        "-threads", "0",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-an",
        output_video
    ]
    
    # Essayer NVENC en premier
    try:
        subprocess.run(cmd_nvenc, check=True, capture_output=True)
        print(f"    ✅ Normalisé avec NVENC")
        return True
    except:
        pass
    
    # Essayer QSV
    try:
        subprocess.run(cmd_qsv, check=True, capture_output=True)
        print(f"    ✅ Normalisé avec QSV")
        return True
    except:
        pass
    
    # Fallback CPU
    try:
        subprocess.run(cmd_cpu, check=True, capture_output=True)
        print(f"    ✅ Normalisé avec CPU")
        return True
    except Exception as e:
        print(f"    ❌ Erreur de normalisation: {e}")
        return False

def generate_background_video_from_local(target_duration, output_video):
    """
    Génère une vidéo de fond en utilisant des vidéos locales du dossier videos_db.
    """
    # Ajouter 4 secondes à la durée cible (2s avant + 2s après)
    extended_duration = target_duration + 4
    print(f"🔄 Génération vidéo de fond pour {extended_duration:.1f}s (audio: {target_duration:.1f}s + 4s marge)...")
    
    videos_dir = os.path.join(os.getcwd(), "videos_db")
    
    if not os.path.exists(videos_dir):
        raise FileNotFoundError(f"Le dossier videos_db n'existe pas : {videos_dir}")
    
    # Lister tous les fichiers vidéo
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    video_files = []
    
    for file in os.listdir(videos_dir):
        if any(file.lower().endswith(ext) for ext in video_extensions):
            video_files.append(os.path.join(videos_dir, file))
    
    if not video_files:
        raise FileNotFoundError(f"Aucun fichier vidéo trouvé dans {videos_dir}")
    
    print(f"📹 {len(video_files)} vidéos disponibles")
    
    # Sélectionner aléatoirement des vidéos
    selected_videos = []
    total_duration = 0
    
    while total_duration < extended_duration:
        video = random.choice(video_files)
        video_duration = get_audio_duration(video)
        selected_videos.append(video)
        total_duration += video_duration
        print(f"  ✓ {os.path.basename(video)} ({video_duration:.1f}s) - Total: {total_duration:.1f}s")
    
    print(f"📊 {len(selected_videos)} vidéo(s) sélectionnée(s)")
    
    # Créer dossier temporaire
    temp_dir = os.path.join(OUTPUT_DIR, "temp_normalized")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # Normaliser chaque vidéo
    print(f"🔧 Normalisation à 1920x1080@30fps...")
    normalized_videos = []
    for i, video in enumerate(selected_videos):
        normalized_path = os.path.join(temp_dir, f"normalized_{i}.mp4")
        if normalize_video(video, normalized_path):
            normalized_videos.append(normalized_path)
    
    if not normalized_videos:
        raise Exception("Aucune vidéo n'a pu être normalisée")
    
    # Concaténer ou découper
    if len(normalized_videos) == 1:
        cmd = [
            "ffmpeg", "-y",
            "-i", normalized_videos[0],
            "-t", str(extended_duration),
            "-c:v", "copy",
            "-an",
            output_video
        ]
        subprocess.run(cmd, check=True)
    else:
        concat_file = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            for video in normalized_videos:
                f.write(f"file '{os.path.abspath(video)}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-t", str(extended_duration),
            "-c:v", "copy",
            "-an",
            output_video
        ]
        subprocess.run(cmd, check=True)
    
    # Nettoyer
    shutil.rmtree(temp_dir)
    print(f"✅ Vidéo de fond générée : {output_video}")
    
    return output_video

def mix_audio_with_background_delayed(voice_audio, bg_music, output, voice_delay_seconds=2):
    """
    Mixe l'audio principal avec la musique d'ambiance.
    """
    voice_duration = get_audio_duration(voice_audio)
    total_duration = voice_duration + 4
    
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
    print(f"✅ Audio mixé : {output} (durée: {total_duration:.1f}s)")

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
    """
    Détecte les phrases de transition vers la prière dans le fichier SRT.
    Retourne une liste des timestamps (en ms) où insérer des pauses.
    """
    subtitles = parse_srt_file(srt_path)
    
    # Patterns de transition (insensible à la casse)
    transition_patterns = [
        r'maintenant[\s,]+prions',
        r'maintenant[\s,]+prions[\s,]+le[\s,]+seigneur',
        r'maintenant[\s,]+prions[\s,]+dieu',
        r'prions[\s,]+ensemble',
        r'prions[\s,]+maintenant',
        r'alors[\s,]+prions',
    ]
    
    transition_points = []
    
    for subtitle in subtitles:
        text_lower = subtitle['text'].lower()
        
        # Vérifier si le texte contient une des phrases de transition
        for pattern in transition_patterns:
            if re.search(pattern, text_lower):
                print(f"🔍 Transition détectée : '{subtitle['text']}' à {subtitle['end_time']/1000:.2f}s")
                transition_points.append(subtitle['end_time'])
                break  # Une seule détection par sous-titre
    
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
    "genese": "GENÈSE", "exode": "EXODE", "levitique": "LÉVITIQUE", "nombres": "NOMBRES", 
    "deuteronome": "DEUTÉRONOME", "josue": "JOSUÉ", "juges": "JUGES", "ruth": "RUTH",
    "1 samuel": "1 SAMUEL", "premier samuel": "1 SAMUEL", "2 samuel": "2 SAMUEL", 
    "deuxieme samuel": "2 SAMUEL", "second samuel": "2 SAMUEL",
    "1 rois": "1 ROIS", "premier rois": "1 ROIS", "2 rois": "2 ROIS", 
    "deuxieme rois": "2 ROIS", "second rois": "2 ROIS",
    "1 chroniques": "1 CHRONIQUES", "premiere chroniques": "1 CHRONIQUES",
    "2 chroniques": "2 CHRONIQUES", "deuxieme chroniques": "2 CHRONIQUES",
    "esdras": "ESDRAS", "nehemie": "NÉHÉMIE", "esther": "ESTHER", "job": "JOB",
    "psaumes": "PSAUMES", "psaume": "PSAUMES", "proverbes": "PROVERBES",
    "ecclesiaste": "ECCLÉSIASTE", "cantique des cantiques": "CANTIQUE DES CANTIQUES",
    "esaie": "ÉSAÏE", "jeremie": "JÉRÉMIE", "lamentations": "LAMENTATIONS",
    "ezechiel": "ÉZÉCHIEL", "daniel": "DANIEL", "osee": "OSÉE", "joel": "JOËL",
    "amos": "AMOS", "abdias": "ABDIAS", "jonas": "JONAS", "michee": "MICHÉE",
    "nahum": "NAHUM", "habacuc": "HABACUC", "sophonie": "SOPHONIE", "aggee": "AGGÉE",
    "zacharie": "ZACHARIE", "malachie": "MALACHIE",
    "matthieu": "MATTHIEU", "marc": "MARC", "luc": "LUC", "jean": "JEAN",
    "actes": "ACTES", "romains": "ROMAINS",
    "1 corinthiens": "1 CORINTHIENS", "premier corinthiens": "1 CORINTHIENS",
    "premiere corinthiens": "1 CORINTHIENS", "première corinthiens": "1 CORINTHIENS",
    "2 corinthiens": "2 CORINTHIENS", "deuxieme corinthiens": "2 CORINTHIENS",
    "deuxième corinthiens": "2 CORINTHIENS", "second corinthiens": "2 CORINTHIENS", 
    "seconde corinthiens": "2 CORINTHIENS",
    "galates": "GALATES", "ephesiens": "ÉPHÉSIENS", "philippiens": "PHILIPPIENS",
    "colossiens": "COLOSSIENS",
    "1 thessaloniciens": "1 THESSALONICIENS", "premiere thessaloniciens": "1 THESSALONICIENS",
    "2 thessaloniciens": "2 THESSALONICIENS", "deuxieme thessaloniciens": "2 THESSALONICIENS",
    "1 timothee": "1 TIMOTHÉE", "premiere timothee": "1 TIMOTHÉE",
    "2 timothee": "2 TIMOTHÉE", "deuxieme timothee": "2 TIMOTHÉE",
    "tite": "TITE", "philemon": "PHILÉMON", "hebreux": "HÉBREUX",
    "jacques": "JACQUES", "1 pierre": "1 PIERRE", "premiere pierre": "1 PIERRE",
    "2 pierre": "2 PIERRE", "deuxieme pierre": "2 PIERRE",
    "1 jean": "1 JEAN", "premier jean": "1 JEAN",
    "2 jean": "2 JEAN", "deuxieme jean": "2 JEAN",
    "3 jean": "3 JEAN", "troisieme jean": "3 JEAN",
    "jude": "JUDE", "apocalypse": "APOCALYPSE"
}

# Dictionnaire de conversion des nombres écrits en lettres
NUMBERS_FR = {
    "premier": "1", "premiere": "1", "un": "1", "une": "1",
    "deuxieme": "2", "second": "2", "seconde": "2", "deux": "2",
    "troisieme": "3", "trois": "3", "quatrieme": "4", "quatre": "4",
    "cinquieme": "5", "cinq": "5", "sixieme": "6", "six": "6",
    "septieme": "7", "sept": "7", "huitieme": "8", "huit": "8",
    "neuvieme": "9", "neuf": "9", "dixieme": "10", "dix": "10",
    "onzieme": "11", "onze": "11", "douzieme": "12", "douze": "12",
    "treizieme": "13", "treize": "13", "quatorzieme": "14", "quatorze": "14",
    "quinzieme": "15", "quinze": "15", "seizieme": "16", "seize": "16",
    "dix-sept": "17", "dixsept": "17", "dix-huit": "18", "dixhuit": "18", 
    "dix-neuf": "19", "dixneuf": "19", "vingt": "20",
    "vingt-et-un": "21", "vingt-deux": "22", "vingt-trois": "23", "vingt-quatre": "24",
    "vingt-cinq": "25", "vingt-six": "26", "vingt-sept": "27", "vingt-huit": "28",
    "vingt-neuf": "29", "trente": "30", "trente-et-un": "31", "trente-deux": "32",
    "trente-trois": "33", "trente-quatre": "34", "trente-cinq": "35", "trente-six": "36",
    "trente-sept": "37", "trente-huit": "38", "trente-neuf": "39", "quarante": "40",
    "quarante-et-un": "41", "quarante-deux": "42", "quarante-trois": "43", "quarante-quatre": "44",
    "quarante-cinq": "45", "quarante-six": "46", "quarante-sept": "47", "quarante-huit": "48",
    "quarante-neuf": "49", "cinquante": "50"
}

def parse_number_text(text):
    """Convertit un nombre écrit en lettres en chiffre"""
    text_lower = text.lower().strip()
    
    # Essayer une correspondance directe
    if text_lower in NUMBERS_FR:
        return NUMBERS_FR[text_lower]
    
    # Si c'est déjà un chiffre, le retourner tel quel
    if text_lower.isdigit():
        return text_lower
    
    # Sinon, retourner le texte original (non converti)
    return text_lower

def detect_bible_references_in_source(source_text):
    """
    Détecte les références bibliques dans le texte source.
    
    Patterns supportés:
    - "dans [Livre] chapitre [X], versets [Y]"
    - "en [Livre] [X], verset [Y]"
    - "[Livre] [X], versets [Y]"
    
    Retourne: Liste de dictionnaires avec {original, book, chapter, verses, formatted}
    """
    references = []
    seen_positions = set()  # Pour éviter les doublons
    
    print("\n" + "="*80)
    print("📚 DÉTECTION DES RÉFÉRENCES BIBLIQUES DANS LE TEXTE SOURCE")
    print("="*80)
    
    # Pattern 1: "dans [Livre] chapitre [X], verset(s) [Y]"
    pattern1 = r'dans\s+([A-ZÉÈa-zéèêû]+(?:\s+[A-ZÉÈa-zéèêû]+)*?)\s+chapitre\s+([a-zéèêû\-]+),\s+verset(?:s)?\s+([a-zéèêû\-]+(?:\s+et\s+[a-zéèêû\-]+)*)'
    
    # Pattern 2: "en [Livre] [nombre], verset [Y], dit" (avec "en")
    pattern2 = r'en\s+([A-ZÉÈa-zéèêû]+(?:\s+[A-ZÉÈa-zéèêû]+)*?)\s+([a-zéèêû\-]+),\s+verset\s+([a-zéèêû\-]+),\s+dit'
    
    # Pattern 3: "[Livre] [nombre], verset(s) [Y], dit" (SANS "en" ni "dans")
    pattern3 = r'([A-ZÉÈ][a-zéèêû]+(?:\s+[a-zéèêû]+)?)\s+([a-zéèêû\-]+),\s+verset(?:s)?\s+([a-zéèêû\-]+(?:\s+et\s+[a-zéèêû\-]+)*),\s+dit'
    
    # Pattern 4: "en [Livre] [nombre], verset [Y]" (SANS ", dit" à la fin)
    pattern4 = r'en\s+([A-ZÉÈa-zéèêû]+(?:\s+[A-ZÉÈa-zéèêû]+)*?)\s+([a-zéèêû\-]+),\s+verset\s+([a-zéèêû\-]+)(?!\s*,\s*dit)'
    
    # Ordre important : du plus spécifique au plus général
    patterns = [
        (pattern1, "Format 1: 'dans [Livre] chapitre [X], verset(s) [Y]'"),
        (pattern2, "Format 2: 'en [Livre] [X], verset [Y], dit'"),
        (pattern3, "Format 3: '[Livre] [X], verset(s) [Y], dit'"),
        (pattern4, "Format 4: 'en [Livre] [X], verset [Y]'")
    ]
    
    for pattern, description in patterns:
        for match in re.finditer(pattern, source_text, re.IGNORECASE):
            # Éviter les doublons basés sur la position
            match_pos = match.start()
            if match_pos in seen_positions:
                continue
            
            
            seen_positions.add(match_pos)
            
            book_text = match.group(1).strip()
            chapter_text = match.group(2).strip()
            verses_text = match.group(3).strip()
            
            # Normaliser le nom du livre
            book_normalized = book_text.lower()
            
            # Trouver le livre dans notre dictionnaire (essayer d'abord la correspondance exacte)
            book_display = BIBLE_BOOKS.get(book_normalized)
            
            if not book_display:
                # Essayer avec préfixe (pour "deuxieme corinthiens" → "2 corinthiens")
                for key, value in BIBLE_BOOKS.items():
                    if book_normalized == key or (book_normalized + "s") == key:
                        book_display = value
                        break
            
            if not book_display:
                print(f"   ⚠️  Livre non reconnu : '{book_text}' (Pattern: {description})")
                continue
            
            # Convertir le chapitre en chiffre
            chapter = parse_number_text(chapter_text)
            
            # Parser les versets (gérer "neuf et dix" → "9-10")
            verses_parts = re.split(r'\s+et\s+', verses_text)
            verses_numbers = [parse_number_text(v) for v in verses_parts]
            
            if len(verses_numbers) == 1:
                verses_display = verses_numbers[0]
            else:
                verses_display = f"{verses_numbers[0]}-{verses_numbers[-1]}"
            
            # Format final
            formatted = f"{book_display} {chapter}:{verses_display}"
            
            references.append({
                'original': match.group(0),
                'book': book_display,
                'chapter': chapter,
                'verses': verses_display,
                'formatted': formatted,
                'position': match_pos
            })
            
            print(f"\n📖 RÉFÉRENCE #{len(references)}")
            print(f"   Pattern utilisé : {description}")
            print(f"   Texte original : '{match.group(0)}'")
            print(f"   Livre détecté  : '{book_text}' → {book_display}")
            print(f"   Format final   : {formatted}")
    
    print(f"\n{'='*80}")
    print(f"✅ TOTAL : {len(references)} référence(s) biblique(s) détectée(s)")
    print(f"{'='*80}\n")
    
    return references

def link_references_to_verses(references, verses_data):
    """
    Lie les références bibliques aux versets détectés.
    
    Args:
        references: Liste des références détectées (avec position dans le texte)
        verses_data: Liste des versets avec leurs timestamps SRT
    
    Retourne: Liste de dictionnaires {reference, start_time, end_time, text}
    """
    print("\n" + "="*80)
    print("🔗 LIAISON DES RÉFÉRENCES AUX VERSETS")
    print("="*80)
    
    linked_data = []
    
    # Trier par position dans le texte
    references_sorted = sorted(references, key=lambda x: x['position'])
    verses_sorted = sorted(verses_data, key=lambda x: x.get('position_in_source', 0))
    
    # Associer chaque référence au verset le plus proche
    for i, ref in enumerate(references_sorted):
        if i < len(verses_sorted):
            verse = verses_sorted[i]
            
            linked_data.append({
                'reference': ref['formatted'],
                'start_time': ms_to_timecode(verse['start_time']),
                'end_time': ms_to_timecode(verse['end_time']),
                'text': verse['text'],
                'start_time_ms': verse['start_time'],
                'end_time_ms': verse['end_time']
            })
            
            print(f"\n📖 VERSET #{i+1}")
            print(f"   Référence : {ref['formatted']}")
            print(f"   Timestamps : {ms_to_timecode(verse['start_time'])} --> {ms_to_timecode(verse['end_time'])}")
            print(f"   Texte : «{verse['text'][:60]}...»")
        else:
            print(f"\n⚠️  Référence #{i+1} sans verset correspondant : {ref['formatted']}")
    
    print(f"\n{'='*80}")
    print(f"✅ {len(linked_data)} verset(s) lié(s) avec succès")
    print(f"{'='*80}\n")
    
    return linked_data

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

def shift_srt_timing(input_srt, output_srt, delay_seconds=2):
    """
    Décale tous les timecodes du fichier SRT de delay_seconds secondes.
    """
    with open(input_srt, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern pour matcher les timecodes SRT (HH:MM:SS,mmm --> HH:MM:SS,mmm)
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
        def ms_to_timecode_local(total_ms):
            hours = total_ms // (3600 * 1000)
            minutes = (total_ms % (3600 * 1000)) // (60 * 1000)
            seconds = (total_ms % (60 * 1000)) // 1000
            milliseconds = total_ms % 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
        start_tc = ms_to_timecode_local(start_total_ms)
        end_tc = ms_to_timecode_local(end_total_ms)
        
        return f"{start_tc} --> {end_tc}"
    
    # Remplacer tous les timecodes
    shifted_content = re.sub(timecode_pattern, shift_timecode, content)
    
    with open(output_srt, 'w', encoding='utf-8') as f:
        f.write(shifted_content)
    
    print(f"✅ Fichier SRT décalé de +{delay_seconds}s : {output_srt}")

def normalize_text(text):
    """Normalise le texte pour comparaison (enlève ponctuation, minuscules)"""
    # Enlever ponctuation et normaliser espaces
    text = re.sub(r'[«»"\'.,;:!?—–-]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def detect_bible_verses_in_source(source_text):
    """
    Détecte tous les versets bibliques dans le texte source.
    
    Pattern spécifique : ': «' (deux-points + espace + guillemet français ouvrant)
    Fin du verset : '»' (guillemet français fermant)
    
    Retourne: Liste de dictionnaires avec le texte complet de chaque verset
    """
    verses = []
    
    # Pattern: ': «' suivi de n'importe quoi jusqu'à '»'
    # re.DOTALL pour matcher sur plusieurs lignes
    pattern = r':\s*«\s*([^»]+?)\s*»'
    
    print("\n" + "="*80)
    print("📖 DÉTECTION DES VERSETS BIBLIQUES DANS LE TEXTE SOURCE")
    print("="*80)
    
    for match in re.finditer(pattern, source_text, re.DOTALL):
        verse_text = match.group(1).strip()
        
        # Ignorer les versets très courts (< 15 caractères)
        if len(verse_text) < 15:
            continue
        
        # Normaliser pour comparaison
        normalized = normalize_text(verse_text)
        words = normalized.split()
        first_words = ' '.join(words[:5]) if len(words) >= 5 else normalized
        
        verses.append({
            'content': verse_text,
            'normalized': normalized,
            'first_words': first_words,
            'words_set': set(words),
            'start_pos': match.start()  # Position dans le texte source
        })
        
        print(f"\n{'='*80}")
        print(f"📖 VERSET #{len(verses)}")
        print(f"{'='*80}")
        print(f"Texte complet :")
        print(f"«{verse_text}»")
        print(f"\nLongueur : {len(verse_text)} caractères")
        print(f"Premiers mots : {first_words}")
    
    print(f"\n{'='*80}")
    print(f"✅ TOTAL : {len(verses)} verset(s) biblique(s) détecté(s)")
    print(f"{'='*80}\n")
    
    return verses

def find_verse_in_srt(verse, srt_subtitles):
    """
    Trouve l'emplacement d'un verset dans le SRT - Approche en 2 passes.
    
    PASSE 1: Trouver le DÉBUT précis (les 3 premiers mots consécutifs du verset)
    PASSE 2: Étendre jusqu'à avoir le verset complet (y compris les derniers mots)
    
    Retourne (start_index, end_index) ou None si pas trouvé.
    """
    verse_words = verse['normalized'].split()
    verse_words_set = verse['words_set']
    
    # PASSE 1: Trouver le début précis
    # On cherche les 3 premiers mots du verset dans l'ordre
    first_3_words = ' '.join(verse_words[:3])
    start_idx = None
    
    for i in range(len(srt_subtitles)):
        # Regarder ce sous-titre et les 3 suivants
        window_size = min(4, len(srt_subtitles) - i)
        combined = ' '.join(srt_subtitles[i+j]['text'] for j in range(window_size))
        combined_normalized = normalize_text(combined)
        
        # Vérifier si les 3 premiers mots sont présents dans l'ordre
        if first_3_words in combined_normalized:
            start_idx = i
            break
    
    if start_idx is None:
        return None
    
    # PASSE 2: Trouver la fin en étendant jusqu'à avoir le verset complet
    # IMPORTANT: S'assurer d'avoir aussi les DERNIERS mots du verset
    best_end_idx = start_idx
    best_coverage = 0
    consecutive_no_improvement = 0
    
    for end_idx in range(start_idx, min(start_idx + 30, len(srt_subtitles))):
        combined_text = ' '.join(sub['text'] for sub in srt_subtitles[start_idx:end_idx+1])
        combined_normalized = normalize_text(combined_text)
        combined_words_set = set(combined_normalized.split())
        
        common_words = verse_words_set & combined_words_set
        coverage = len(common_words) / len(verse_words_set) if verse_words_set else 0
        
        # Amélioration de la couverture?
        if coverage > best_coverage:
            best_coverage = coverage
            best_end_idx = end_idx
            consecutive_no_improvement = 0
        else:
            consecutive_no_improvement += 1
            
            # Si pas d'amélioration pendant 3 sous-titres ET on a déjà >85%, arrêter
            if consecutive_no_improvement >= 3 and best_coverage > 0.85:
                break
    
    # ÉTAPE FINALE: Vérifier si le sous-titre suivant termine par un point
    # Si oui, il fait probablement partie du verset (ex: "Jésus Christ.")
    if best_end_idx + 1 < len(srt_subtitles):
        next_subtitle = srt_subtitles[best_end_idx + 1]
        if next_subtitle['text'].rstrip().endswith('.'):
            # Vérifier si ce sous-titre pourrait faire partie du verset
            next_text_norm = normalize_text(next_subtitle['text'])
            next_words = next_text_norm.split()
            # Si le sous-titre suivant est court (1-3 mots) et se termine par un point
            if len(next_words) <= 3 and len(next_text_norm) > 3:
                best_end_idx += 1
    
    # Vérifier qu'on a au moins 70% du verset
    if best_coverage < 0.70:
        return None
    
    # Affiner le début exact (trouver où commence vraiment le contenu du verset)
    actual_start = start_idx
    for i in range(start_idx, min(start_idx + 5, best_end_idx + 1)):
        sub_normalized = normalize_text(srt_subtitles[i]['text'])
        # Compter combien de premiers mots du verset sont dans ce sous-titre
        matches = sum(1 for word in verse_words[:4] if word in sub_normalized)
        if matches >= 2:
            actual_start = i
            break
    
    return (actual_start, best_end_idx, best_coverage)

def correct_verse_quotes(srt_subtitles, start_idx, end_idx, verse):
    """
    Corrige les guillemets pour un verset donné.
    
    Règles:
    1. Si "dit «" existe juste avant le verset → GARDER ce «
    2. Sinon → Placer « au début du verset
    3. Nettoyer tous les » parasites sauf à la fin
    4. Placer » à la fin du verset
    
    Retourne True si correction effectuée, False sinon.
    """
    if start_idx >= len(srt_subtitles) or end_idx >= len(srt_subtitles):
        return False
    
    print(f"    Correction: sous-titres {srt_subtitles[start_idx]['index']} à {srt_subtitles[end_idx]['index']}")
    
    # ÉTAPE 1: Trouver où le verset commence exactement
    verse_start_idx = start_idx
    verse_words = verse['normalized'].split()
    
    for i in range(start_idx, min(start_idx + 5, end_idx + 1)):
        sub_normalized = normalize_text(srt_subtitles[i]['text'])
        matches = sum(1 for word in verse_words[:3] if word in sub_normalized)
        if matches >= 2:
            verse_start_idx = i
            break
    
    print(f"      Début du verset: sous-titre {srt_subtitles[verse_start_idx]['index']}")
    
    # ÉTAPE 2: Vérifier si "dit «" existe juste avant OU dans le début du verset
    has_dit_quote = False
    dit_quote_idx = None
    
    # Chercher "dit «" dans les 2 sous-titres AVANT verse_start_idx ET dans verse_start_idx
    for i in range(max(0, verse_start_idx - 2), verse_start_idx + 1):
        if re.search(r'\bdit\s*«', srt_subtitles[i]['text'], re.IGNORECASE):
            has_dit_quote = True
            dit_quote_idx = i
            print(f"      ✓ 'dit «' trouvé au sous-titre {srt_subtitles[i]['index']} (GARDER)")
            break
    
    # ÉTAPE 3: Nettoyer les guillemets
    for i in range(start_idx, end_idx + 1):
        text = srt_subtitles[i]['text']
        
        if has_dit_quote and i == dit_quote_idx:
            # Garder le « de "dit «", mais enlever les » parasites
            text = re.sub(r'[»""]', '', text).strip()
        else:
            # Enlever tous les guillemets
            text = re.sub(r'[«»""]', '', text).strip()
        
        srt_subtitles[i]['text'] = text
    
    # ÉTAPE 4: Placer le guillemet ouvrant « si nécessaire
    if has_dit_quote:
        # Le « existe déjà dans "dit «", on ne fait rien
        print(f"      Guillemet « déjà présent dans 'dit «' (conservé)")
    else:
        # Pas de "dit «", on doit ajouter le «
        start_text = srt_subtitles[verse_start_idx]['text']
        
        # Vérifier si le sous-titre contient "dit" ou ":"
        if re.search(r'\b(dit|:)\s', start_text, re.IGNORECASE):
            # Placer après "dit" ou ":"
            start_text = re.sub(
                r'(\bdit|:)(\s+)',
                r'\1 « ',
                start_text,
                count=1,
                flags=re.IGNORECASE
            )
            print(f"      Guillemet « placé après 'dit' ou ':'")
        else:
            # Placer au début
            start_text = '« ' + start_text
            print(f"      Guillemet « placé au début")
        
        srt_subtitles[verse_start_idx]['text'] = start_text
    
    # ÉTAPE 5: Placer le guillemet fermant » à la fin
    end_text = srt_subtitles[end_idx]['text']
    
    # Ajouter un point si nécessaire
    if not end_text.rstrip().endswith('.'):
        end_text = end_text.rstrip() + '.'
    
    # Ajouter le guillemet fermant
    end_text = end_text.rstrip() + ' »'
    srt_subtitles[end_idx]['text'] = end_text
    print(f"      Guillemet » placé à la fin")
    
    # ÉTAPE 6: Vérification du contenu
    combined_result = ' '.join(sub['text'] for sub in srt_subtitles[verse_start_idx:end_idx+1])
    result_normalized = normalize_text(combined_result)
    
    verse_words_set = verse['words_set']
    result_words_set = set(result_normalized.split())
    common = verse_words_set & result_words_set
    coverage = len(common) / len(verse_words_set) if verse_words_set else 0
    
    print(f"      Vérification: {coverage*100:.1f}% du verset présent")
    
    if coverage < 0.7:
        print(f"      ⚠️  ATTENTION: Faible correspondance!")
    
    return True

def enhance_srt_with_source(source_text_path, srt_path, output_srt_path):
    """
    Améliore le SRT en ajoutant les guillemets français pour les versets bibliques.
    
    Approche robuste basée sur correct_srt_quotes.py :
    1. Extraire TOUS les versets du texte original
    2. Pour chaque verset, le trouver dans le SRT (2 passes)
    3. Corriger les guillemets « et »
    4. Sauvegarder automatiquement les corrections
    
    Retourne: (nombre_corrections, liste_versets_avec_timestamps)
    """
    print("\n" + "="*80)
    print("CORRECTION DES GUILLEMETS BIBLIQUES DANS LE SRT")
    print("="*80 + "\n")
    
    # ÉTAPE 1: Lire et extraire les versets
    print("ÉTAPE 1: Extraction des versets du texte original")
    print("-" * 80)
    
    with open(source_text_path, 'r', encoding='utf-8') as f:
        source_text = f.read()
    
    verses = detect_bible_verses_in_source(source_text)
    
    if not verses:
        print("ℹ️  Aucun verset biblique à traiter")
        # Copier le SRT tel quel si pas de versets
        import shutil
        shutil.copy2(srt_path, output_srt_path)
        return (0, [])
    
    # ÉTAPE 2: Parser le SRT
    print("\nÉTAPE 2: Lecture du fichier SRT")
    print("-" * 80)
    
    srt_subtitles = parse_srt_file(srt_path)
    print(f"✓ {len(srt_subtitles)} sous-titres parsés\n")
    
    # ÉTAPE 3: Traiter chaque verset
    print("ÉTAPE 3: Recherche et correction des versets")
    print("-" * 80)
    
    corrections_made = 0
    verses_with_timestamps = []
    
    for i, verse in enumerate(verses, 1):
        preview = verse['content'][:50] + "..." if len(verse['content']) > 50 else verse['content']
        print(f"\nVerset {i}/{len(verses)}: {preview}")
        
        # Trouver le verset dans le SRT
        location = find_verse_in_srt(verse, srt_subtitles)
        
        if location is None:
            print("  ✗ VERSET NON TROUVÉ dans le SRT")
            continue
        
        start_idx, end_idx, coverage = location
        print(f"  ✓ Trouvé aux sous-titres {srt_subtitles[start_idx]['index']}-{srt_subtitles[end_idx]['index']}")
        print(f"  ✓ Couverture: {coverage*100:.1f}%")
        
        # Sauvegarder les infos du verset avec timestamps
        verses_with_timestamps.append({
            'text': verse['content'],
            'start_time': srt_subtitles[start_idx]['start_time'],
            'end_time': srt_subtitles[end_idx]['end_time'],
            'start_idx': start_idx,
            'end_idx': end_idx,
            'position_in_source': verse.get('start_pos', 0)
        })
        
        # Corriger les guillemets
        if correct_verse_quotes(srt_subtitles, start_idx, end_idx, verse):
            corrections_made += 1
    
    # ÉTAPE 4: Sauvegarder AUTOMATIQUEMENT
    print()
    print("ÉTAPE 4: Sauvegarde du fichier corrigé")
    print("-" * 80)
    
    with open(output_srt_path, 'w', encoding='utf-8') as f:
        for subtitle in srt_subtitles:
            f.write(f"{subtitle['index']}\n")
            f.write(f"{ms_to_timecode(subtitle['start_time'])} --> {ms_to_timecode(subtitle['end_time'])}\n")
            f.write(f"{subtitle['text']}\n\n")
    
    print(f"✓ Fichier corrigé sauvegardé: {output_srt_path}")
    
    print()
    print("="*80)
    print(f"✅ TERMINÉ: {corrections_made}/{len(verses)} versets corrigés")
    print("="*80 + "\n")
    
    return (corrections_made, verses_with_timestamps)

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
# PIPELINE PRINCIPAL
##############################

def detect_input_files():
    """
    Détecte automatiquement les fichiers d'entrée dans WORKING_DIR.
    Cherche : 1 fichier .txt, 1 fichier .srt, 1 fichier .mp3
    
    Returns:
        tuple: (txt_path, srt_path, audio_path) ou None si erreur
    """
    print("🔍 Détection automatique des fichiers d'entrée...")
    
    if not os.path.exists(WORKING_DIR):
        print(f"❌ Dossier de travail introuvable : {WORKING_DIR}")
        return None
    
    # Lister tous les fichiers
    all_files = os.listdir(WORKING_DIR)
    
    # Filtrer par extension
    txt_files = [f for f in all_files if f.lower().endswith('.txt')]
    srt_files = [f for f in all_files if f.lower().endswith('.srt')]
    mp3_files = [f for f in all_files if f.lower().endswith('.mp3')]
    
    # Vérifier qu'on a exactement 1 de chaque
    errors = []
    
    if len(txt_files) == 0:
        errors.append("❌ Aucun fichier .txt trouvé")
    elif len(txt_files) > 1:
        errors.append(f"⚠️  Plusieurs fichiers .txt trouvés : {', '.join(txt_files)}")
        print(f"   → Utilisation du premier : {txt_files[0]}")
    
    if len(srt_files) == 0:
        errors.append("❌ Aucun fichier .srt trouvé")
    elif len(srt_files) > 1:
        errors.append(f"⚠️  Plusieurs fichiers .srt trouvés : {', '.join(srt_files)}")
        print(f"   → Utilisation du premier : {srt_files[0]}")
    
    if len(mp3_files) == 0:
        errors.append("❌ Aucun fichier .mp3 trouvé")
    elif len(mp3_files) > 1:
        errors.append(f"⚠️  Plusieurs fichiers .mp3 trouvés : {', '.join(mp3_files)}")
        print(f"   → Utilisation du premier : {mp3_files[0]}")
    
    # Afficher les erreurs critiques
    critical_errors = [e for e in errors if e.startswith("❌")]
    if critical_errors:
        for error in errors:
            print(error)
        print(f"\n💡 Assurez-vous d'avoir exactement 1 fichier de chaque type dans {WORKING_DIR}")
        return None
    
    # Construire les chemins complets
    txt_path = os.path.join(WORKING_DIR, txt_files[0])
    srt_path = os.path.join(WORKING_DIR, srt_files[0])
    audio_path = os.path.join(WORKING_DIR, mp3_files[0])
    
    print(f"✅ Fichier texte    : {txt_files[0]}")
    print(f"✅ Fichier SRT      : {srt_files[0]}")
    print(f"✅ Fichier audio    : {mp3_files[0]}\n")
    
    return txt_path, srt_path, audio_path



def main():
    """
    Pipeline complet INTELLIGENT - VERSION FINALE AVEC FALLBACK
    """
    print("🚀 Démarrage du pipeline - Video_Generator_Dark_Intelligent")
    print("🧠 Mode INTELLIGENT : Pauses de prière + Overlays bibliques")
    print(f"📁 Dossier de travail: {WORKING_DIR}")
    print(f"📁 Dossier de sortie: {OUTPUT_DIR}\n")
    
    # ÉTAPE 1: Détection fichiers
    result = detect_input_files()
    if result is None:
        return
    
    source_text_path, srt_path, voice_audio = result
    
    # ÉTAPE 2: Détection transitions + pauses
    print("🧠 ÉTAPE 2/7 : Détection des transitions de prière...")
    transition_points = detect_prayer_transitions(srt_path)
    
    if transition_points:
        print(f"✅ {len(transition_points)} transition(s) détectée(s)")
        
        voice_audio_with_pauses = os.path.join(OUTPUT_DIR, "voice_audio_with_pauses.mp3")
        insert_silence_in_audio(voice_audio, voice_audio_with_pauses, transition_points, pause_duration=3.0)
        
        srt_file_adjusted = os.path.join(OUTPUT_DIR, "subtitles_adjusted.srt")
        adjust_srt_with_pauses(srt_path, srt_file_adjusted, transition_points, pause_duration_ms=3000)
        
        voice_audio = voice_audio_with_pauses
        srt_path = srt_file_adjusted
        print("🎯 Pauses de méditation insérées\n")
    else:
        print("ℹ️  Aucune transition détectée\n")
        voice_audio_copy = os.path.join(OUTPUT_DIR, "voice_audio.mp3")
        srt_file_copy = os.path.join(OUTPUT_DIR, "subtitles.srt")
        shutil.copy2(voice_audio, voice_audio_copy)
        shutil.copy2(srt_path, srt_file_copy)
        voice_audio = voice_audio_copy
        srt_path = srt_file_copy
    
    # ÉTAPE 3: Amélioration SRT (correction guillemets)
    print("📖 ÉTAPE 3/7 : Amélioration du SRT (correction guillemets)...")
    output_srt_path = os.path.join(OUTPUT_DIR, "subtitles_enhanced.srt")
    
    with open(source_text_path, 'r', encoding='utf-8') as f:
        source_text = f.read()
    
    corrections_count, verses_data = enhance_srt_with_source(source_text_path, srt_path, output_srt_path)
    references = detect_bible_references_in_source(source_text)
    
    # 🔍 DEBUG : Afficher ce qui a été détecté
    print(f"\n🔍 Détection des versets bibliques:")
    print(f"   Références détectées : {len(references) if references else 0}")
    print(f"   Versets détectés     : {len(verses_data) if verses_data else 0}")
    
    # ÉTAPE 4: Génération vidéo de fond
    print("\n🎬 ÉTAPE 4/7 : Génération de la vidéo de fond...")
    audio_duration = get_audio_duration(voice_audio)
    background_video = os.path.join(OUTPUT_DIR, "background_video.mp4")
    generate_background_video_from_local(audio_duration, background_video)
    print()
    
    # ÉTAPE 5: Sélection musique
    print("🎵 ÉTAPE 5/7 : Sélection de la musique de fond...")
    background_music = select_random_background_music()
    print()
    
    # ÉTAPE 6: Mixage audio
    print("🎚️  ÉTAPE 6/7 : Mixage audio...")
    mixed_audio = os.path.join(OUTPUT_DIR, "mixed_audio.m4a")
    mix_audio_with_background_delayed(voice_audio, background_music, mixed_audio, voice_delay_seconds=2)
    print()
    
    # ÉTAPE 7: Vidéo finale
    print("🎨 ÉTAPE 7/7 : Génération vidéo finale...")
    
    # Créer SRT décalé de 2 secondes
    shifted_srt = os.path.join(OUTPUT_DIR, "subtitles_shifted.srt")
    shift_srt_timing(output_srt_path, shifted_srt, delay_seconds=2)
    
    # ✅ DÉCISION : MODE OVERLAYS ou MODE STANDARD
    if references and verses_data:
        print("\n📖 MODE OVERLAYS BIBLIQUES activé")
        
        # Re-parser le SRT shifté pour avoir les bons timestamps
        print("📖 Extraction des versets du SRT final (avec shift +2s)...")
        _, verses_data_shifted = enhance_srt_with_source(
            source_text_path, 
            shifted_srt,
            shifted_srt
        )
        
        # Créer le JSON avec les timestamps corrects
        linked_verses_final = link_references_to_verses(references, verses_data_shifted)
        metadata_path_final = os.path.join(OUTPUT_DIR, "bible_verses_metadata.json")
        save_verses_metadata(linked_verses_final, metadata_path_final)
        
        # Générer la vidéo avec overlays
        final_video = os.path.join(OUTPUT_DIR, "final_video_with_overlays.mp4")
        generate_video_with_bible_overlays(
            background_video, 
            mixed_audio, 
            metadata_path_final,
            shifted_srt, 
            final_video
        )
        
        print("\n" + "="*80)
        print("🎉 PIPELINE COMPLET TERMINÉ - MODE OVERLAYS BIBLIQUES")
        print("="*80)
        print(f"🎬 Vidéo finale      : {final_video}")
        print(f"📖 Versets overlays  : {len(linked_verses_final)}")
        print(f"⏸️  Pauses prière     : {len(transition_points) if transition_points else 0}")
        print(f"📁 Dossier sortie    : {OUTPUT_DIR}")
        print("="*80 + "\n")
    
    else:
        # ✅ MODE STANDARD (utiliser la fonction de l'ancien script)
        print("\n⚠️  Aucun verset biblique détecté")
        print("🎬 Génération en MODE STANDARD (sans overlays)...\n")
        
        final_video = os.path.join(OUTPUT_DIR, "final_video_standard.mp4")
        
        # ✅ UTILISER LA FONCTION SIMPLE ET ROBUSTE DE L'ANCIEN SCRIPT
        success = generate_final_video_standard(
            background_video,
            mixed_audio,
            shifted_srt,
            final_video
        )
        
        if success:
            print("\n" + "="*80)
            print("🎉 PIPELINE COMPLET TERMINÉ - MODE STANDARD")
            print("="*80)
            print(f"🎬 Vidéo finale      : {final_video}")
            print(f"📖 Mode             : Standard (sans overlays bibliques)")
            print(f"⏸️  Pauses prière     : {len(transition_points) if transition_points else 0}")
            print(f"📁 Dossier sortie    : {OUTPUT_DIR}")
            print("="*80 + "\n")
        else:
            print("\n❌ Échec de la génération de la vidéo finale")


if __name__ == "__main__":
    main()
