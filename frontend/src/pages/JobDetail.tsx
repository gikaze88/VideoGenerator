import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Download, Loader2, CheckCircle, XCircle, Clock, Terminal,
  Youtube, ExternalLink, Upload, LogIn, LogOut, RefreshCw,
} from 'lucide-react'
import {
  getJob, getJobLogs, getJobFiles, getDownloadUrl, formatDate, formatDuration,
  STATUS_LABELS, STATUS_COLORS, type Job, type JobStatus,
  getYoutubeAuthStatus, getYoutubeAuthUrl, revokeYoutubeToken,
  getYoutubePlaylists, uploadToYoutube, getYoutubeJobStatus,
  type YoutubePlaylist, type YoutubeUploadResult,
} from '../api'

const STEP_LABELS: Record<string, string> = {
  'Étape 1': '📝 Extraction du script',
  'Étape 2': '🎙️  Génération audio',
  'Étape 3': '📝 Génération sous-titres',
  'Étape 4': '🙏 Transitions de prière',
  'Étape 5': '📖 Versets bibliques',
  'Étape 6': '🎬 Vidéo de fond',
  'Étape 7': '🎥 Encodage final',
}

function detectCurrentStep(lines: string[]): number {
  let step = 0
  for (const line of lines) {
    const m = line.match(/Étape (\d+)\//)
    if (m) step = Math.max(step, parseInt(m[1]))
  }
  return step
}

function StatusIcon({ status }: { status: JobStatus }) {
  if (status === 'running') return <Loader2 size={18} className="animate-spin text-blue-400" />
  if (status === 'completed') return <CheckCircle size={18} className="text-green-400" />
  if (status === 'failed') return <XCircle size={18} className="text-red-400" />
  return <Clock size={18} className="text-gray-400" />
}

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const [job, setJob] = useState<Job | null>(null)
  const [logLines, setLogLines] = useState<string[]>([])
  const [linesLoaded, setLinesLoaded] = useState(0)
  const [notFound, setNotFound] = useState(false)
  const [outputFiles, setOutputFiles] = useState<string[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── YouTube state ──────────────────────────────────────────────────────────
  const [ytAuthenticated, setYtAuthenticated] = useState<boolean | null>(null)
  const [ytAuthLoading, setYtAuthLoading] = useState(false)
  const [playlists, setPlaylists] = useState<YoutubePlaylist[]>([])
  const [ytForm, setYtForm] = useState({
    title: '',
    description: '',
    tags: '',
    privacy: 'private',
    categoryId: '27',
    playlistId: '',
    filename: '',
  })
  const [ytThumbnail, setYtThumbnail] = useState<File | null>(null)
  const [ytUploading, setYtUploading] = useState(false)
  const [ytResult, setYtResult] = useState<YoutubeUploadResult | null>(null)
  const [ytError, setYtError] = useState<string | null>(null)
  const ytAuthPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchJob() {
    if (!jobId) return
    try {
      const j = await getJob(jobId)
      setJob(j)
      return j
    } catch {
      setNotFound(true)
      return null
    }
  }

  // ── YouTube helpers ────────────────────────────────────────────────────────
  async function checkYtAuth() {
    try {
      const { authenticated } = await getYoutubeAuthStatus()
      setYtAuthenticated(authenticated)
      if (authenticated) loadPlaylists()
    } catch {
      setYtAuthenticated(false)
    }
  }

  async function loadPlaylists() {
    try {
      const list = await getYoutubePlaylists()
      setPlaylists(list)
    } catch {
      setPlaylists([])
    }
  }

  async function handleYtAuth() {
    setYtAuthLoading(true)
    setYtError(null)
    try {
      // 1) Demander l'URL d'authentification au backend
      const { url } = await getYoutubeAuthUrl()
      // 2) Ouvrir l'URL dans un nouvel onglet/fenêtre du navigateur courant
      window.open(url, '_blank', 'noopener,noreferrer')
      // 3) Poller le statut d'authentification toutes les 2 secondes
      if (ytAuthPollRef.current) {
        clearInterval(ytAuthPollRef.current)
      }
      ytAuthPollRef.current = setInterval(async () => {
        try {
          const { authenticated } = await getYoutubeAuthStatus()
          if (authenticated) {
            setYtAuthenticated(true)
            clearInterval(ytAuthPollRef.current!)
            ytAuthPollRef.current = null
            await loadPlaylists()
          }
        } catch {
          // on ignore les erreurs ponctuelles de polling
        }
      }, 2000)
    } catch (e: any) {
      setYtError(e.message)
    } finally {
      setYtAuthLoading(false)
    }
  }

  async function handleYtRevoke() {
    await revokeYoutubeToken()
    setYtAuthenticated(false)
    setPlaylists([])
    setYtResult(null)
    if (ytAuthPollRef.current) {
      clearInterval(ytAuthPollRef.current)
      ytAuthPollRef.current = null
    }
  }

  async function handleYtUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!jobId) return
    setYtUploading(true)
    setYtError(null)
    setYtResult(null)
    try {
      const result = await uploadToYoutube(jobId, {
        ...ytForm,
        thumbnail: ytThumbnail ?? undefined,
      })
      setYtResult(result)
      // Refresh job to get youtube_video_id
      const updated = await getJob(jobId)
      setJob(updated)
    } catch (e: any) {
      setYtError(e.message)
    } finally {
      setYtUploading(false)
    }
  }

  async function fetchLogs(fromLine: number) {
    if (!jobId) return 0
    try {
      const data = await getJobLogs(jobId, fromLine)
      if (data.lines.length > 0) {
        setLogLines((prev) => [...prev, ...data.lines])
        setLinesLoaded(data.total_lines)
      }
      return data.total_lines
    } catch {
      return fromLine
    }
  }

  useEffect(() => {
    let cancelled = false
    let currentLine = 0

    async function poll() {
      if (cancelled) return
      const j = await fetchJob()
      if (!j) return

      const newLine = await fetchLogs(currentLine)
      currentLine = newLine

      if (j.status === 'completed' && !cancelled) {
        const files = await getJobFiles(j.id)
        if (!cancelled) setOutputFiles(files)
      }

      if (!cancelled && (j.status === 'pending' || j.status === 'running')) {
        pollRef.current = setTimeout(poll, 3000)
      }
    }

    poll()
    return () => {
      cancelled = true
      if (pollRef.current) clearTimeout(pollRef.current)
    }
  }, [jobId])

  // Load YouTube auth status once on mount
  useEffect(() => {
    checkYtAuth()
  }, [])

  // Pre-fill YouTube title from job title when job is loaded
  useEffect(() => {
    if (job?.title && !ytForm.title) {
      setYtForm((f) => ({ ...f, title: job.title ?? '' }))
    }
    // Default filename to first output file or main video
    if (outputFiles.length > 0 && !ytForm.filename) {
      const preferred = outputFiles.find((f) => f.includes('overlay')) ?? outputFiles[0]
      setYtForm((f) => ({ ...f, filename: preferred }))
    }
  }, [job, outputFiles])

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  if (notFound) {
    return (
      <div className="text-center py-20 text-gray-400">
        <p>Job introuvable.</p>
        <Link to="/" className="text-amber-400 hover:underline mt-2 inline-block">Retour</Link>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 size={28} className="animate-spin text-gray-500" />
      </div>
    )
  }

  const currentStep = detectCurrentStep(logLines)
  const totalSteps = job.style === 'audio_srt' ? 6 : 7
  const progress = job.status === 'completed' ? 100 : Math.round((currentStep / totalSteps) * 100)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start sm:items-center gap-2 sm:gap-3">
        <Link to="/history" className="text-gray-500 hover:text-gray-300 transition-colors mt-1 sm:mt-0 shrink-0">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-base sm:text-xl font-bold text-gray-100 truncate">
            {job.title || 'Génération en cours…'}
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {job.style} · <span className="font-mono text-gray-600">{job.id.slice(0, 8)}…</span>
          </p>
        </div>
        <span className={`text-xs font-medium px-2 sm:px-3 py-1 rounded-full flex items-center gap-1 sm:gap-1.5 shrink-0 ${STATUS_COLORS[job.status]}`}>
          <StatusIcon status={job.status} />
          <span className="hidden sm:inline">{STATUS_LABELS[job.status]}</span>
        </span>
      </div>

      {/* Meta cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetaCard label="Créé le" value={formatDate(job.created_at)} />
        <MetaCard label="Démarré" value={job.started_at ? formatDate(job.started_at) : '—'} />
        <MetaCard label="Terminé" value={job.completed_at ? formatDate(job.completed_at) : '—'} />
        <MetaCard label="Durée" value={formatDuration(job.created_at, job.completed_at)} />
      </div>

      {/* Progress */}
      {(job.status === 'running' || job.status === 'completed') && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>Progression</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                job.status === 'completed' ? 'bg-green-500' : 'bg-amber-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-7 gap-1 mt-2">
            {Array.from({ length: totalSteps }, (_, i) => {
              const step = i + 1
              const isDone = job.status === 'completed' || step < currentStep
              const isCurrent = step === currentStep && job.status === 'running'
              return (
                <div
                  key={step}
                  className={`text-xs px-2 py-1 rounded text-center transition-colors ${
                    isDone
                      ? 'bg-green-900 text-green-300'
                      : isCurrent
                      ? 'bg-amber-900 text-amber-300 animate-pulse'
                      : 'bg-gray-800 text-gray-600'
                  }`}
                >
                  {step}/{totalSteps}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Erreur */}
      {job.status === 'failed' && job.error_message && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4">
          <p className="text-red-300 text-sm font-medium mb-1">Erreur lors de la génération</p>
          <p className="text-red-400 text-xs font-mono">{job.error_message}</p>
        </div>
      )}

      {/* Téléchargement */}
      {job.status === 'completed' && (
        <div className="bg-green-900/20 border border-green-800 rounded-xl p-3 sm:p-4 space-y-3">
          <div>
            <p className="text-green-300 font-medium text-sm sm:text-base">Vidéo prête !</p>
            <p className="text-green-500 text-xs sm:text-sm mt-0.5">
              Durée totale : {formatDuration(job.created_at, job.completed_at)}
            </p>
          </div>
          {outputFiles.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {outputFiles.map((filename) => {
                const isOverlay = filename.includes('overlay')
                const label = isOverlay ? 'Avec versets bibliques' : 'Version standard'
                return (
                  <a
                    key={filename}
                    href={getDownloadUrl(job.id, filename)}
                    download={filename}
                    className={`flex items-center justify-center gap-2 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm ${
                      isOverlay
                        ? 'bg-amber-600 hover:bg-amber-500 text-white'
                        : 'bg-green-600 hover:bg-green-500 text-white'
                    }`}
                  >
                    <Download size={15} />
                    {label}
                  </a>
                )
              })}
            </div>
          ) : (
            <a
              href={getDownloadUrl(job.id)}
              download
              className="flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 text-white
                         font-semibold px-5 py-2.5 rounded-xl transition-colors w-full sm:w-fit"
            >
              <Download size={16} />
              Télécharger
            </a>
          )}
        </div>
      )}

      {/* YouTube Upload */}
      {job.status === 'completed' && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 sm:p-4 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Youtube size={18} className="text-red-500 shrink-0" />
              <span className="text-gray-200 font-medium text-sm sm:text-base">Publier sur YouTube</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {ytAuthenticated === true && (
                <span className="text-xs text-green-400 flex items-center gap-1">
                  <CheckCircle size={12} /> Connecté
                </span>
              )}
              {ytAuthenticated === false && (
                <span className="text-xs text-gray-500">Non connecté</span>
              )}
              {ytAuthenticated === true && (
                <button
                  onClick={handleYtRevoke}
                  className="text-xs text-gray-500 hover:text-red-400 flex items-center gap-1 transition-colors"
                  title="Déconnecter YouTube"
                >
                  <LogOut size={12} /> Déconnecter
                </button>
              )}
              <button
                onClick={checkYtAuth}
                className="text-gray-600 hover:text-gray-400 transition-colors"
                title="Rafraîchir le statut"
              >
                <RefreshCw size={13} />
              </button>
            </div>
          </div>

          {/* Résultat upload */}
          {ytResult && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-3 space-y-2">
              <p className="text-red-300 text-sm font-medium flex items-center gap-2">
                <CheckCircle size={14} /> Vidéo uploadée avec succès !
              </p>
              <div className="flex flex-wrap gap-2">
                <a
                  href={ytResult.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs bg-red-700 hover:bg-red-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                >
                  <ExternalLink size={12} /> Voir sur YouTube
                </a>
                <a
                  href={ytResult.studio_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <ExternalLink size={12} /> Studio YouTube
                </a>
              </div>
              <p className="text-xs text-gray-500">Statut : {ytResult.privacy}</p>
            </div>
          )}

          {/* Déjà uploadé (persisté en DB) */}
          {!ytResult && job.youtube_video_id && (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 space-y-2">
              <p className="text-gray-300 text-sm">Déjà publié sur YouTube</p>
              <div className="flex flex-wrap gap-2">
                <a
                  href={`https://youtu.be/${job.youtube_video_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs bg-red-700 hover:bg-red-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                >
                  <ExternalLink size={12} /> Voir sur YouTube
                </a>
                <a
                  href={`https://studio.youtube.com/video/${job.youtube_video_id}/edit`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <ExternalLink size={12} /> Studio YouTube
                </a>
              </div>
            </div>
          )}

          {/* Auth button si non connecté */}
          {ytAuthenticated === false && (
            <div className="text-center py-2">
              <button
                onClick={handleYtAuth}
                disabled={ytAuthLoading}
                className="flex items-center gap-2 mx-auto bg-red-600 hover:bg-red-500 disabled:opacity-50
                           text-white font-medium px-5 py-2.5 rounded-xl transition-colors"
              >
                {ytAuthLoading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
                {ytAuthLoading ? 'Ouverture du navigateur…' : 'Connecter mon compte Google'}
              </button>
              <p className="text-xs text-gray-600 mt-2">
                Le navigateur s'ouvrira pour vous connecter à Google.
              </p>
            </div>
          )}

          {/* Formulaire upload si authentifié */}
          {ytAuthenticated === true && !ytResult && (
            <form onSubmit={handleYtUpload} className="space-y-3">
              {/* Titre */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Titre *</label>
                <input
                  type="text"
                  required
                  value={ytForm.title}
                  onChange={(e) => setYtForm((f) => ({ ...f, title: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  placeholder="Titre de la vidéo YouTube"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Description</label>
                <textarea
                  rows={4}
                  value={ytForm.description}
                  onChange={(e) => setYtForm((f) => ({ ...f, description: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-sm text-gray-200 focus:outline-none focus:border-red-600 resize-none"
                  placeholder="Description de la vidéo…"
                />
              </div>

              {/* Tags */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Tags (séparés par des virgules)</label>
                <input
                  type="text"
                  value={ytForm.tags}
                  onChange={(e) => setYtForm((f) => ({ ...f, tags: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  placeholder="prière, foi, guérison, évangile…"
                />
              </div>

              {/* Fichier vidéo + Confidentialité */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Fichier vidéo à uploader</label>
                  <select
                    value={ytForm.filename}
                    onChange={(e) => setYtForm((f) => ({ ...f, filename: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  >
                    <option value="">Vidéo principale</option>
                    {outputFiles.map((fn) => (
                      <option key={fn} value={fn}>{fn}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Confidentialité</label>
                  <select
                    value={ytForm.privacy}
                    onChange={(e) => setYtForm((f) => ({ ...f, privacy: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  >
                    <option value="private">🔒 Privé</option>
                    <option value="unlisted">🔗 Non répertorié</option>
                    <option value="public">🌍 Public</option>
                  </select>
                </div>
              </div>

              {/* Catégorie + Playlist */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Catégorie YouTube</label>
                  <select
                    value={ytForm.categoryId}
                    onChange={(e) => setYtForm((f) => ({ ...f, categoryId: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  >
                    <option value="27">Éducation</option>
                    <option value="22">People & Blogs</option>
                    <option value="29">Activisme & ONG</option>
                    <option value="26">Comment faire</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Playlist</label>
                  <select
                    value={ytForm.playlistId}
                    onChange={(e) => setYtForm((f) => ({ ...f, playlistId: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                               text-sm text-gray-200 focus:outline-none focus:border-red-600"
                  >
                    <option value="">— Aucune playlist —</option>
                    {playlists.map((p) => (
                      <option key={p.id} value={p.id}>{p.title}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Miniature */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Miniature (optionnelle)</label>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => setYtThumbnail(e.target.files?.[0] ?? null)}
                  className="w-full text-xs text-gray-400 file:mr-3 file:py-1.5 file:px-3
                             file:rounded-lg file:border-0 file:text-xs file:font-medium
                             file:bg-gray-700 file:text-gray-300 hover:file:bg-gray-600"
                />
                {ytThumbnail && (
                  <p className="text-xs text-gray-500 mt-1">
                    Sélectionnée : {ytThumbnail.name}
                  </p>
                )}
              </div>

              {/* Erreur */}
              {ytError && (
                <div className="bg-red-900/30 border border-red-700 rounded-lg p-3">
                  <p className="text-red-400 text-xs font-mono">{ytError}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={ytUploading}
                className="flex items-center gap-2 bg-red-600 hover:bg-red-500 disabled:opacity-50
                           text-white font-semibold px-5 py-2.5 rounded-xl transition-colors w-full justify-center"
              >
                {ytUploading
                  ? <><Loader2 size={16} className="animate-spin" /> Upload en cours…</>
                  : <><Upload size={16} /> Uploader sur YouTube</>
                }
              </button>
              {ytUploading && (
                <p className="text-xs text-gray-500 text-center">
                  L'upload peut prendre plusieurs minutes selon la taille de la vidéo.
                </p>
              )}
            </form>
          )}
        </div>
      )}

      {/* Logs */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Terminal size={14} />
          <span>Logs ({logLines.length} ligne{logLines.length > 1 ? 's' : ''})</span>
          {job.status === 'running' && (
            <Loader2 size={12} className="animate-spin ml-1" />
          )}
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 sm:p-4 h-60 sm:h-80 overflow-y-auto font-mono text-xs text-gray-400 leading-relaxed">
          {logLines.length === 0 ? (
            <span className="text-gray-600">En attente de logs…</span>
          ) : (
            logLines.map((line, i) => (
              <div
                key={i}
                className={
                  line.includes('❌') ? 'text-red-400' :
                  line.includes('✅') ? 'text-green-400' :
                  line.includes('🚀') ? 'text-amber-300' :
                  line.includes('🎉') ? 'text-amber-400 font-semibold' :
                  ''
                }
              >
                {line || '\u00A0'}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  )
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-3 py-2">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-medium text-gray-200 mt-0.5 truncate">{value}</p>
    </div>
  )
}
