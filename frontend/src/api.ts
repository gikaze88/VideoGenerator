/**
 * Client API — toutes les requêtes vers le backend FastAPI.
 */

const BASE = '/api'

export type JobStyle = 'full' | 'simple' | 'audio_srt'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface Job {
  id: string
  style: string
  title: string | null
  status: JobStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  output_video_path: string | null
  error_message: string | null
  youtube_video_id: string | null
  youtube_status: string | null
}

export interface JobLogs {
  job_id: string
  lines: string[]
  total_lines: number
  is_running: boolean
}

export interface Assets {
  songs: string[]
  songs_count: number
  videos: string[]
  videos_count: number
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export async function createJob(
  style: JobStyle,
  scriptText: string,
  files: {
    backgroundVideo?: File
    audioFile?: File
    srtFile?: File
  } = {}
): Promise<{ job_id: string; status: string }> {
  const form = new FormData()
  form.append('style', style)
  form.append('script_text', scriptText)
  if (files.backgroundVideo) form.append('background_video', files.backgroundVideo)
  if (files.audioFile) form.append('audio_file', files.audioFile)
  if (files.srtFile) form.append('srt_file', files.srtFile)

  const res = await fetch(`${BASE}/jobs`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Erreur lors de la création du job')
  }
  return res.json()
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch(`${BASE}/jobs`)
  if (!res.ok) throw new Error('Erreur lors de la récupération des jobs')
  return res.json()
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${jobId}`)
  if (!res.ok) throw new Error('Job non trouvé')
  return res.json()
}

export async function getJobLogs(jobId: string, fromLine = 0): Promise<JobLogs> {
  const res = await fetch(`${BASE}/jobs/${jobId}/logs?from_line=${fromLine}`)
  if (!res.ok) throw new Error('Erreur lors de la récupération des logs')
  return res.json()
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/jobs/${jobId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Erreur lors de la suppression')
}

export async function getJobFiles(jobId: string): Promise<string[]> {
  const res = await fetch(`${BASE}/jobs/${jobId}/files`)
  if (!res.ok) return []
  const data = await res.json()
  return data.files as string[]
}

export function getDownloadUrl(jobId: string, filename?: string): string {
  const base = `${BASE}/jobs/${jobId}/download`
  return filename ? `${base}?filename=${encodeURIComponent(filename)}` : base
}

// ── YouTube ───────────────────────────────────────────────────────────────────

export interface YoutubePlaylist {
  id: string
  title: string
}

export interface YoutubeUploadResult {
  video_id: string
  url: string
  studio_url: string
  privacy: string
  logs: string[]
}

export interface YoutubeJobStatus {
  youtube_video_id: string | null
  youtube_status: string | null
  url: string | null
  studio_url: string | null
}

export async function getYoutubeAuthStatus(): Promise<{ authenticated: boolean }> {
  const res = await fetch(`${BASE}/youtube/auth-status`)
  if (!res.ok) throw new Error('Erreur auth-status YouTube')
  return res.json()
}

export async function getYoutubeAuthUrl(): Promise<{ url: string }> {
  const res = await fetch(`${BASE}/youtube/auth-url`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Erreur génération URL YouTube')
  }
  return res.json()
}

export async function revokeYoutubeToken(): Promise<void> {
  await fetch(`${BASE}/youtube/revoke`, { method: 'POST' })
}

export async function getYoutubePlaylists(): Promise<YoutubePlaylist[]> {
  const res = await fetch(`${BASE}/youtube/playlists`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Erreur playlists YouTube')
  }
  const data = await res.json()
  return data.playlists as YoutubePlaylist[]
}

export async function uploadToYoutube(
  jobId: string,
  params: {
    title: string
    description: string
    tags: string
    privacy: string
    categoryId: string
    playlistId: string
    filename: string
    thumbnail?: File
  }
): Promise<YoutubeUploadResult> {
  const form = new FormData()
  form.append('title', params.title)
  form.append('description', params.description)
  form.append('tags', params.tags)
  form.append('privacy', params.privacy)
  form.append('category_id', params.categoryId)
  form.append('playlist_id', params.playlistId)
  form.append('filename', params.filename)
  if (params.thumbnail) form.append('thumbnail', params.thumbnail)

  const res = await fetch(`${BASE}/youtube/upload/${jobId}`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Erreur upload YouTube')
  }
  return res.json()
}

export async function getYoutubeJobStatus(jobId: string): Promise<YoutubeJobStatus> {
  const res = await fetch(`${BASE}/youtube/job/${jobId}`)
  if (!res.ok) throw new Error('Erreur statut YouTube')
  return res.json()
}

// ── Assets ───────────────────────────────────────────────────────────────────

export async function getAssets(): Promise<Assets> {
  const res = await fetch(`${BASE}/assets`)
  if (!res.ok) throw new Error('Erreur assets')
  return res.json()
}

// ── Utilitaires ───────────────────────────────────────────────────────────────

export function formatDuration(start: string, end: string | null): string {
  if (!end) return '—'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const secs = Math.floor(ms / 1000)
  const mins = Math.floor(secs / 60)
  const h = Math.floor(mins / 60)
  if (h > 0) return `${h}h ${mins % 60}min`
  if (mins > 0) return `${mins}min ${secs % 60}s`
  return `${secs}s`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'En attente',
  running: 'En cours',
  completed: 'Terminé',
  failed: 'Échoué',
}

export const STATUS_COLORS: Record<JobStatus, string> = {
  pending: 'bg-gray-700 text-gray-300',
  running: 'bg-blue-900 text-blue-300',
  completed: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
}
