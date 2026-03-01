import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, Play, Info, Music, Video } from 'lucide-react'
import { createJob, getAssets, type JobStyle, type Assets } from '../api'

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
    description: 'Pas de TTS — vous fournissez l\'audio et les sous-titres. Idéal pour réutiliser un enregistrement.',
    extraFiles: ['Fichier audio (MP3/WAV)', 'Fichier de sous-titres (SRT)'],
  },
}

const SCRIPT_PLACEHOLDER = `Titre: Mon titre de vidéo

Transcript:
Votre texte ici. Les versets bibliques entre «guillemets français» seront détectés automatiquement.

Dans Psaume trente-quatre verset dix-huit : «L'Éternel est près de ceux qui ont le cœur brisé.»

Maintenant prions ensemble...`

export default function NewJob() {
  const navigate = useNavigate()
  const [style, setStyle] = useState<JobStyle>('full')
  const [scriptText, setScriptText] = useState('')
  const [bgVideo, setBgVideo] = useState<File | null>(null)
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [srtFile, setSrtFile] = useState<File | null>(null)
  const [assets, setAssets] = useState<Assets | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAssets().then(setAssets).catch(() => null)
  }, [])

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
      const result = await createJob(style, scriptText, {
        backgroundVideo: bgVideo ?? undefined,
        audioFile: audioFile ?? undefined,
        srtFile: srtFile ?? undefined,
      })
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
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1.5 text-gray-500">
            <Video size={14} />
            <span>{assets.videos_count} vidéo(s) dans videos_db</span>
          </div>
          <div className="flex items-center gap-1.5 text-gray-500">
            <Music size={14} />
            <span>{assets.songs_count} musique(s) disponible(s)</span>
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
        )}

        {/* Script textarea */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-300">Script vidéo</label>
          <div className="relative">
            <textarea
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              rows={14}
              placeholder={SCRIPT_PLACEHOLDER}
              className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200
                         placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1
                         focus:ring-amber-500 resize-none font-mono leading-relaxed"
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
          {loading ? 'Lancement...' : 'Lancer la génération'}
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
