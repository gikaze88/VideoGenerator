"""
Détection des versets bibliques et extraction des références.
Logique extraite intégralement de video_gen_full.py / video_gen_simple.py
"""
import re
import json
from datetime import datetime
from pathlib import Path

from backend.services.pipelines.shared.srt import parse_srt_file, ms_to_timecode
from backend.services.pipelines.shared.utils import log


# Dictionnaire des livres bibliques (français → format canonique)
BIBLE_BOOKS = {
    "genese": "GENÈSE", "génèse": "GENÈSE",
    "exode": "EXODE",
    "levitique": "LÉVITIQUE", "lévitique": "LÉVITIQUE",
    "nombres": "NOMBRES", "nombre": "NOMBRES",
    "deuteronome": "DEUTÉRONOME", "deutéronome": "DEUTÉRONOME",
    "josue": "JOSUÉ", "josué": "JOSUÉ",
    "juges": "JUGES", "juge": "JUGES",
    "ruth": "RUTH",
    "samuel": "SAMUEL",
    "1 samuel": "1 SAMUEL", "un samuel": "1 SAMUEL",
    "premier samuel": "1 SAMUEL", "première samuel": "1 SAMUEL",
    "2 samuel": "2 SAMUEL", "deux samuel": "2 SAMUEL",
    "deuxieme samuel": "2 SAMUEL", "deuxième samuel": "2 SAMUEL",
    "second samuel": "2 SAMUEL", "seconde samuel": "2 SAMUEL",
    "rois": "ROIS",
    "1 rois": "1 ROIS", "premier rois": "1 ROIS",
    "2 rois": "2 ROIS", "deuxieme rois": "2 ROIS", "deuxième rois": "2 ROIS",
    "chroniques": "CHRONIQUES", "chronique": "CHRONIQUES",
    "1 chroniques": "1 CHRONIQUES", "premiere chroniques": "1 CHRONIQUES",
    "première chroniques": "1 CHRONIQUES",
    "2 chroniques": "2 CHRONIQUES", "deuxieme chroniques": "2 CHRONIQUES",
    "esdras": "ESDRAS",
    "nehemie": "NÉHÉMIE", "néhémie": "NÉHÉMIE",
    "esther": "ESTHER",
    "job": "JOB",
    "psaume": "PSAUMES", "psaumes": "PSAUMES",
    "proverbe": "PROVERBES", "proverbes": "PROVERBES",
    "ecclesiaste": "ECCLÉSIASTE", "ecclésiaste": "ECCLÉSIASTE",
    "cantique": "CANTIQUE DES CANTIQUES", "cantiques": "CANTIQUE DES CANTIQUES",
    "cantique des cantiques": "CANTIQUE DES CANTIQUES",
    "esaie": "ÉSAÏE", "ésaïe": "ÉSAÏE", "esaïe": "ÉSAÏE", "isaie": "ÉSAÏE", "isaïe": "ÉSAÏE",
    "jeremie": "JÉRÉMIE", "jérémie": "JÉRÉMIE",
    "lamentations": "LAMENTATIONS", "lamentation": "LAMENTATIONS",
    "ezechiel": "ÉZÉCHIEL", "ézéchiel": "ÉZÉCHIEL", "ezéchiel": "ÉZÉCHIEL",
    "daniel": "DANIEL",
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
    "matthieu": "MATTHIEU",
    "marc": "MARC",
    "luc": "LUC",
    "jean": "JEAN",
    "actes": "ACTES", "acte": "ACTES",
    "actes des apotres": "ACTES", "actes des apôtres": "ACTES",
    "romains": "ROMAINS", "romain": "ROMAINS",
    "corinthiens": "CORINTHIENS", "corinthien": "CORINTHIENS",
    "1 corinthiens": "1 CORINTHIENS", "premier corinthiens": "1 CORINTHIENS",
    "première corinthiens": "1 CORINTHIENS",
    "2 corinthiens": "2 CORINTHIENS", "deuxieme corinthiens": "2 CORINTHIENS",
    "deuxième corinthiens": "2 CORINTHIENS",
    "galates": "GALATES", "galate": "GALATES",
    "ephesiens": "ÉPHÉSIENS", "éphésiens": "ÉPHÉSIENS",
    "philippiens": "PHILIPPIENS", "philippien": "PHILIPPIENS",
    "colossiens": "COLOSSIENS", "colossien": "COLOSSIENS",
    "thessaloniciens": "THESSALONICIENS",
    "1 thessaloniciens": "1 THESSALONICIENS",
    "2 thessaloniciens": "2 THESSALONICIENS",
    "timothee": "TIMOTHÉE", "timothée": "TIMOTHÉE",
    "1 timothee": "1 TIMOTHÉE", "1 timothée": "1 TIMOTHÉE",
    "2 timothee": "2 TIMOTHÉE", "2 timothée": "2 TIMOTHÉE",
    "tite": "TITE",
    "philemon": "PHILÉMON", "philémon": "PHILÉMON",
    "hebreux": "HÉBREUX", "hébreux": "HÉBREUX",
    "hebreu": "HÉBREUX", "hébreu": "HÉBREUX",
    "jacques": "JACQUES",
    "pierre": "PIERRE",
    "1 pierre": "1 PIERRE", "premier pierre": "1 PIERRE",
    "première pierre": "1 PIERRE",
    "2 pierre": "2 PIERRE", "deuxieme pierre": "2 PIERRE",
    "1 jean": "1 JEAN", "premier jean": "1 JEAN",
    "2 jean": "2 JEAN", "deuxieme jean": "2 JEAN",
    "3 jean": "3 JEAN", "troisieme jean": "3 JEAN", "troisième jean": "3 JEAN",
    "jude": "JUDE",
    "apocalypse": "APOCALYPSE",
    "revelation": "APOCALYPSE",
}

FRENCH_NUMBERS = {
    "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19,
    "vingt": 20, "vingt-et-un": 21, "vingt-et-une": 21,
    "vingt-deux": 22, "vingt-trois": 23, "vingt-quatre": 24, "vingt-cinq": 25,
    "vingt-six": 26, "vingt-sept": 27, "vingt-huit": 28, "vingt-neuf": 29,
    "trente": 30, "trente-et-un": 31, "trente-et-une": 31,
    "trente-deux": 32, "trente-trois": 33, "trente-quatre": 34, "trente-cinq": 35,
    "trente-six": 36, "trente-sept": 37, "trente-huit": 38, "trente-neuf": 39,
    "quarante": 40, "quarante-et-un": 41, "quarante-et-une": 41,
    "quarante-deux": 42, "quarante-trois": 43, "quarante-quatre": 44, "quarante-cinq": 45,
    "quarante-six": 46, "quarante-sept": 47, "quarante-huit": 48, "quarante-neuf": 49,
    "cinquante": 50, "cinquante-et-un": 51, "cinquante-deux": 52, "cinquante-trois": 53,
    "cinquante-quatre": 54, "cinquante-cinq": 55, "cinquante-six": 56,
    "cinquante-sept": 57, "cinquante-huit": 58, "cinquante-neuf": 59,
    "soixante": 60, "soixante-et-un": 61, "soixante-deux": 62, "soixante-trois": 63,
    "soixante-quatre": 64, "soixante-cinq": 65, "soixante-six": 66,
    "soixante-sept": 67, "soixante-huit": 68, "soixante-neuf": 69,
    "soixante-dix": 70, "soixante-et-onze": 71, "soixante-douze": 72,
    "soixante-treize": 73, "soixante-quatorze": 74, "soixante-quinze": 75,
    "soixante-seize": 76, "soixante-dix-sept": 77, "soixante-dix-huit": 78, "soixante-dix-neuf": 79,
    "septante": 70, "septante-et-un": 71, "septante-deux": 72, "septante-trois": 73,
    "septante-quatre": 74, "septante-cinq": 75, "septante-six": 76, "septante-sept": 77,
    "septante-huit": 78, "septante-neuf": 79,
    "quatre-vingt": 80, "quatre-vingts": 80, "huitante": 80, "octante": 80,
    "quatre-vingt-un": 81, "quatre-vingt-une": 81, "quatre-vingt-deux": 82,
    "quatre-vingt-trois": 83, "quatre-vingt-quatre": 84, "quatre-vingt-cinq": 85,
    "quatre-vingt-six": 86, "quatre-vingt-sept": 87, "quatre-vingt-huit": 88, "quatre-vingt-neuf": 89,
    "quatre-vingt-dix": 90, "quatre-vingt-onze": 91, "quatre-vingt-douze": 92,
    "quatre-vingt-treize": 93, "quatre-vingt-quatorze": 94, "quatre-vingt-quinze": 95,
    "quatre-vingt-seize": 96, "quatre-vingt-dix-sept": 97, "quatre-vingt-dix-huit": 98,
    "quatre-vingt-dix-neuf": 99, "nonante": 90, "nonante-et-un": 91,
    "cent": 100, "cents": 100,
    "cent-un": 101, "cent-deux": 102, "cent-trois": 103, "cent-quatre": 104,
    "cent-cinq": 105, "cent-six": 106, "cent-sept": 107, "cent-huit": 108, "cent-neuf": 109,
    "cent-dix": 110, "cent-onze": 111, "cent-douze": 112, "cent-treize": 113,
    "cent-quatorze": 114, "cent-quinze": 115, "cent-seize": 116,
    "cent-dix-sept": 117, "cent-dix-huit": 118, "cent-dix-neuf": 119,
    "cent-vingt": 120, "cent-vingt-et-un": 121, "cent-vingt-deux": 122,
    "cent-trente": 130, "cent-trente-et-un": 131,
    "cent-quarante": 140, "cent-quarante-et-un": 141, "cent-quarante-sept": 147,
    "cent-cinquante": 150,
    "deux-cents": 200, "deux-cent": 200,
}


def convert_french_number_to_digit(text: str) -> str:
    """Convertit un nombre écrit en français en chiffre arabe."""
    if str(text).isdigit():
        return str(text)
    t = text.lower().strip()
    if t in FRENCH_NUMBERS:
        return str(FRENCH_NUMBERS[t])
    normalized = t.replace(" et ", "-").replace(" ", "-")
    if normalized in FRENCH_NUMBERS:
        return str(FRENCH_NUMBERS[normalized])
    return "1"


def normalize_text_for_search(text: str) -> str:
    text = text.lower()
    # Remove punctuation including apostrophe (using double-quoted string to avoid Python string concat issue)
    text = re.sub(r"[«»\"''`',.;:!?\-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_verse_in_srt(
    verse_normalized: str,
    subtitles: list[dict],
    start_after_index: int = 0,
    max_window: int = 35,
) -> dict | None:
    """
    Cherche un verset dans le SRT avec une fenêtre glissante.
    - start_after_index : ne cherche qu'à partir de cet index SRT (recherche séquentielle).
    - Retourne le meilleur match (≥75% de couverture) ou None, avec l'index de fin de fenêtre.
    """
    verse_words = set(verse_normalized.split())
    if not verse_words:
        return None

    best_match = None
    best_coverage = 0.0

    search_subs = subtitles[start_after_index:]

    for window_size in range(3, max_window + 1):
        for i in range(len(search_subs) - window_size + 1):
            window = search_subs[i: i + window_size]
            combined = " ".join(s["text"] for s in window)
            combined_norm = normalize_text_for_search(combined)
            combined_words = set(combined_norm.split())
            common = combined_words & verse_words
            coverage = len(common) / len(verse_words)

            if coverage >= 0.75 and coverage > best_coverage:
                best_coverage = coverage
                abs_start = start_after_index + i
                abs_end = abs_start + window_size - 1
                best_match = {
                    "start_time": subtitles[abs_start]["start_time"],
                    "end_time": subtitles[abs_end]["end_time"],
                    "coverage": coverage,
                    "end_index": abs_end,
                }

    return best_match


def _parse_reference_match(match: re.Match, ptype: str) -> str | None:
    """Convertit un match regex en référence biblique formatée."""
    g = match.groups()
    if ptype == "std":
        book = BIBLE_BOOKS.get(g[0].lower(), g[0].upper())
        chapter = convert_french_number_to_digit(g[1])
        verse_n = convert_french_number_to_digit(g[2])
        return f"{book} {chapter}:{verse_n}"
    elif ptype == "range":
        book = BIBLE_BOOKS.get(g[0].lower(), g[0].upper())
        chapter = convert_french_number_to_digit(g[1])
        v_start = convert_french_number_to_digit(g[2])
        v_end = convert_french_number_to_digit(g[3])
        return f"{book} {chapter}:{v_start}-{v_end}"
    elif ptype == "digits":
        book = BIBLE_BOOKS.get(g[0].lower(), g[0].upper())
        chapter = g[1]
        verse_n = g[2] if g[2] else "1"
        return f"{book} {chapter}:{verse_n}"
    elif ptype == "modern":
        book = BIBLE_BOOKS.get(g[0].lower(), g[0].upper())
        chapter = g[1]
        v_start = g[2]
        v_end = g[3] if len(g) > 3 and g[3] else None
        return f"{book} {chapter}:{v_start}-{v_end}" if v_end else f"{book} {chapter}:{v_start}"
    elif ptype == "ordinal":
        ordinal_map = {"premier": "1", "première": "1", "deuxième": "2",
                       "second": "2", "seconde": "2", "troisième": "3"}
        num = ordinal_map.get(g[0].lower(), "1")
        book_full = f"{num} {g[1].lower()}"
        book = BIBLE_BOOKS.get(book_full, g[1].upper())
        chapter = convert_french_number_to_digit(g[2])
        verse_n = convert_french_number_to_digit(g[3])
        return f"{book} {chapter}:{verse_n}"
    elif ptype == "standalone":
        # Format: "Jean 3:16" or "1 Corinthiens 15:1"
        book_raw = g[0].strip()
        book = BIBLE_BOOKS.get(book_raw.lower(), book_raw.upper())
        chapter = g[1]
        verse_n = g[2] if len(g) > 2 and g[2] else "1"
        return f"{book} {chapter}:{verse_n}"
    return None


REF_PATTERNS = [
    # "Dans l'Évangile selon Matthieu, chapitre dix, verset trente"
    (r"[Dd]ans\s+l[''\u2019][ÉéEe]vangile\s+(?:selon|de)\s+([A-Za-zéèêàù]+),?\s+chapitres?\s+([a-zéèê\-\d]+),?\s+versets?\s+([a-zéèê\-\d]+)", 'std'),
    # "Selon l'Évangile de Matthieu, chapitre X, verset Y"
    (r"[Ss]elon\s+l[''\u2019][ÉéEe]vangile\s+(?:de|selon)?\s*([A-Za-zéèêàù]+),?\s+chapitres?\s+([a-zéèê\-\d]+),?\s+versets?\s+([a-zéèê\-\d]+)", 'std'),
    # "Dans l'Épître de Paul aux Éphésiens, chapitre X, verset Y" → generic "Épître ... BookName"
    (r"[Dd]ans\s+l[''\u2019][ÉéEe]p[iî]tre\s+(?:\w+\s+){0,4}([A-Za-zéèêàù]+),?\s+chapitres?\s+([a-zéèê\-\d]+),?\s+versets?\s+([a-zéèê\-\d]+)", 'std'),
    # Standard: "Dans Matthieu chapitre dix verset trente"
    (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèêàù\-]+)\s+chapitres?\s+([a-zéèê\-\d]+),?\s+versets?\s+([a-zéèê\-\d]+)', 'std'),
    (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'std'),
    (r'[Ee]n\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'std'),
    (r'[Ee]t\s+en\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+versets?\s+([a-zéèê\-]+)', 'std'),
    (r'[Ss]elon\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)', 'std'),
    (r"[Dd]'après\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)", 'std'),
    (r'[Ee]t\s+dans\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)', 'std'),
    (r'[Dd]ans\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+([a-zéèê\-]+)\s+à\s+([a-zéèê\-]+)', 'range'),
    (r'[Dd]ans\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s*,\s*(?:versets?\s+)?([a-zéèê\-]+)', 'std'),
    (r'[Dd]ans\s+(?:le\s+)?([A-Za-zéèêàù]+)\s+(\d+)(?:,?\s*versets?\s*(\d+))?', 'digits'),
    (r'[Ee]n\s+([A-Za-zéèêàù]+)\s+(\d+):(\d+)(?:-(\d+))?', 'modern'),
    (r'[Ss]elon\s+([A-Za-zéèêàù]+)\s+(\d+):(\d+)(?:-(\d+))?', 'modern'),
    (r'[Dd]ans\s+(?:le\s+)?(premier|première|deuxième|second|seconde|troisième)\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+(?:versets?\s+)?([a-zéèê\-]+)', 'ordinal'),
    (r'[Ee]n\s+(premier|première|deuxième|second|seconde|troisième)\s+([A-Za-zéèêàù\-]+)\s+([a-zéèê\-]+)\s+(?:versets?\s+)?([a-zéèê\-]+)', 'ordinal'),
    # Standalone: "Jean 3:16", "1 Corinthiens 15:1-3"
    (r'\b([A-Za-zéèêàù][A-Za-zéèêàù\-]+)\s+(\d+):(\d+)(?:-\d+)?', 'standalone'),
    (r'\b(\d\s+[A-Za-zéèêàù][A-Za-zéèêàù\-]+)\s+(\d+):(\d+)(?:-\d+)?', 'standalone'),
]


def extract_reference_from_source(verse_text: str, source_text: str, log_file=None) -> str:
    """
    Extrait la référence biblique depuis le texte source.
    Cherche dans les 500 chars AVANT et 300 chars APRÈS le verset.
    """
    verse_start = verse_text[:50] if len(verse_text) > 50 else verse_text
    verse_pos = source_text.find(verse_start)
    log(f"      [REF] verse_start={repr(verse_start[:40])} pos={verse_pos}", log_file)
    if verse_pos == -1:
        verse_pos = source_text.find(verse_text[:30])
        log(f"      [REF] fallback 30-char pos={verse_pos}", log_file)
    if verse_pos == -1:
        log(f"      [REF] verset introuvable dans source_text", log_file)
        return "VERSET BIBLIQUE"

    verse_end_pos = verse_pos + len(verse_text)

    # Zone de recherche : 500 chars avant + 300 chars après le verset
    before_start = max(0, verse_pos - 500)
    after_end = min(len(source_text), verse_end_pos + 300)

    search_before = source_text[before_start:verse_pos]
    search_after = source_text[verse_end_pos:after_end]

    best_reference = None
    best_score = float("inf")  # lower = closer to verse

    for zone, zone_text, is_before in [
        ("before", search_before, True),
        ("after", search_after, False),
    ]:
        for pattern, ptype in REF_PATTERNS:
            for match in re.finditer(pattern, zone_text, re.IGNORECASE):
                if is_before:
                    # Distance = chars between end of match and start of verse
                    distance = len(zone_text) - match.end()
                else:
                    # Distance = chars between end of verse and start of match
                    distance = match.start()

                if distance < best_score:
                    ref = _parse_reference_match(match, ptype)
                    if ref:
                        best_score = distance
                        best_reference = ref

    log(f"      [REF] best_reference={best_reference}", log_file)
    return best_reference or "VERSET BIBLIQUE"


def extract_verses_with_timestamps(
    source_text: str,
    srt_path: Path,
    log_file: Path | None = None,
) -> list[dict]:
    """
    Méthode hybride :
    1. Détecte les versets dans le source (entre «» ou "")
    2. Les cherche dans le SRT avec fenêtre glissante
    Retourne une liste de métadonnées avec timestamps.
    """
    log("📖 Détection des versets bibliques... [bible.py v2]", log_file)

    verse_pattern = r'[«"]([^»"]{30,}?)[»"]'
    detected = [v.strip() for v in re.findall(verse_pattern, source_text) if len(v.strip()) >= 30]
    log(f"   {len(detected)} verset(s) détecté(s) dans le texte source", log_file)

    subtitles = parse_srt_file(srt_path)
    results = []
    last_end_index = 0  # Sequential search: each verse starts after the previous one

    for i, verse_text in enumerate(detected, 1):
        verse_norm = normalize_text_for_search(verse_text)
        match = find_verse_in_srt(verse_norm, subtitles, start_after_index=last_end_index)
        if match:
            last_end_index = match["end_index"]
            reference = extract_reference_from_source(verse_text, source_text, log_file)
            results.append({
                "reference": reference,
                "text": verse_text,
                "start_time_ms": match["start_time"],
                "end_time_ms": match["end_time"],
                "start_time": ms_to_timecode(match["start_time"]),
                "end_time": ms_to_timecode(match["end_time"]),
                "coverage": match["coverage"],
            })
            log(f"   ✅ Verset #{i} trouvé : {reference} ({match['coverage']:.0%})", log_file)
        else:
            log(f"   ⚠️  Verset #{i} non trouvé dans le SRT", log_file)

    return results


def save_verses_metadata(verses: list[dict], output_path: Path) -> Path:
    """Sauvegarde les métadonnées des versets dans un fichier JSON."""
    metadata = {
        "bible_verses": verses,
        "total_verses": len(verses),
        "generated_at": datetime.now().isoformat(),
    }
    output_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def shift_verses_timestamps(verses: list[dict], shift_ms: int) -> list[dict]:
    """Décale les timestamps de tous les versets de shift_ms millisecondes."""
    shifted = []
    for v in verses:
        vv = v.copy()
        vv["start_time_ms"] = v["start_time_ms"] + shift_ms
        vv["end_time_ms"] = v["end_time_ms"] + shift_ms
        vv["start_time"] = ms_to_timecode(vv["start_time_ms"])
        vv["end_time"] = ms_to_timecode(vv["end_time_ms"])
        shifted.append(vv)
    return shifted
