"""
Point d'entrée FastAPI — SagesseDuChrist Video Generator.
"""
import ctypes.util
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── Monkey-patch Windows Whisper ──────────────────────────────────────────────
_orig_find_library = ctypes.util.find_library

def _patched_find_library(name):
    result = _orig_find_library(name)
    if name == "c" and result is None:
        return "msvcrt"
    return result

ctypes.util.find_library = _patched_find_library

# ── Chargement des variables d'environnement ──────────────────────────────────
load_dotenv()

# ── Initialisation de la base de données ─────────────────────────────────────
from backend.database import init_db
init_db()

# ── Application FastAPI ───────────────────────────────────────────────────────
app = FastAPI(
    title="SagesseDuChrist — Video Generator API",
    description="API de génération de vidéos religieuses avec sous-titres et overlays bibliques.",
    version="1.0.0",
)

# CORS : autorise le frontend React en développement (localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes API (avant les mounts pour avoir la priorité) ─────────────────────
from backend.routers import jobs, assets
app.include_router(jobs.router)
app.include_router(assets.router)


@app.get("/api/ping")
async def ping():
    return {"status": "ok", "service": "SagesseDuChrist Video Generator"}

# ── Servir les fichiers de sortie (vidéos téléchargeables) ───────────────────
from backend.config import OUTPUTS_DIR
OUTPUTS_DIR.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# ── Servir le build React (frontend) — doit être en dernier ──────────────────
FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_BUILD.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {
            "message": "SagesseDuChrist Video Generator API",
            "docs": "/docs",
            "frontend": "Build React non trouvé — lancez build_frontend.bat",
        }
