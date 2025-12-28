# 🚀 Guide d'Installation Complète - Depuis Zéro

Ce guide vous permet de répliquer l'environnement **SagesseDuChrist** sur une machine vide.

---

## 📋 Prérequis Système

### 1. Système d'Exploitation

- ✅ **Windows 10/11** (64-bit)
- ✅ **Ubuntu/Debian 20.04+** (64-bit)
- ✅ **macOS 11+** (Intel ou Apple Silicon)

### 2. Espace Disque

- **Minimum**: 10 GB libres
- **Recommandé**: 20+ GB (pour vidéos, musiques, cache)

### 3. RAM

- **Minimum**: 8 GB
- **Recommandé**: 16+ GB (surtout si utilisation de Whisper)

---

## 🔧 Étape 1: Installer Python

### Windows

**Option A: Télécharger depuis Python.org (Recommandé)**

```powershell
# 1. Aller sur https://www.python.org/downloads/
# 2. Télécharger Python 3.11.x (version stable recommandée)
# 3. Lancer l'installateur
# 4. ✅ IMPORTANT: Cocher "Add Python to PATH"
# 5. Cliquer "Install Now"

# Vérifier l'installation
python --version
# Devrait afficher: Python 3.11.x
```

**Option B: Avec Chocolatey**

```powershell
# Si Chocolatey est installé
choco install python311 -y

# Vérifier
python --version
```

### Linux (Ubuntu/Debian)

```bash
# Mettre à jour les paquets
sudo apt update
sudo apt upgrade -y

# Installer Python 3.11
sudo apt install python3.11 python3.11-venv python3.11-dev -y

# Vérifier
python3.11 --version
```

### macOS

```bash
# Avec Homebrew
brew install python@3.11

# Vérifier
python3.11 --version
```

---

## 🎬 Étape 2: Installer FFmpeg

### Windows

**Option A: Avec Chocolatey (Recommandé)**

```powershell
choco install ffmpeg -y
```

**Option B: Avec Scoop**

```powershell
scoop install ffmpeg
```

**Option C: Manuel**

```
1. Aller sur https://www.gyan.dev/ffmpeg/builds/
2. Télécharger "ffmpeg-release-essentials.zip"
3. Extraire dans C:\ffmpeg
4. Ajouter C:\ffmpeg\bin au PATH système
5. Redémarrer le terminal
```

**Vérifier l'installation:**

```powershell
ffmpeg -version
# Devrait afficher la version de FFmpeg
```

### Linux (Ubuntu/Debian)

```bash
sudo apt install ffmpeg -y

# Vérifier
ffmpeg -version
```

### macOS

```bash
brew install ffmpeg

# Vérifier
ffmpeg -version
```

---

## 📁 Étape 3: Créer la Structure du Projet

### Windows (PowerShell)

```powershell
# Créer le dossier principal
mkdir C:\Projects\SagesseDuChrist-New
cd C:\Projects\SagesseDuChrist-New

# Cloner depuis GitHub (si déjà sur GitHub)
git clone https://github.com/VOTRE-USERNAME/SagesseDuChrist-Video-Generator.git
cd SagesseDuChrist-Video-Generator

# OU créer la structure manuellement
mkdir videos_db\videos_db_light
mkdir videos_db\videos_db_dark
mkdir background_songs
mkdir working_dir
mkdir working_dir_audio_srt
mkdir working_dir_simple
mkdir working_dir_shorts
mkdir working_dir_full_local
mkdir subs_generator
```

### Linux/macOS (Bash)

```bash
# Créer le dossier principal
mkdir -p ~/Projects/SagesseDuChrist-New
cd ~/Projects/SagesseDuChrist-New

# Cloner depuis GitHub (si déjà sur GitHub)
git clone https://github.com/VOTRE-USERNAME/SagesseDuChrist-Video-Generator.git
cd SagesseDuChrist-Video-Generator

# OU créer la structure manuellement
mkdir -p videos_db/videos_db_light
mkdir -p videos_db/videos_db_dark
mkdir -p background_songs
mkdir -p working_dir
mkdir -p working_dir_audio_srt
mkdir -p working_dir_simple
mkdir -p working_dir_shorts
mkdir -p working_dir_full_local
mkdir -p subs_generator
```

---

## 🐍 Étape 4: Créer l'Environnement Virtuel

### Windows

```powershell
# Créer l'environnement virtuel avec Python 3.11
python -m venv venv

# Activer l'environnement
.\venv\Scripts\activate

# Vous devriez voir (venv) au début de votre ligne de commande
```

### Linux/macOS

```bash
# Créer l'environnement virtuel
python3.11 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Vous devriez voir (venv) au début de votre ligne de commande
```

---

## 📦 Étape 5: Installer les Dépendances Python

### Installation Standard (CPU)

```bash
# Mettre à jour pip
pip install --upgrade pip

# Installer toutes les dépendances
pip install -r requirements.txt

# Cela prendra 5-15 minutes selon votre connexion
```

### Installation avec GPU (NVIDIA CUDA)

**Prérequis:**

- Carte graphique NVIDIA compatible CUDA
- Drivers NVIDIA à jour
- CUDA Toolkit 12.1+ installé

```bash
# Mettre à jour pip
pip install --upgrade pip

# Installer PyTorch avec CUDA 12.1 d'abord (versions testées)
pip install torch==2.7.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.7.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# Puis installer le reste
pip install -r requirements.txt

# Vérifier CUDA
python -c "import torch; print(f'CUDA disponible: {torch.cuda.is_available()}')"
python -c "import torch; print(f'Version CUDA: {torch.version.cuda}')"
```

### Vérification de l'Installation

```bash
# Vérifier que tout est installé
pip list

# Vérifier les packages critiques
python -c "import whisper; print('Whisper OK')"
python -c "import torch; print('PyTorch OK')"
python -c "import requests; print('Requests OK')"
python -c "from dotenv import load_dotenv; print('python-dotenv OK')"
```

---

## 🔑 Étape 6: Configurer les Variables d'Environnement

### Créer le fichier .env

```bash
# Copier le template
cp env.example .env

# Ou créer manuellement (Windows)
copy env.example .env
```

### Éditer le fichier .env

Ouvrez `.env` avec votre éditeur préféré et ajoutez vos clés API:

```env
# REQUIS pour pipeline complète
ELEVENLABS_API_KEY=sk_votre_clé_ici_xxxxxxxxxxxxxxxx
ELEVENLABS_VOICE_ID=votre_voice_id_ici

# Optionnel
OPENAI_API_KEY=sk-votre_clé_openai_optionnelle
PEXELS_API_KEY=votre_clé_pexels_optionnelle
PIXABAY_API_KEY=votre_clé_pixabay_optionnelle
```

**Où obtenir les clés API:**

1. **ElevenLabs** (REQUIS):

   - https://elevenlabs.io/
   - Créer un compte
   - Aller dans "Profile" → "API Keys"
   - Copier votre clé API
   - Pour Voice ID: Tester les voix et copier l'ID

2. **OpenAI** (Optionnel):

   - https://platform.openai.com/api-keys

3. **Pexels/Pixabay** (Optionnel):
   - https://www.pexels.com/api/
   - https://pixabay.com/api/docs/

---

## 🎨 Étape 7: Installer les Polices (Pour Overlays)

### Windows

```
1. Aller sur https://fonts.google.com/specimen/Montserrat
2. Cliquer "Download family"
3. Extraire le ZIP
4. Ouvrir le dossier "static"
5. Sélectionner ces fichiers:
   - Montserrat-Regular.ttf
   - Montserrat-Bold.ttf
   - Montserrat-ExtraLight.ttf
6. Clic droit → "Installer" (ou copier dans C:\Windows\Fonts\)
7. Redémarrer votre terminal
```

### Linux

```bash
# Créer le dossier des polices local
mkdir -p ~/.local/share/fonts

# Télécharger Montserrat
cd ~/.local/share/fonts
wget https://github.com/JulietaUla/Montserrat/archive/master.zip
unzip master.zip
mv Montserrat-master/fonts/ttf/*.ttf .
rm -rf Montserrat-master master.zip

# Mettre à jour le cache des polices
fc-cache -f -v

# Vérifier
fc-list | grep Montserrat
```

### macOS

```bash
# Télécharger et installer avec Homebrew
brew tap homebrew/cask-fonts
brew install font-montserrat

# Ou manuel:
# 1. Télécharger depuis Google Fonts
# 2. Double-cliquer sur chaque fichier .ttf
# 3. Cliquer "Installer la police"
```

---

## 📹 Étape 8: Ajouter les Ressources

### Vidéos de Fond

```
videos_db/
  ├── videos_db_light/     # Vidéos thème clair (nature, lumière)
  │   ├── video_001.mp4
  │   ├── video_002.mp4
  │   └── ... (10-50 vidéos recommandées)
  │
  └── videos_db_dark/      # Vidéos thème sombre (nuit, contemplation)
      ├── video_001.mp4
      ├── video_002.mp4
      └── ... (10-50 vidéos recommandées)
```

**Recommandations:**

- Format: MP4 (H.264)
- Résolution: 1920x1080 minimum
- Durée: 10-60 secondes chacune
- Thème: Nature, paysages, ciel, eau, feu, etc.

**Sources gratuites:**

- Pexels Videos: https://www.pexels.com/videos/
- Pixabay Videos: https://pixabay.com/videos/
- Coverr: https://coverr.co/

### Musiques de Fond

```
background_songs/
  ├── peaceful_piano_01.mp3
  ├── ambient_worship_02.mp3
  └── ... (5-20 musiques recommandées)
```

**Recommandations:**

- Format: MP3
- Bitrate: 192 kbps minimum
- Durée: 2-10 minutes
- Style: Ambiance, piano, instrumental, worship

**Sources gratuites:**

- YouTube Audio Library
- Free Music Archive
- Incompetech

---

## 🧪 Étape 9: Tester l'Installation

### Test Rapide

```bash
# Activer l'environnement (si pas déjà fait)
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Test 1: Vérifier Python
python --version

# Test 2: Vérifier FFmpeg
ffmpeg -version

# Test 3: Vérifier les imports Python
python -c "import whisper, torch, requests; print('✅ Tous les modules importés avec succès!')"

# Test 4: Vérifier CUDA (si GPU)
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# Test 5: Lister les polices (optionnel)
# Windows PowerShell:
Get-ChildItem C:\Windows\Fonts\*montserrat*.ttf
# Linux:
fc-list | grep -i montserrat
```

### Créer un Fichier de Test

Créez `working_dir/script_video.txt`:

```text
Titre: Test du Système

Transcript:
Seigneur, je te remercie pour cette journée.

Dans Psaume vingt-trois un, il est écrit : « L'Éternel est mon berger, je ne manquerai de rien. »

Maintenant, prions ensemble pour ta protection.

Amen.
```

### Lancer un Test Complet

```bash
# Test avec le script complet (nécessite clés API)
python Video_Generator_Full_Light_Intelligent_Final.py

# OU test sans génération audio (si pas de clé ElevenLabs)
# 1. Mettre un audio.mp3 et subtitles.srt dans working_dir_audio_srt/
# 2. Mettre le script.txt
python Video_Generator_Light_Intelligent_Final.py
```

---

## ✅ Vérification Finale - Checklist

Avant de lancer votre première vidéo, vérifiez:

- [ ] Python 3.10-3.12 installé et dans le PATH
- [ ] FFmpeg installé et dans le PATH
- [ ] Environnement virtuel créé et activé
- [ ] Toutes les dépendances pip installées (requirements.txt)
- [ ] Fichier .env créé avec ELEVENLABS_API_KEY et ELEVENLABS_VOICE_ID
- [ ] Polices Montserrat installées
- [ ] Au moins 1 vidéo dans videos_db/videos_db_light/
- [ ] Au moins 1 musique dans background_songs/
- [ ] Fichier de test dans working_dir/script_video.txt
- [ ] Tous les tests passent sans erreur

---

## 🚨 Dépannage

### Problème: "python: command not found"

**Solution:**

- Windows: Réinstaller Python en cochant "Add to PATH"
- Linux: Utiliser `python3.11` au lieu de `python`
- Redémarrer le terminal après installation

### Problème: "ffmpeg: command not found"

**Solution:**

- Vérifier l'installation: `ffmpeg -version`
- Windows: Ajouter FFmpeg au PATH système
- Linux: `sudo apt install ffmpeg`
- Redémarrer le terminal

### Problème: "No module named 'whisper'"

**Solution:**

```bash
pip install openai-whisper
```

### Problème: "CUDA not available" (mais vous avez un GPU NVIDIA)

**Solution:**

```bash
# Réinstaller PyTorch avec CUDA
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Problème: "Font not found" pendant génération overlays

**Solution:**

- Vérifier que Montserrat est installé
- Windows: Vérifier dans C:\Windows\Fonts\
- Linux: `fc-list | grep Montserrat`
- Réinstaller les polices si nécessaire

### Problème: ElevenLabs API Error (401)

**Solution:**

- Vérifier que ELEVENLABS_API_KEY est correct dans .env
- Vérifier que le fichier .env est dans le dossier racine
- Vérifier que la clé n'a pas expiré sur elevenlabs.io

### Problème: Out of Memory (Whisper)

**Solution:**

```bash
# Utiliser un modèle plus petit
# Dans subs_generator/srt_generator.py ligne 50, changer:
model = whisper.load_model("base", device="cpu")  # au lieu de "medium"
```

---

## 📞 Support

Si vous rencontrez des problèmes:

1. Consultez ce guide d'installation
2. Vérifiez la checklist ci-dessus
3. Lisez le README.md principal
4. Ouvrez une Issue sur GitHub avec:
   - Votre système d'exploitation
   - Version de Python
   - Message d'erreur complet
   - Étapes pour reproduire le problème

---

## 🎉 Félicitations !

Si tous les tests passent, votre environnement est prêt ! 🚀

**Prochaines étapes:**

1. Lire le README.md pour les détails d'utilisation
2. Consulter PROJECT_STRUCTURE.md pour comprendre l'architecture
3. Créer votre première vidéo avec Video_Generator_Full_Light_Intelligent_Final.py

**Bon courage avec vos créations vidéo !** 🎬✨
