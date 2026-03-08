"""
Service d'intégration YouTube Data API v3.

Gère l'authentification OAuth 2.0 (flux Desktop App), l'upload de vidéos,
la gestion des miniatures et des playlists.

Fonctionnement OAuth :
  - Premier lancement : ouvre le navigateur pour la connexion Google.
  - Le token est sauvegardé dans youtube_token.json (ignoré par git).
  - Les lancements suivants : rafraîchissement automatique du token.
"""
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from backend.config import CLIENT_SECRETS_PATH, YOUTUBE_TOKEN_PATH

# Scopes nécessaires : upload + lecture des playlists
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def is_authenticated() -> bool:
    """Vérifie si un token valide (ou rafraîchissable) existe."""
    if not YOUTUBE_TOKEN_PATH.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)
        return creds.valid or bool(creds.expired and creds.refresh_token)
    except Exception:
        return False


def get_credentials() -> Credentials:
    """
    Retourne des credentials valides.
    Si le token est expiré, le rafraîchit automatiquement.
    Si aucun token n'existe, ouvre le navigateur pour l'autorisation initiale.
    """
    creds = None

    if YOUTUBE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_PATH.exists():
                raise FileNotFoundError(
                    f"client_secrets.json introuvable : {CLIENT_SECRETS_PATH}\n"
                    "Téléchargez-le depuis Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


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
    log_callback=None,
) -> str:
    """
    Upload une vidéo sur YouTube et retourne son video_id.

    Paramètres :
      - privacy     : "private" | "unlisted" | "public"
      - category_id : "27" = People & Blogs (défaut), "22" = People & Blogs (EN)
      - thumbnail   : chemin vers une image .jpg/.png (optionnel)
      - playlist_id : ID de playlist pour y ajouter la vidéo (optionnel)
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
            "defaultLanguage": "fr",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
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
