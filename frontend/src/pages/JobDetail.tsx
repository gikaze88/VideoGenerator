import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Download, Loader2, CheckCircle, XCircle, Clock, Terminal
} from 'lucide-react'
import {
  getJob, getJobLogs, getJobFiles, getDownloadUrl, formatDate, formatDuration,
  STATUS_LABELS, STATUS_COLORS, type Job, type JobStatus,
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
      <div className="flex items-center gap-3">
        <Link to="/history" className="text-gray-500 hover:text-gray-300 transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-100">
            {job.title || 'Génération en cours…'}
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Style : <span className="text-gray-400">{job.style}</span>
            {' · '}ID : <span className="font-mono text-gray-600">{job.id.slice(0, 8)}…</span>
          </p>
        </div>
        <span className={`text-xs font-medium px-3 py-1 rounded-full flex items-center gap-1.5 ${STATUS_COLORS[job.status]}`}>
          <StatusIcon status={job.status} />
          {STATUS_LABELS[job.status]}
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
        <div className="bg-green-900/20 border border-green-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-300 font-medium">Vidéo prête !</p>
              <p className="text-green-500 text-sm mt-0.5">
                Durée totale : {formatDuration(job.created_at, job.completed_at)}
              </p>
            </div>
          </div>
          {outputFiles.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {outputFiles.map((filename) => {
                const isOverlay = filename.includes('overlay')
                const label = isOverlay ? 'Avec versets bibliques' : 'Version standard'
                return (
                  <a
                    key={filename}
                    href={getDownloadUrl(job.id, filename)}
                    download={filename}
                    className={`flex items-center gap-2 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm ${
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
              className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white
                         font-semibold px-5 py-2.5 rounded-xl transition-colors w-fit"
            >
              <Download size={16} />
              Télécharger
            </a>
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
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 overflow-y-auto font-mono text-xs text-gray-400 leading-relaxed">
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
