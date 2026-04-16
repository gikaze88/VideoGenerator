"""
Service d'intégration YouTube Data API v3.

Gère l'authentification OAuth 2.0, l'upload de vidéos,
la gestion des miniatures et des playlists.

Deux couches :
  - Flux OAuth "smart" basé sur URL (Flow) :
      * le backend génère une URL d'autorisation
      * le frontend ouvre cette URL dans le navigateur courant
      * Google redirige vers /api/youtube/oauth-callback avec ?code=...
      * le backend échange le code contre un token et le sauvegarde
  - Utilisation du token sauvegardé (Credentials) pour toutes les requêtes API.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from backend.config import CLIENT_SECRETS_PATH, YOUTUBE_TOKEN_PATH

# Scopes nécessaires : upload + lecture des playlists
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# URL de redirection utilisée par Google pour renvoyer le code
# Doit correspondre à celle déclarée dans la console Google (Authorized redirect URI)
REDIRECT_URI = "http://localhost:8000/api/youtube/oauth-callback"

# Flow OAuth en attente (entre /auth-url et /oauth-callback)
_pending_flow_lock = threading.Lock()
_pending_flow: Optional[Flow] = None


def is_authenticated() -> bool:
    """Vérifie si un token valide (ou rafraîchissable) existe."""
    if not YOUTUBE_TOKEN_PATH.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)
        return creds.valid or bool(creds.expired and creds.refresh_token)
    except Exception:
        return False


def _load_credentials() -> Optional[Credentials]:
    """Charge les credentials depuis le disque sans déclencher d'OAuth interactif."""
    if not YOUTUBE_TOKEN_PATH.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)
    except Exception:
        return None

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            return None
    return creds if creds and creds.valid else None


def get_credentials() -> Credentials:
    """
    Retourne des credentials valides basés sur le token sauvegardé.
    Ne lance PAS de flux OAuth interactif : celui-ci est géré séparément
    via get_auth_url() + exchange_code().
    """
    creds = _load_credentials()
    if not creds:
        raise RuntimeError(
            "Aucun token YouTube valide trouvé. "
            "Lancez d'abord le flux OAuth via /api/youtube/auth-url."
        )
    return creds


def get_auth_url() -> str:
    """
    Crée un Flow OAuth et retourne l'URL d'autorisation.
    Le Flow est conservé en mémoire jusqu'à l'appel à exchange_code().
    """
    if not CLIENT_SECRETS_PATH.exists():
        raise FileNotFoundError(
            f"client_secrets.json introuvable : {CLIENT_SECRETS_PATH}\n"
            "Téléchargez-le depuis Google Cloud Console."
        )

    global _pending_flow
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    with _pending_flow_lock:
        _pending_flow = flow

    return auth_url


def exchange_code(code: str) -> None:
    """
    Complète le flux OAuth en échangeant le code contre un token,
    puis sauvegarde les credentials dans youtube_token.json.
    """
    global _pending_flow
    with _pending_flow_lock:
        flow = _pending_flow
        _pending_flow = None

    if flow is None:
        raise RuntimeError("Aucun flux OAuth en attente. Relancez la demande d'authentification.")

    flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds:
        raise RuntimeError("Impossible de récupérer les credentials YouTube.")

    YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def get_youtube_client():
    """Construit et retourne un client YouTube API authentifié."""
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def get_playlists() -> list[dict]:
    """
    Retourne la liste des playlists de la chaîne connectée.
    Chaque entrée : {"id": str, "title": str}.
    """
    youtube = get_youtube_client()
    response = youtube.playlists().list(
        part="snippet", mine=True, maxResults=50
    ).execute()
    return [
        {"id": p["id"], "title": p["snippet"]["title"]}
        for p in response.get("items", [])
    ]


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "private",
    category_id: str = "27",
    thumbnail_path: Path | None = None,
    playlist_id: str | None = None,
    language: str = "fr",
    license: str = "youtube",
    embeddable: bool = True,
    log_callback=None,
) -> str:
    """
    Upload une vidéo sur YouTube et retourne son video_id.

    Paramètres :
      - privacy     : "private" | "unlisted" | "public"
      - category_id : "22" = People & Blogs, "27" = Education (défaut),
                      "26" = Howto & Style, "29" = Nonprofits & Activism
      - thumbnail   : chemin vers une image .jpg/.png (optionnel)
      - playlist_id : ID de playlist pour y ajouter la vidéo (optionnel)
      - language    : langue de la vidéo et de l'audio (défaut: "fr")
      - license     : "youtube" (Standard) ou "creativeCommon"
      - embeddable  : autoriser l'intégration sur d'autres sites
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    youtube = get_youtube_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "license": license,
            "embeddable": embeddable,
            "publicStatsViewable": True,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        chunksize=50 * 1024 * 1024,  # chunks de 50 Mo
        resumable=True,
        mimetype="video/mp4",
    )

    _log(f"  📤 Début de l'upload : {video_path.name}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            _log(f"  ⏳ Upload en cours : {pct}%")

    video_id = response["id"]
    _log(f"  ✅ Vidéo uploadée → https://youtu.be/{video_id} (statut : {privacy})")

    # Miniature
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()
            _log("  🖼️  Miniature ajoutée")
        except HttpError as e:
            _log(f"  ⚠️  Miniature ignorée (compte non vérifié?) : {e}")

    # Ajout à une playlist
    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            _log(f"  📋 Ajouté à la playlist {playlist_id}")
        except HttpError as e:
            _log(f"  ⚠️  Ajout playlist échoué : {e}")

    return video_id
