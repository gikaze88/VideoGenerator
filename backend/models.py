"""
Schémas Pydantic pour l'API.
"""
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel


JobStyle = Literal["full", "simple", "audio_srt"]
JobStatus = Literal["pending", "running", "completed", "failed"]


class JobCreate(BaseModel):
    style: JobStyle
    # Le contenu du script est envoyé en multipart (fichier ou texte) — voir router


class JobResponse(BaseModel):
    id: str
    style: str
    title: Optional[str]
    status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    output_video_path: Optional[str]
    error_message: Optional[str]

    @property
    def has_output(self) -> bool:
        return self.output_video_path is not None


class JobLogResponse(BaseModel):
    job_id: str
    lines: list[str]
    is_running: bool


class AssetListResponse(BaseModel):
    songs: list[str]
    videos: list[str]
