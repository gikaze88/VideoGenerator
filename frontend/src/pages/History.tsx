import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Loader2, Trash2, Download, Eye, Film, RefreshCw
} from 'lucide-react'
import {
  listJobs, deleteJob, getDownloadUrl, formatDate, formatDuration,
  STATUS_LABELS, STATUS_COLORS, type Job,
} from '../api'

export default function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      setJobs(await listJobs())
    } catch {
      /* silence */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleDelete(jobId: string) {
    if (!confirm('Supprimer ce job et ses fichiers ?')) return
    setDeletingId(jobId)
    try {
      await deleteJob(jobId)
      setJobs((prev) => prev.filter((j) => j.id !== jobId))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Erreur lors de la suppression')
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 size={28} className="animate-spin text-gray-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Historique</h1>
          <p className="text-gray-400 mt-1">{jobs.length} génération{jobs.length > 1 ? 's' : ''}</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 px-3 py-2
                     rounded-lg hover:bg-gray-800 transition-colors"
        >
          <RefreshCw size={14} />
          Actualiser
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <Film size={40} className="mx-auto text-gray-700" />
          <p className="text-gray-500">Aucune génération pour l'instant.</p>
          <Link
            to="/"
            className="inline-block text-sm text-amber-400 hover:text-amber-300 hover:underline"
          >
            Créer ma première vidéo →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onDelete={handleDelete}
              deleting={deletingId === job.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function JobCard({
  job,
  onDelete,
  deleting,
}: {
  job: Job
  onDelete: (id: string) => void
  deleting: boolean
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-4
                    hover:border-gray-700 transition-colors">
      {/* Status dot */}
      <div className={`w-2 h-2 rounded-full shrink-0 ${
        job.status === 'completed' ? 'bg-green-500' :
        job.status === 'running' ? 'bg-blue-400 animate-pulse' :
        job.status === 'failed' ? 'bg-red-500' :
        'bg-gray-600'
      }`} />

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-gray-200 truncate">
            {job.title || 'Sans titre'}
          </p>
          <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${STATUS_COLORS[job.status]}`}>
            {STATUS_LABELS[job.status]}
          </span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5 flex gap-3">
          <span>Style : <span className="text-gray-400">{job.style}</span></span>
          <span>{formatDate(job.created_at)}</span>
          {job.status === 'completed' && (
            <span>Durée : {formatDuration(job.created_at, job.completed_at)}</span>
          )}
        </div>
        {job.status === 'failed' && job.error_message && (
          <p className="text-xs text-red-400 mt-1 truncate">{job.error_message}</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <Link
          to={`/jobs/${job.id}`}
          className="p-2 text-gray-500 hover:text-gray-200 hover:bg-gray-800 rounded-lg transition-colors"
          title="Voir les détails"
        >
          <Eye size={16} />
        </Link>

        {job.status === 'completed' && (
          <a
            href={getDownloadUrl(job.id)}
            download
            className="p-2 text-gray-500 hover:text-green-400 hover:bg-gray-800 rounded-lg transition-colors"
            title="Télécharger la vidéo"
          >
            <Download size={16} />
          </a>
        )}

        {job.status !== 'running' && (
          <button
            onClick={() => onDelete(job.id)}
            disabled={deleting}
            className="p-2 text-gray-600 hover:text-red-400 hover:bg-gray-800 rounded-lg
                       transition-colors disabled:opacity-40"
            title="Supprimer"
          >
            {deleting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Trash2 size={16} />
            )}
          </button>
        )}
      </div>
    </div>
  )
}
