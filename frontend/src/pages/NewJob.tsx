import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Upload, Play, Info, Music, Video, Youtube, ChevronDown, ChevronUp,
  LogIn, CheckCircle, Loader2, LogOut, Moon, Sun,
} from 'lucide-react'
import {
  createJob, getAssets, getYoutubeAuthStatus, getYoutubeAuthUrl,
  revokeYoutubeToken, getYoutubePlaylists,
  type JobStyle, type Assets, type YoutubeFormData, type YoutubePlaylist, type VideoMode,
} from '../api'

const STYLE_INFO: Record<JobStyle, { label: string; description: string; extraFiles: string[] }> = {
  full: {
    label: 'Full (ElevenLabs + vidéos_db)',
    description: 'Pipeline complet : TTS via ElevenLabs, vidéo de fond assemblée aléatoirement depuis videos_db/.',
    extraFiles: [],
  },
  simple: {
    label: 'Simple (ElevenLabs + vidéo unique)',
    description: 'Comme Full, mais boucle une seule vidéo de fond que vous fournissez.',
    extraFiles: ['Vidéo de fond (MP4)'],
  },
  audio_srt: {
    label: 'Audio + SRT (sans TTS)',
    description: 'Pas de TTS — vous fournissez l\'audio et les sous-titres. Idéal pour réutiliser un enregistrement existant.',
    extraFiles: ['Fichier audio (MP3/WAV)', 'Fichier SRT', 'Vidéo de fond (optionnelle)'],
  },
}

const SCRIPT_PLACEHOLDER = `Titre: Mon titre de vidéo

Transcript:
Votre texte ici. Les versets bibliques entre «guillemets français» seront détectés automatiquement.

Dans Psaume trente-quatre verset dix-huit : «L'Éternel est près de ceux qui ont le cœur brisé.»

Maintenant prions ensemble...`

const YT_CATEGORIES = [
  { id: '27', label: 'Education' },
  { id: '29', label: 'Nonprofits & Activism' },
  { id: '22', label: 'People & Blogs' },
  { id: '26', label: 'Howto & Style' },
]

export default function NewJob() {
  const navigate = useNavigate()
  const [style, setStyle] = useState<JobStyle>('full')
  const [videoMode, setVideoMode] = useState<VideoMode>('dark')
  const [scriptText, setScriptText] = useState('')
  const [bgVideo, setBgVideo] = useState<File | null>(null)
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [srtFile, setSrtFile] = useState<File | null>(null)
  const [assets, setAssets] = useState<Assets | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // YouTube state
  const [ytAutoUpload, setYtAutoUpload] = useState(false)
  const [ytExpanded, setYtExpanded] = useState(false)
  const [ytAuthenticated, setYtAuthenticated] = useState<boolean | null>(null)
  const [ytAuthLoading, setYtAuthLoading] = useState(false)
  const [playlists, setPlaylists] = useState<YoutubePlaylist[]>([])
  const [ytForm, setYtForm] = useState<YoutubeFormData>({
    title: '',
    description: '',
    tags: '',
    privacy: 'private',
    categoryId: '27',
    playlistId: '',
    language: 'fr',
    license: 'youtube',
    embeddable: true,
  })
  const [ytThumbnail, setYtThumbnail] = useState<File | null>(null)

  useEffect(() => {
    getAssets().then(setAssets).catch(() => null)
    checkYtAuth()
  }, [])

  async function checkYtAuth() {
    try {
      const { authenticated } = await getYoutubeAuthStatus()
      setYtAuthenticated(authenticated)
      if (authenticated) {
        try {
          const list = await getYoutubePlaylists()
          setPlaylists(list)
        } catch { setPlaylists([]) }
      }
    } catch { setYtAuthenticated(false) }
  }

  async function handleYtAuth() {
    setYtAuthLoading(true)
    try {
      const { url } = await getYoutubeAuthUrl()
      window.open(url, '_blank', 'noopener,noreferrer')
      const poll = setInterval(async () => {
        try {
          const { authenticated } = await getYoutubeAuthStatus()
          if (authenticated) {
            clearInterval(poll)
            setYtAuthenticated(true)
            setYtAuthLoading(false)
            try {
              const list = await getYoutubePlaylists()
              setPlaylists(list)
            } catch { setPlaylists([]) }
          }
        } catch {}
      }, 2000)
    } catch {
      setYtAuthLoading(false)
    }
  }

  const info = STYLE_INFO[style]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!scriptText.trim()) {
      setError('Le texte du script est requis.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const ytData: YoutubeFormData | undefined =
        ytAutoUpload && ytForm.title.trim()
          ? { ...ytForm, thumbnail: ytThumbnail ?? undefined }
          : undefined

      const result = await createJob(
        style,
        scriptText,
        {
          backgroundVideo: bgVideo ?? undefined,
          audioFile: audioFile ?? undefined,
          srtFile: srtFile ?? undefined,
        },
        ytData,
        videoMode,
      )
      navigate(`/jobs/${result.job_id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Nouvelle génération</h1>
        <p className="text-gray-400 mt-1">Choisissez un style, collez votre script et lancez.</p>
      </div>

      {/* Assets info */}
      {assets && (
        <div className="flex flex-wrap gap-3 sm:gap-4 text-xs sm:text-sm">
          <div className="flex items-center gap-1.5 text-gray-500">
            <Moon size={14} />
            <span>{assets.videos_dark_count} vidéo(s) sombres</span>
          </div>
          <div className="flex items-center gap-1.5 text-gray-500">
            <Sun size={14} />
            <span>{assets.videos_light_count} vidéo(s) claires</span>
          </div>
          <div className="flex items-center gap-1.5 text-gray-500">
            <Music size={14} />
            <span>{assets.songs_count} musique(s)</span>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Style selector */}
        <div className="space-y-3">
          <label className="block text-sm font-medium text-gray-300">Style de génération</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {(Object.keys(STYLE_INFO) as JobStyle[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStyle(s)}
                className={`text-left p-4 rounded-xl border transition-all ${
                  style === s
                    ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-600'
                }`}
              >
                <div className="font-medium text-sm text-gray-100 mb-1">{STYLE_INFO[s].label}</div>
                <div className="text-xs text-gray-500 leading-relaxed">{STYLE_INFO[s].description}</div>
                {STYLE_INFO[s].extraFiles.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {STYLE_INFO[s].extraFiles.map((f) => (
                      <span key={f} className="text-xs bg-gray-800 text-amber-400 px-2 py-0.5 rounded">
                        + {f}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Mode visuel (dark/light) — pertinent pour full et audio_srt sans vidéo fournie */}
        {style !== 'simple' && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">Ambiance visuelle</label>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setVideoMode('dark')}
                className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border transition-all ${
                  videoMode === 'dark'
                    ? 'border-indigo-500 bg-indigo-500/10 ring-1 ring-indigo-500'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-600'
                }`}
              >
                <Moon size={16} className={videoMode === 'dark' ? 'text-indigo-400' : 'text-gray-500'} />
                <div className="text-left">
                  <div className={`text-sm font-medium ${videoMode === 'dark' ? 'text-indigo-300' : 'text-gray-300'}`}>Sombre</div>
                  <div className="text-xs text-gray-500">Prières du soir, ambiance contemplative</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setVideoMode('light')}
                className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border transition-all ${
                  videoMode === 'light'
                    ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-600'
                }`}
              >
                <Sun size={16} className={videoMode === 'light' ? 'text-amber-400' : 'text-gray-500'} />
                <div className="text-left">
                  <div className={`text-sm font-medium ${videoMode === 'light' ? 'text-amber-300' : 'text-gray-300'}`}>Clair</div>
                  <div className="text-xs text-gray-500">Prières du matin, ambiance lumineuse</div>
                </div>
              </button>
            </div>
          </div>
        )}

        {/* Fichiers supplémentaires conditionnels */}
        {style === 'simple' && (
          <FileUpload
            label="Vidéo de fond (MP4)"
            accept="video/mp4,video/*"
            file={bgVideo}
            onChange={setBgVideo}
            required
          />
        )}
        {style === 'audio_srt' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FileUpload
                label="Fichier audio (MP3 / WAV)"
                accept="audio/*"
                file={audioFile}
                onChange={setAudioFile}
                required
              />
              <FileUpload
                label="Fichier de sous-titres (SRT)"
                accept=".srt"
                file={srtFile}
                onChange={setSrtFile}
                required
              />
            </div>
            <FileUpload
              label="Vidéo de fond (MP4) — optionnelle"
              accept="video/mp4,video/*"
              file={bgVideo}
              onChange={setBgVideo}
            />
            {bgVideo && (
              <p className="text-xs text-amber-400/80 flex items-center gap-1.5">
                <Info size={12} />
                Format détecté automatiquement : portrait (9:16) → 3 mots/ligne · paysage (16:9) → 5 mots/ligne.
                Sans vidéo de fond, les clips de videos_db sont utilisés.
              </p>
            )}
          </div>
        )}

        {/* Script textarea */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300">Script vidéo</label>
          <div className="relative">
            <textarea
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              rows={10}
              placeholder={SCRIPT_PLACEHOLDER}
              className="w-full bg-gray-900 border border-gray-700 rounded-xl px-3 sm:px-4 py-3 text-sm text-gray-200
                         placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1
                         focus:ring-amber-500 resize-y font-mono leading-relaxed"
            />
          </div>
          <div className="flex items-start gap-2 text-xs text-gray-500">
            <Info size={13} className="mt-0.5 shrink-0" />
            <span>
              Format requis : commencez par <code className="text-amber-500">Titre: …</code> puis{' '}
              <code className="text-amber-500">Transcript:</code> suivi du texte.
              Les versets entre <code className="text-amber-500">«»</code> génèrent des overlays bibliques.
              Les phrases "Maintenant prions" insèrent une pause de 3 secondes.
            </span>
          </div>
        </div>

        {/* ── YouTube Upload ──────────────────────────────────────────── */}
        <div className="border border-gray-700 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-gray-900/60">
            <label className="flex items-center gap-3 cursor-pointer flex-1">
              <input
                type="checkbox"
                checked={ytAutoUpload}
                onChange={(e) => {
                  setYtAutoUpload(e.target.checked)
                  if (e.target.checked) setYtExpanded(true)
                }}
                className="accent-red-500 w-4 h-4 shrink-0"
              />
              <div className="flex items-center gap-2">
                <Youtube size={18} className="text-red-500" />
                <span className="text-sm font-medium text-gray-200">Uploader automatiquement sur YouTube à la fin du job</span>
              </div>
            </label>
            {ytAutoUpload && (
              <button
                type="button"
                onClick={() => setYtExpanded(!ytExpanded)}
                className="p-1 hover:bg-gray-700/50 rounded transition-colors"
              >
                {ytExpanded ? <ChevronUp size={16} className="text-gray-500" /> : <ChevronDown size={16} className="text-gray-500" />}
              </button>
            )}
          </div>

          {!ytAutoUpload && (
            <div className="px-4 py-2 border-t border-gray-700/50 bg-gray-950/30">
              <p className="text-xs text-gray-500">
                Sans auto-upload, vous pourrez télécharger la vidéo et l'uploader manuellement depuis la page de détails du job.
              </p>
            </div>
          )}

          {ytAutoUpload && ytExpanded && (
            <div className="p-4 space-y-5 border-t border-gray-700/50 bg-gray-950/30">
              {/* Auth status */}
              {ytAuthenticated === null ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2 size={14} className="animate-spin" />
                  Vérification de l'authentification YouTube…
                </div>
              ) : ytAuthenticated ? (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm text-green-400">
                    <CheckCircle size={14} />
                    Connecté à YouTube
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await revokeYoutubeToken()
                      setYtAuthenticated(false)
                      setPlaylists([])
                    }}
                    className="text-xs text-gray-500 hover:text-red-400 flex items-center gap-1 transition-colors"
                  >
                    <LogOut size={12} /> Déconnecter
                  </button>
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                  <button
                    type="button"
                    onClick={handleYtAuth}
                    disabled={ytAuthLoading}
                    className="flex items-center gap-2 bg-red-600 hover:bg-red-500 disabled:opacity-50
                               text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                  >
                    {ytAuthLoading ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
                    {ytAuthLoading ? 'En attente…' : 'Se connecter à YouTube'}
                  </button>
                  <span className="text-xs text-gray-500">
                    Requis pour l'upload automatique après génération.
                  </span>
                </div>
              )}

              <p className="text-xs text-gray-500 flex items-center gap-1.5">
                <Info size={12} className="shrink-0" />
                Remplissez le titre YouTube pour activer l'auto-upload. La vidéo avec overlays sera uploadée par défaut.
              </p>

              {/* Title */}
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-gray-300">Titre YouTube</label>
                <input
                  type="text"
                  value={ytForm.title}
                  onChange={(e) => setYtForm({ ...ytForm, title: e.target.value })}
                  placeholder="ex: Prière puissante pour la guérison 🙏"
                  maxLength={100}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                             placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
                <div className="text-right text-xs text-gray-600">{ytForm.title.length}/100</div>
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-gray-300">Description</label>
                <textarea
                  value={ytForm.description}
                  onChange={(e) => setYtForm({ ...ytForm, description: e.target.value })}
                  rows={4}
                  placeholder="Description de la vidéo…"
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                             placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1
                             focus:ring-amber-500 resize-y"
                />
              </div>

              {/* Tags */}
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-gray-300">Tags</label>
                <input
                  type="text"
                  value={ytForm.tags}
                  onChange={(e) => setYtForm({ ...ytForm, tags: e.target.value })}
                  placeholder="prière, bible, guérison, foi, Dieu"
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                             placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
                <p className="text-xs text-gray-600">Séparez les tags par des virgules.</p>
              </div>

              {/* Grid: Visibility + Category */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Visibility */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Visibilité</label>
                  <div className="space-y-1.5">
                    {(['private', 'unlisted', 'public'] as const).map((v) => (
                      <label key={v} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="yt_privacy"
                          value={v}
                          checked={ytForm.privacy === v}
                          onChange={() => setYtForm({ ...ytForm, privacy: v })}
                          className="accent-amber-500"
                        />
                        <span className="text-sm text-gray-300 capitalize">
                          {v === 'private' ? 'Private (review avant publication)' : v === 'unlisted' ? 'Unlisted' : 'Public'}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Category */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Catégorie</label>
                  <select
                    value={ytForm.categoryId}
                    onChange={(e) => setYtForm({ ...ytForm, categoryId: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                               focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                  >
                    {YT_CATEGORIES.map((c) => (
                      <option key={c.id} value={c.id}>{c.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Grid: Playlist + Thumbnail */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Playlist */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Playlist</label>
                  {ytAuthenticated && playlists.length > 0 ? (
                    <select
                      value={ytForm.playlistId}
                      onChange={(e) => setYtForm({ ...ytForm, playlistId: e.target.value })}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                                 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    >
                      <option value="">Aucune playlist</option>
                      {playlists.map((p) => (
                        <option key={p.id} value={p.id}>{p.title}</option>
                      ))}
                    </select>
                  ) : (
                    <p className="text-xs text-gray-600 py-2">
                      {ytAuthenticated ? 'Aucune playlist trouvée.' : 'Connectez-vous pour voir vos playlists.'}
                    </p>
                  )}
                </div>

                {/* Thumbnail */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Miniature</label>
                  <label className="flex items-center gap-2 p-2 border border-dashed border-gray-600 rounded-lg
                                    cursor-pointer hover:border-amber-500 transition-colors bg-gray-900 text-sm">
                    <Upload size={14} className="text-gray-500 shrink-0" />
                    <span className="text-gray-400 truncate">
                      {ytThumbnail ? ytThumbnail.name : 'Image .jpg/.png…'}
                    </span>
                    <input
                      type="file"
                      accept="image/jpeg,image/png"
                      className="hidden"
                      onChange={(e) => setYtThumbnail(e.target.files?.[0] ?? null)}
                    />
                  </label>
                </div>
              </div>

              {/* Grid: Language + Audio language */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Langue de la vidéo</label>
                  <select
                    value={ytForm.language}
                    onChange={(e) => setYtForm({ ...ytForm, language: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                               focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                    <option value="es">Español</option>
                    <option value="pt">Português</option>
                    <option value="de">Deutsch</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Langue audio</label>
                  <select
                    value={ytForm.language}
                    onChange={(e) => setYtForm({ ...ytForm, language: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                               focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="fr">Français</option>
                    <option value="en">English</option>
                    <option value="es">Español</option>
                    <option value="pt">Português</option>
                    <option value="de">Deutsch</option>
                  </select>
                  <p className="text-xs text-gray-600">Identique à la langue vidéo par défaut.</p>
                </div>
              </div>

              {/* Grid: License + Embedding + Made for kids */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Licence</label>
                  <select
                    value={ytForm.license}
                    onChange={(e) => setYtForm({ ...ytForm, license: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                               focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="youtube">Standard YouTube License</option>
                    <option value="creativeCommon">Creative Commons - Attribution</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Intégration</label>
                  <label className="flex items-center gap-2 py-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ytForm.embeddable}
                      onChange={(e) => setYtForm({ ...ytForm, embeddable: e.target.checked })}
                      className="accent-amber-500 w-4 h-4"
                    />
                    <span className="text-sm text-gray-300">Autoriser l'intégration</span>
                  </label>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">Contenu pour enfants</label>
                  <div className="flex items-center gap-3 py-2">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input type="radio" name="yt_kids" value="false" checked readOnly className="accent-amber-500" />
                      <span className="text-sm text-gray-300">Non</span>
                    </label>
                    <span className="text-xs text-gray-600">(fixe)</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full sm:w-auto flex items-center justify-center gap-2 bg-amber-500 hover:bg-amber-400
                     disabled:opacity-50 disabled:cursor-not-allowed text-gray-950 font-semibold
                     px-8 py-3 rounded-xl transition-colors"
        >
          <Play size={16} />
          {loading ? 'Lancement...' : ytAutoUpload && ytForm.title.trim() ? 'Lancer la génération + Upload YouTube' : 'Lancer la génération'}
        </button>
      </form>
    </div>
  )
}

function FileUpload({
  label,
  accept,
  file,
  onChange,
  required,
}: {
  label: string
  accept: string
  file: File | null
  onChange: (f: File | null) => void
  required?: boolean
}) {
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-300">
        {label} {required && <span className="text-amber-500">*</span>}
      </label>
      <label className="flex items-center gap-3 p-3 border border-dashed border-gray-600 rounded-xl
                        cursor-pointer hover:border-amber-500 transition-colors bg-gray-900">
        <Upload size={16} className="text-gray-500 shrink-0" />
        <span className="text-sm text-gray-400 truncate">
          {file ? file.name : 'Cliquer pour sélectionner…'}
        </span>
        <input
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        />
      </label>
    </div>
  )
}
