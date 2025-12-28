# 📋 Versions Exactes Validées - SagesseDuChrist

Ce fichier liste les **versions exactes** testées et validées dans l'environnement de production.

---

## ✅ Configuration Actuelle (Validée)

### Environnement

- **Python:** 3.10 ou 3.11 (recommandé)
- **OS:** Windows 10/11 (64-bit)
- **GPU:** NVIDIA avec CUDA 12.1
- **FFmpeg:** Dernière version stable

### Versions PyTorch (CUDA 12.1)

```
torch==2.5.1+cu121
torchaudio==2.5.1+cu121
torchvision==0.20.1+cu121
```

**Source:** https://download.pytorch.org/whl/cu121

**Installation:**

```bash
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

---

## 📦 Dépendances Principales

### Intelligence Artificielle

```
openai==1.86.0                    # Client API ElevenLabs
openai-whisper==20240930          # Speech-to-text Whisper
```

### Traitement Audio/Vidéo

```
ffmpeg-python==0.2.0              # Wrapper FFmpeg Python
librosa==0.11.0                   # Analyse audio
soundfile==0.13.1                 # I/O fichiers audio
numpy==2.2.6                      # Computing numérique
scipy==1.15.3                     # Computing scientifique
```

### Utilitaires

```
python-dotenv==1.1.0              # Variables d'environnement
requests==2.32.4                  # HTTP requests
tqdm==4.67.1                      # Barres de progression
colorama==0.4.6                   # Couleurs terminal (Windows)
```

---

## 🎯 Commandes d'Installation Complètes

### Installation depuis Zéro (GPU NVIDIA)

```bash
# 1. Créer environnement
python -m venv venv
venv\Scripts\activate  # Windows
# ou
source venv/bin/activate  # Linux/macOS

# 2. Mettre à jour pip
pip install --upgrade pip

# 3. Installer PyTorch avec CUDA 12.1 (VERSIONS EXACTES)
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# 4. Installer le reste des dépendances
pip install -r requirements.txt

# 5. Vérifier CUDA
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'CUDA Version: {torch.version.cuda}')"
```

**Sortie attendue:**

```
PyTorch: 2.5.1+cu121
CUDA: True
CUDA Version: 12.1
```

### Installation CPU (Sans GPU)

```bash
# 1-2. Même chose (venv + pip upgrade)

# 3. Installer directement toutes les dépendances
pip install -r requirements.txt
# Installe automatiquement torch==2.5.1 (version CPU)

# 4. Vérifier
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

**Sortie attendue:**

```
PyTorch: 2.5.1
CUDA: False
```

---

## 🔍 Vérification des Versions Installées

### Commande Complète

```bash
pip show torch torchaudio torchvision openai openai-whisper
```

### Versions Attendues (GPU)

```
Name: torch
Version: 2.5.1+cu121

Name: torchaudio
Version: 2.5.1+cu121

Name: torchvision
Version: 0.20.1+cu121

Name: openai
Version: 1.86.0

Name: openai-whisper
Version: 20240930
```

---

## 📊 Compatibilité des Versions

### PyTorch 2.5.1

- ✅ **Python 3.10** - Recommandé
- ✅ **Python 3.11** - Recommandé
- ✅ **Python 3.12** - Compatible
- ⚠️ **Python 3.9** - Déconseillé (ancien)
- ❌ **Python 3.13** - Non testé (trop récent)

### CUDA 12.1

- ✅ **NVIDIA GeForce RTX 20xx** et plus récent
- ✅ **NVIDIA Quadro RTX 4000** et plus récent
- ✅ **NVIDIA Tesla** (data center)
- ❌ **NVIDIA GTX 10xx** et plus ancien (utiliser CUDA 11.8)

### Whisper Model "medium"

- ✅ **VRAM 4GB+** - Fonctionne
- ✅ **VRAM 8GB+** - Optimal
- ⚠️ **RAM 8GB** (CPU) - Lent mais fonctionne
- ✅ **RAM 16GB+** (CPU) - Recommandé

---

## 🚀 Performance Attendue

### Configuration Testée

- **GPU:** NVIDIA Quadro RTX 4000 (8GB VRAM)
- **CPU:** Intel Xeon / Core i7+
- **RAM:** 16GB+
- **Whisper:** Model "medium" sur GPU

### Temps de Traitement (Vidéo de 5 minutes)

```
✅ Génération audio (ElevenLabs):  ~30 secondes
✅ Génération SRT (Whisper GPU):   ~1-2 minutes
✅ Vidéo de fond:                  ~30 secondes
✅ Encodage final:                 ~2-3 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 TOTAL:                          ~5-8 minutes
```

### Avec CPU (Sans GPU)

```
⚠️ Génération audio (ElevenLabs):  ~30 secondes
⚠️ Génération SRT (Whisper CPU):   ~5-10 minutes
⚠️ Vidéo de fond:                  ~1-2 minutes
⚠️ Encodage final:                 ~5-10 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 TOTAL:                          ~15-25 minutes
```

---

## 📝 Notes Importantes

### torchvision 0.20.1 vs 0.22.1

**Question:** Pourquoi 0.20.1 et pas 0.22.1 ?

**Réponse:**

- `torchvision==0.20.1+cu121` est la version **stable** compatible avec `torch==2.5.1+cu121`
- Les versions sont liées : PyTorch 2.5.1 → torchvision 0.20.x
- La version 0.22.x serait pour PyTorch 2.6.x ou plus récent

**Référence:** [PyTorch CUDA 12.1 Index](https://download.pytorch.org/whl/cu121)

### Pourquoi ">=" dans requirements.txt ?

Le `requirements.txt` utilise `==` pour garantir la reproductibilité:

```python
torch==2.5.1        # Version exacte testée
torchvision==0.20.1  # Version exacte testée
```

**Avantages:**

- ✅ Installation identique sur tous les environnements
- ✅ Pas de surprises avec les mises à jour
- ✅ Versions testées et validées

**Si problème:** Vérifier les versions exactes:

```bash
pip show torch torchvision torchaudio
```

---

## 🔧 Mise à Jour des Versions

### Mettre à Jour PyTorch

```bash
# Vérifier les nouvelles versions
pip index versions torch --index-url https://download.pytorch.org/whl/cu121

# Mettre à jour (exemple vers 2.8.0 quand disponible)
pip install torch==2.8.0+cu121 torchvision==0.22.0+cu121 torchaudio==2.8.0+cu121 --index-url https://download.pytorch.org/whl/cu121 --upgrade

# Vérifier
python -c "import torch; print(torch.__version__)"
```

### Mettre à Jour Whisper

```bash
pip install openai-whisper --upgrade

# Vérifier
python -c "import whisper; print(whisper.__version__)"
```

---

## ✅ Checklist de Validation

Après installation, vérifier que tout fonctionne:

```bash
# 1. Python
python --version
# Attendu: Python 3.10.x ou 3.11.x

# 2. FFmpeg
ffmpeg -version
# Attendu: Version récente avec CUDA support

# 3. PyTorch
python -c "import torch; print(f'{torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
# Attendu: 2.5.1+cu121, CUDA: True

# 4. Whisper
python -c "import whisper; model = whisper.load_model('base'); print('Whisper OK')"
# Attendu: Téléchargement du modèle puis "Whisper OK"

# 5. Toutes les dépendances
python -c "import requests, dotenv, librosa, soundfile; print('Toutes les dépendances OK')"
# Attendu: "Toutes les dépendances OK"
```

---

## 📞 Support

Si les versions ne correspondent pas ou si vous avez des problèmes:

1. Vérifiez ce fichier pour les versions exactes
2. Comparez avec `pip show <package>`
3. Réinstallez avec les versions exactes si nécessaire
4. Consultez `INSTALLATION_GUIDE.md` pour le guide complet

---

**Dernière mise à jour:** 28 décembre 2025  
**Environnement de référence:** Windows 11 + NVIDIA Quadro RTX 4000 + CUDA 12.1
