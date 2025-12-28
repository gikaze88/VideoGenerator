#!/usr/bin/env python3
import os
import time
import whisper
import re
from datetime import datetime
from difflib import SequenceMatcher
import sys
import torch
import warnings

# Supprimer les warnings normaux (RTX 4000 + PyTorch)
warnings.filterwarnings("ignore", category=UserWarning, module="whisper.timing")
warnings.filterwarnings("ignore", category=FutureWarning, module="whisper")
warnings.filterwarnings("ignore", message=".*weights_only.*")

def setup_rtx4000_model():
    """Configuration optimale pour Quadro RTX 4000 avec modèle MEDIUM."""
    print("🎮 Configuration GPU RTX 4000...")
    
    # Vérifier et préparer le GPU
    if not torch.cuda.is_available():
        print("   ❌ CUDA non disponible - utilisation CPU")
        return whisper.load_model("medium", device="cpu")
    
    try:
        # Nettoyer la mémoire GPU
        torch.cuda.empty_cache()
        
        # Informations GPU
        gpu_props = torch.cuda.get_device_properties(0)
        total_memory = gpu_props.total_memory / 1024**3
        
        print(f"   GPU détecté: {gpu_props.name}")
        print(f"   Mémoire totale: {total_memory:.1f} GB")
        
        # Test GPU basique
        test_tensor = torch.randn(100, 100).cuda()
        result = torch.matmul(test_tensor, test_tensor)
        torch.cuda.synchronize()
        
        print("   ✅ Test GPU réussi")
        
        # Le modèle medium nécessite moins de mémoire (~1.5GB vs ~3GB)
        if total_memory < 3:  # Moins de 3GB
            print("   ⚠️ Mémoire GPU limitée mais suffisante pour le modèle medium")
        
        # Charger le modèle medium sur GPU
        print("   📥 Chargement modèle 'medium' sur GPU...")
        model = whisper.load_model("medium", device="cuda")
        
        # Vérifier mémoire utilisée
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        print(f"   ✅ Modèle medium chargé - Mémoire utilisée: {allocated:.1f} GB")
        print(f"   🚀 Avantages medium: ~2-3x plus rapide, moins d'hallucinations")
        
        return model
        
    except Exception as e:
        print(f"   ❌ Erreur GPU: {e}")
        print("   🔄 Fallback vers CPU...")
        return whisper.load_model("medium", device="cpu")

def get_rtx4000_transcribe_params(model_device):
    """Paramètres ÉQUILIBRÉS pour modèle MEDIUM - Optimisés pour vitesse et précision."""
    print("🎯 Configuration ÉQUILIBRÉE pour modèle MEDIUM...")
    
    base_params = {
        "language": "fr",
        "verbose": False,
        "word_timestamps": True,
        "temperature": 0.0,  # Déterministe pour éviter la créativité
        
        # PARAMÈTRES ÉQUILIBRÉS - Le modèle medium est naturellement moins hallucinatoire
        "no_speech_threshold": 0.4,    # Légèrement plus sensible que large (0.5)
        "logprob_threshold": -1.8,     # Légèrement plus permissif que large (-1.5)
        "compression_ratio_threshold": 3.0,  # Légèrement plus permissif que large (2.8)
        
        # Réduire les inférences mais garder un peu de contexte
        "condition_on_previous_text": True,   # ✅ ACTIVÉ mais avec prompt strict
        "initial_prompt": "Transcription précise en français. Ne pas inventer de contenu."
        # Pas de suppress_tokens - laisser le modèle fonctionner naturellement
    }
    
    # Optimisations GPU avec paramètres modérés
    if model_device == "cuda":
        base_params.update({
            "fp16": True,
            "beam_size": 3,  # Compromis entre 1 et 5
            "patience": 1.5  # Compromis entre 1.0 et 2.0
        })
        print("   🚀 GPU + Medium: fp16=True, beam_size=3, patience=1.5")
    else:
        print("   💻 CPU + Medium activé")
    
    print("   📊 Seuils optimisés pour medium:")
    print(f"      - no_speech_threshold: {base_params['no_speech_threshold']} (plus sensible)")
    print(f"      - logprob_threshold: {base_params['logprob_threshold']} (plus permissif)")
    print(f"      - compression_ratio: {base_params['compression_ratio_threshold']} (plus permissif)")
    print(f"      - beam_size: {base_params.get('beam_size', 'N/A')} (compromis)")
    print("   ⚖️ Medium: Naturellement moins d'hallucinations + Plus rapide")
    print("   🔄 Tokens naturels: Aucune suppression pour comportement prévisible")
    
    return base_params

def analyze_transcription_coverage(result, input_audio):
    """Analyser la couverture de transcription pour détecter les trous."""
    
    # Obtenir durée audio totale
    ffprobe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_audio
    ]
    
    try:
        import subprocess
        duration_result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30)
        if duration_result.returncode == 0:
            audio_duration = float(duration_result.stdout.strip())
        else:
            print("⚠️ Impossible d'obtenir la durée audio")
            return
    except Exception as e:
        print(f"⚠️ Erreur analyse durée: {e}")
        return
    
    # Analyser couverture
    segments = result.get("segments", [])
    if not segments:
        print("❌ AUCUN segment transcrit!")
        return
    
    # Calculer temps total transcrit
    total_transcribed = sum(seg["end"] - seg["start"] for seg in segments)
    coverage_percent = (total_transcribed / audio_duration) * 100
    
    print(f"\n📊 ANALYSE COUVERTURE TRANSCRIPTION (MODÈLE MEDIUM):")
    print(f"   🕐 Durée audio totale: {audio_duration:.1f}s ({audio_duration/60:.1f} min)")
    print(f"   🎤 Temps transcrit: {total_transcribed:.1f}s ({total_transcribed/60:.1f} min)")
    print(f"   📈 Couverture: {coverage_percent:.1f}%")
    
    # Détecter les trous significatifs
    gaps = []
    for i in range(len(segments) - 1):
        gap_duration = segments[i+1]["start"] - segments[i]["end"]
        if gap_duration > 3.0:  # Trous de plus de 3 secondes
            gaps.append({
                "start": segments[i]["end"],
                "end": segments[i+1]["start"], 
                "duration": gap_duration
            })
    
    if gaps:
        print(f"   ⚠️ {len(gaps)} TROUS SIGNIFICATIFS détectés:")
        for i, gap in enumerate(gaps[:5]):  # Afficher 5 premiers trous
            start_min = gap["start"] / 60
            end_min = gap["end"] / 60
            print(f"      {i+1}. {start_min:.1f}min → {end_min:.1f}min (trou: {gap['duration']:.1f}s)")
        
        if len(gaps) > 5:
            print(f"      ... et {len(gaps) - 5} autres trous")
    else:
        print("   ✅ Aucun trou significatif détecté")
    
    # Recommandations spécifiques au modèle medium
    if coverage_percent < 70:
        print("\n🚨 COUVERTURE FAIBLE! Recommandations pour modèle medium:")
        print("   1. Vérifiez la qualité de votre audio")
        print("   2. Augmentez le volume si nécessaire") 
        print("   3. Réduisez le bruit de fond")
        print("   4. Le modèle medium peut manquer la parole très faible")
    elif coverage_percent < 85:
        print("\n⚠️ Couverture modérée - normal pour le modèle medium")
    else:
        print("\n✅ Excellente couverture pour le modèle medium!")
    
    return coverage_percent

def normalize_text(text):
    """Normalise le texte pour la comparaison."""
    # Enlever la ponctuation et les espaces multiples
    text = re.sub(r'[^\w\s]', '', text.lower())
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def advanced_deduplication(segments):
    """Déduplication contre les répétitions de Whisper."""
    if not segments:
        return []
    
    print("Déduplication des répétitions en cours...")
    clean_segments = []
    
    i = 0
    while i < len(segments):
        current = segments[i]
        current_text = current["text"].strip()
        
        # Ignorer les segments très courts ou vides
        if len(current_text) < 3:
            i += 1
            continue
        
        # Chercher des répétitions consécutives (minimum 3 répétitions)
        consecutive_count = 1
        j = i + 1
        
        while j < len(segments):
            next_text = segments[j]["text"].strip()
            similarity = SequenceMatcher(None, 
                                       normalize_text(current_text), 
                                       normalize_text(next_text)).ratio()
            
            if similarity > 0.8:  # Très similaire
                consecutive_count += 1
                j += 1
            else:
                break
        
        # Si on a trouvé 3+ répétitions consécutives, c'est probablement une répétition
        if consecutive_count >= 3:
            print(f"  🔄 Répétition détectée ({consecutive_count} fois): '{current_text[:40]}...'")
            # Garder seulement la première occurrence avec durée étendue
            extended_segment = {
                "start": current["start"],
                "end": segments[j-1]["end"] if j-1 < len(segments) else current["end"],
                "text": current_text,
                "words": current.get("words", [])
            }
            clean_segments.append(extended_segment)
            i = j  # Passer après toutes les répétitions
        else:
            # Segment normal, le garder
            clean_segments.append(current)
            i += 1
    
    return clean_segments

def merge_compound_words(word_data):
    """Merge compound words with apostrophes and hyphens into single linguistic units."""
    if not word_data:
        return []
    
    merged_words = []
    i = 0
    
    while i < len(word_data):
        current_word = word_data[i]
        word_text = current_word["word"].strip()
        
        # Check if we should merge with the next word
        should_merge = False
        
        if i < len(word_data) - 1:
            next_word = word_data[i + 1]
            next_text = next_word["word"].strip()
            
            # Pattern 1: Current word ends with apostrophe or hyphen
            # Example: ["j'", "aime"] or ["Saint-", "Esprit"]
            if word_text.endswith("'") or word_text.endswith("-"):
                should_merge = True
            
            # Pattern 2: Next word starts with apostrophe or hyphen  
            # Example: ["l", "'Esprit"] or ["Saint", "-Esprit"] or ["s", "'apprend"]
            elif next_text.startswith("'") or next_text.startswith("-"):
                should_merge = True
        
        if should_merge:
            next_word = word_data[i + 1]
            next_text = next_word["word"].strip()
            
            # Merge the compound word
            merged_text = word_text + next_text
            merged_word = {
                "word": " " + merged_text if current_word["word"].startswith(" ") else merged_text,
                "start": current_word["start"],
                "end": next_word["end"]
            }
            merged_words.append(merged_word)
            i += 2  # Skip both words since we merged them
        else:
            merged_words.append(current_word)
            i += 1
    
    return merged_words

def count_linguistic_words(word_data):
    """Count actual linguistic words after merging compound words."""
    merged_words = merge_compound_words(word_data)
    return len(merged_words)

def process_words_sequentially(word_data, max_words, max_chars, min_gap):
    """Traite les mots séquentiellement avec timings précis - AUCUN mot perdu."""
    if not word_data:
        return []
    
    # First, merge compound words to get proper linguistic units
    merged_word_data = merge_compound_words(word_data)
    
    segments = []
    current_words = []
    
    for i, word_info in enumerate(merged_word_data):
        current_words.append(word_info)
        
        # Construire le texte actuel avec les espaces de Whisper
        current_text = "".join([w["word"] for w in current_words]).strip()
        
        # Vérifier si on doit créer un segment (now using linguistic word count)
        should_create_segment = (
            len(current_words) >= max_words or  # Limite de mots linguistiques atteinte
            len(current_text) >= max_chars or   # Limite de caractères atteinte
            i == len(merged_word_data) - 1 or   # Dernier mot
            word_info["word"].rstrip().endswith(('.', '!', '?', ';', ':'))  # Fin de phrase naturelle
        )
        
        if should_create_segment and current_text:
            # Créer le segment avec timings précis
            segment_start = current_words[0]["start"]
            segment_end = current_words[-1]["end"]
            
            segments.append({
                "start": segment_start,
                "end": segment_end,
                "text": current_text
            })
            
            print(f"    Segment créé: '{current_text}' ({len(current_words)} mots linguistiques, {len(current_text)} chars)")
            
            # Réinitialiser pour le prochain segment
            current_words = []
    
    return segments

def process_text_sequentially(text, start_time, end_time, max_words, max_chars, min_gap):
    """Traite le texte séquentiellement sans horodatages précis - AUCUN mot perdu."""
    words = text.split()
    if not words:
        return []
    
    segments = []
    duration = end_time - start_time
    total_words = len(words)
    
    word_index = 0
    
    while word_index < total_words:
        current_words = []
        
        # Prendre des mots jusqu'aux limites
        while (word_index < total_words and 
               len(current_words) < max_words and 
               len(" ".join(current_words + [words[word_index]])) <= max_chars):
            current_words.append(words[word_index])
            word_index += 1
        
        # Si aucun mot n'a pu être ajouté (mot très long), le prendre quand même
        if not current_words and word_index < total_words:
            current_words.append(words[word_index])
            word_index += 1
        
        if current_words:
            # Calculer les timings proportionnels
            words_start_ratio = (word_index - len(current_words)) / total_words
            words_end_ratio = word_index / total_words
            
            segment_start = start_time + (duration * words_start_ratio)
            segment_end = start_time + (duration * words_end_ratio)
            
            current_text = " ".join(current_words)
            
            segments.append({
                "start": segment_start,
                "end": segment_end,
                "text": current_text
            })
            
            print(f"    Segment créé: '{current_text}' ({len(current_words)} mots, {len(current_text)} chars)")
    
    return segments

def smart_segmentation(segments):
    """Segmentation séquentielle - Version 27 améliorée avec zéro perte de mots."""
    print("Segmentation séquentielle intelligente en cours...")
    optimized = []
    
    # Paramètres éprouvés de la version 27
    MAX_WORDS_PER_SEGMENT = 5  # 5 mots maximum
    MAX_CHARS_PER_SEGMENT = 35  # 35 caractères maximum  
    MAX_DURATION = 2.8  # 2.8 secondes maximum
    MIN_GAP = 0.1
    
    for segment in segments:
        text = segment["text"].strip()
        start_time = segment["start"]
        end_time = segment["end"]
        duration = end_time - start_time
        
        # Count linguistic words (after merging compound words)
        if "words" in segment and segment["words"]:
            linguistic_word_count = count_linguistic_words(segment["words"])
        else:
            # Fallback: split on whitespace for basic word count
            linguistic_word_count = len(text.split())
        
        # Si le segment respecte déjà les critères, le garder tel quel (logique version 27)
        if (linguistic_word_count <= MAX_WORDS_PER_SEGMENT and 
            len(text) <= MAX_CHARS_PER_SEGMENT and 
            duration <= MAX_DURATION):
            optimized.append({
                "start": start_time,
                "end": end_time,
                "text": text
            })
            continue
        
        # Segment dépasse les limites : traitement séquentiel avec timings précis
        print(f"  Traitement séquentiel: '{text[:30]}...' ({linguistic_word_count} mots linguistiques)")
        
        if "words" in segment and segment["words"] and len(segment["words"]) > 0:
            # Utiliser les horodatages précis des mots (version 27 style)
            word_data = segment["words"]
            processed_segments = process_words_sequentially(word_data, MAX_WORDS_PER_SEGMENT, MAX_CHARS_PER_SEGMENT, MIN_GAP)
            optimized.extend(processed_segments)
        else:
            # Fallback : traitement séquentiel sans horodatages précis
            fallback_segments = process_text_sequentially(text, start_time, end_time, MAX_WORDS_PER_SEGMENT, MAX_CHARS_PER_SEGMENT, MIN_GAP)
            optimized.extend(fallback_segments)
    
    return optimized

def fill_gaps(segments):
    """Comble les trous entre segments pour éviter les silences dans les sous-titres."""
    if len(segments) < 2:
        return segments
    
    print("Vérification et comblement des trous...")
    filled_segments = []
    
    for i, segment in enumerate(segments):
        filled_segments.append(segment)
        
        # Vérifier s'il y a un trou avec le segment suivant
        if i < len(segments) - 1:
            next_segment = segments[i + 1]
            gap = next_segment["start"] - segment["end"]
            
            # Si le trou est significatif (> 1 seconde) mais pas trop grand (< 5 secondes)
            if 1.0 < gap < 5.0:
                print(f"  Trou détecté de {gap:.1f}s entre segments {i+1} et {i+2}")
                # Étendre légèrement le segment actuel pour réduire le trou
                segment["end"] = min(segment["end"] + gap/2, next_segment["start"] - 0.1)
    
    return filled_segments

def resolve_overlaps(segments):
    """Résout les chevauchements temporels entre segments."""
    print("Résolution des chevauchements temporels...")
    if not segments:
        return []
    
    # Trier les segments par heure de début
    segments.sort(key=lambda x: x["start"])
    
    resolved = []
    for i, current in enumerate(segments):
        if i == 0:
            resolved.append(current)
            continue
        
        previous = resolved[-1]
        
        # Vérifier s'il y a chevauchement
        if current["start"] < previous["end"]:
            # Ajuster les horaires pour éviter le chevauchement
            gap = 0.1  # 100ms de gap minimum
            previous["end"] = current["start"] - gap
            
            # S'assurer que le segment précédent n'est pas trop court
            if previous["end"] - previous["start"] < 0.5:
                previous["end"] = previous["start"] + 0.5
                current["start"] = previous["end"] + gap
            
            print(f"  Chevauchement résolu entre segments {i} et {i+1}")
        
        resolved.append(current)
    
    return resolved

def write_srt(segments, file):
    """Écrire les segments au format SRT - TOUS les mots sont préservés."""
    segment_count = 0
    for segment in segments:
        text = segment["text"].strip()
        
        # Garder tous les segments avec du texte
        if text:
            segment_count += 1
            
            # Numéro de séquence
            file.write(f"{segment_count}\n")
            
            # Temps début --> fin
            start = format_timestamp(segment["start"])
            end = format_timestamp(segment["end"])
            file.write(f"{start} --> {end}\n")
            
            # Texte complet - aucune troncature
            file.write(f"{text}\n\n")

def format_timestamp(seconds):
    """Convertir secondes en format HH:MM:SS,mmm pour SRT."""
    hours = int(seconds / 3600)
    seconds %= 3600
    minutes = int(seconds / 60)
    seconds %= 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def generate_srt(input_audio_path, output_srt_path=None):
    """
    Fonction principale qui génère le fichier SRT professionnel.
    Compatible avec le pipeline existant.
    
    Args:
        input_audio_path: Chemin vers le fichier audio d'entrée
        output_srt_path: Chemin où sauvegarder le fichier SRT (optionnel)
    
    Returns:
        str: Chemin du fichier SRT généré
    """
    # Vérifier si le fichier existe
    if not os.path.exists(input_audio_path):
        raise FileNotFoundError(f"Erreur: Le fichier {input_audio_path} n'existe pas.")
    
    print("=" * 60)
    print("GÉNÉRATEUR SRT PROFESSIONNEL - MODÈLE MEDIUM")
    print("=" * 60)
    print(f"Début de la transcription avec le modèle Whisper MEDIUM optimisé...")
    start_time = time.time()
    
    # Charger le modèle avec optimisations RTX 4000
    model = setup_rtx4000_model()
    model_device = "cuda" if model.device.type == "cuda" else "cpu"
    
    # Paramètres optimisés selon le device
    transcribe_params = get_rtx4000_transcribe_params(model_device)
    
    # Transcription avec paramètres anti-répétition optimisés
    print("🎤 Début transcription avec modèle MEDIUM...")
    try:
        result = model.transcribe(input_audio_path, **transcribe_params)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"✅ Transcription MEDIUM terminée en {duration:.2f} secondes.")
        
        # Monitoring GPU si utilisé
        if model_device == "cuda":
            max_memory = torch.cuda.max_memory_allocated(0) / 1024**3
            print(f"🎮 Mémoire GPU max utilisée: {max_memory:.1f} GB")
            
    except Exception as e:
        print(f"❌ Erreur transcription: {e}")
        raise
    
    # Analyser la couverture de transcription
    print("\n📊 Analyse de la couverture...")
    coverage = analyze_transcription_coverage(result, input_audio_path)
    
    print("\n" + "=" * 60)
    print("ÉTAPE 1: DÉDUPLICATION INTELLIGENTE")
    print("=" * 60)
    
    # Déduplication intelligente (fusionner au lieu de supprimer)
    cleaned_segments = advanced_deduplication(result["segments"])
    print(f"Après déduplication intelligente: {len(cleaned_segments)} segments")
    
    print("\n" + "=" * 60)
    print("ÉTAPE 2: OPTIMISATION DES SEGMENTS")
    print("=" * 60)
    
    # Optimiser les segments pour une meilleure lisibilité
    optimized_segments = smart_segmentation(cleaned_segments)
    print(f"Segments optimisés: {len(optimized_segments)} segments")
    
    print("\n" + "=" * 60)
    print("ÉTAPE 3: COMBLEMENT DES TROUS")
    print("=" * 60)
    
    # Combler les trous potentiels
    filled_segments = fill_gaps(optimized_segments)
    print(f"Après comblement des trous: {len(filled_segments)} segments")
    
    # Vérification finale des chevauchements
    final_segments = resolve_overlaps(filled_segments)
    print(f"Après résolution des chevauchements: {len(final_segments)} segments")
    
    # Déterminer le nom du fichier de sortie
    if output_srt_path:
        srt_filename = output_srt_path
        # Créer le répertoire de sortie si nécessaire
        os.makedirs(os.path.dirname(srt_filename), exist_ok=True)
    else:
        # Créer le dossier output s'il n'existe pas
        os.makedirs("output", exist_ok=True)
        # Générer un timestamp pour le nom du fichier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        srt_filename = f"output/reference_audio_medium_{timestamp}.srt"
    
    # Générer le fichier SRT
    with open(srt_filename, "w", encoding="utf-8") as srt_file:
        write_srt(final_segments, srt_file)
    
    # Nettoyage final GPU
    if model_device == "cuda":
        torch.cuda.empty_cache()
        print("🧹 Mémoire GPU nettoyée")
    
    print("\n" + "=" * 60)
    print("GÉNÉRATION SRT TERMINÉE AVEC SUCCÈS!")
    print("=" * 60)
    print(f"⚡ Performance RTX 4000 + MEDIUM: Transcription en {duration:.2f}s")
    print(f"📁 Fichier SRT professionnel généré: {srt_filename}")
    print(f"📊 Nombre total de segments: {len(final_segments)}")
    
    # Statistiques finales
    if final_segments:
        total_duration = final_segments[-1]["end"]
        print(f"🕐 Durée totale traitée: {total_duration:.1f} secondes ({total_duration/60:.1f} min)")
    
    print("✨ Qualité: Timings précis + Aucun mot perdu + Segmentation intelligente + Anti-hallucination")
    
    return srt_filename

def main():
    """Fonction principale qui génère le fichier SRT professionnel (mode ligne de commande)."""
    # Générer un timestamp pour le nom du fichier
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Fichier audio d'entrée
    input_audio = "reference_audio.mp3"
    
    # Appeler la fonction générique
    generate_srt(input_audio)

if __name__ == "__main__":
    main()