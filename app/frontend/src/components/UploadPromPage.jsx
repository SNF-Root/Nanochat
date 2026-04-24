import { useEffect, useMemo, useRef, useState } from 'react'
import {
  UploadCloud,
  FolderUp,
  FileText,
  CheckCircle2,
  AlertTriangle,
  X,
} from 'lucide-react'

const UPLOAD_TARGETS = {
  prom: {
    label: 'PROM',
    badge: 'PROM forms',
    title: 'Upload PROM documents',
    boxLabel: 'PROM forms',
    extensions: ['.pdf', '.docx'],
    route: '/upload/prom',
    uploadButton: 'Upload PROMs',
    folderButton: 'Upload PROM Folder',
  },
  emails: {
    label: 'Emails',
    badge: 'Emails',
    title: 'Upload Email',
    boxLabel: 'Emails',
    extensions: ['.txt'],
    route: '/upload/emails',
    uploadButton: 'Upload Emails',
    folderButton: 'Upload Email Folder',
  },
}

const getExtension = (name) => {
  const lower = (name || '').toLowerCase()
  const dot = lower.lastIndexOf('.')
  return dot === -1 ? '' : lower.slice(dot)
}

const getDisplayPath = (file) => file?.webkitRelativePath || file?.name || ''

const resetUploadCounter = async () => {
  try {
    // await fetch('/upload/reset_counter', { method: 'POST' })
  } catch {
    // Counter reset failure should not block UI actions.
  }
}

const uploadFile = (file, path, route, onProgress) =>
  new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('path', path)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', route)

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percent = Math.max(
        1,
        Math.min(99, Math.round((event.loaded / event.total) * 100)),
      )
      onProgress(percent)
    }

    xhr.onerror = () => {
      reject(new Error('Network error while uploading file'))
    }

    xhr.onload = () => {
      let payload = null
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        payload = null
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject({
          statusCode: xhr.status,
          payload,
          message: `Upload failed (${xhr.status})`,
        })
        return
      }
      resolve(payload)
    }

    xhr.send(formData)
  })

const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
const TERMINAL_UPLOAD_STATUSES = new Set([
  'Complete',
  'Duplicate Already Exists',
  'Could Not Insert',
  'Could Not Upload',
])

const normalizeUploadStatusItems = (items, limit) => {
  const deduped = []
  const seen = new Set()

  for (let index = items.length - 1; index >= 0; index -= 1) {
    const raw = items[index]
    const item = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!item) continue

    const key = item.upload_id || item.filepath
    if (!key || seen.has(key)) continue
    seen.add(key)
    deduped.push(item)

    if (limit && deduped.length >= limit) break
  }

  return deduped.reverse()
}

function ConfirmUploadModal({
  isOpen,
  target,
  selectionKind,
  entries,
  onConfirm,
  onCancel,
  onRemoveEntry,
}) {
  if (!isOpen) return null

  const fileCount = entries.length

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/45 backdrop-blur-sm px-4 py-6">
      <div className="w-full max-w-5xl max-h-[88vh] overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-2xl shadow-slate-900/30">
        <div className="border-b border-slate-100 bg-gradient-to-r from-red-50 via-white to-slate-50 px-6 py-5 md:px-8 md:py-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-red-100 bg-red-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-red-700">
            Confirm Upload
          </div>
          <h3 className="mt-3 text-2xl font-semibold text-slate-900 md:text-3xl">
            Send {fileCount} {selectionKind === 'directory' ? 'directory items' : 'files'} to the {target.label} pipeline?
          </h3>
          <p className="mt-2 max-w-2xl text-sm text-slate-600 md:text-base">
            Nothing will be sent to the server until you confirm. Review the selection below, then either continue or cancel.
          </p>
        </div>

        <div className="grid gap-4 px-6 py-5 md:grid-cols-[15rem_1fr] md:px-8 md:py-6">
          <div className="flex h-full min-h-[22rem] flex-col rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Summary
            </div>
            <div className="mt-3 text-3xl font-semibold text-slate-900">
              {fileCount}
            </div>
            <div className="mt-1 text-sm text-slate-600">
              {selectionKind === 'directory' ? 'items from selected directory' : 'selected files'}
            </div>
            <div className="mt-4 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
               <span className="font-medium">{target.label}</span>
            </div>
            <div className="mt-auto flex flex-col gap-2 pt-8">
              <button
                onClick={onConfirm}
                disabled={entries.length === 0}
                className="rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Accept Upload
              </button>
              <button
                onClick={onCancel}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
              >
                Decline
              </button>
            </div>
          </div>

          <div className="min-h-0 rounded-2xl border border-slate-200 bg-white overflow-hidden">
            <div className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-900">
              Selection preview
            </div>
            <div className="h-[22rem] overflow-y-auto px-4 py-3">
              <ul className="space-y-2">
                {entries.map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2"
                  >
                    <div className="min-w-0 flex-1 text-sm text-slate-700">
                      {entry.path}
                    </div>
                    <button
                      onClick={() => onRemoveEntry(entry.id)}
                      className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-white text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
                      aria-label={`Remove ${entry.path}`}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
              {entries.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-500">
                  No files selected.
                </div>
              ) : null}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}

function UploadedFilesPanel({ uploaded, onClear }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden h-[16rem] lg:h-full min-h-0 flex flex-col">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-900">Uploaded</div>
          <div className="text-xs text-slate-500 mt-0.5">
            Completed filenames from the last uploads.
          </div>
        </div>
        {uploaded.length > 0 ? (
          <button
            onClick={onClear}
            className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs text-slate-700 hover:bg-slate-50 transition-colors"
          >
            Clear
          </button>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {uploaded.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-500">No uploads yet.</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {uploaded.map((u) => {
              const filename = u.path.split('/').pop() || u.path
              return (
                <li key={u.id} className="px-4 py-2.5">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <CheckCircle2 className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-slate-900 truncate">
                        {filename}
                      </div>
                      <div className="text-xs text-slate-500 truncate mt-0.5">
                        {u.path}
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

function UploadProgressModal({ isOpen, entries, onClose }) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-900/35 px-4 py-6 backdrop-blur-sm">
      <div className="w-full max-w-4xl overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-2xl shadow-slate-900/20">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-red-50/40 px-6 py-5 md:px-8">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
              Upload Progress
            </div>
            <h3 className="mt-3 text-2xl font-semibold text-slate-900">
              Worker processing status
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Latest status for each uploaded file.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900"
          >
            Close
          </button>
        </div>

        <div className="max-h-[65vh] overflow-y-auto px-6 py-5 md:px-8">
          {entries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-sm text-slate-500">
              Waiting for worker updates...
            </div>
          ) : (
            <div className="grid gap-3">
              {entries.map((entry) => {
                const isTerminal = TERMINAL_UPLOAD_STATUSES.has(entry.status)
                const isFailure = entry.status !== 'Complete' && isTerminal
                const filename = entry.filepath?.split('/').pop() || entry.upload_id

                return (
                  <div
                    key={entry.upload_id || entry.filepath}
                    className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4"
                  >
                    <div className="flex items-start gap-4">
                      <div
                        className={[
                          'mt-0.5 flex h-11 w-11 items-center justify-center rounded-2xl',
                          isFailure
                            ? 'bg-red-50 text-red-600'
                            : isTerminal
                              ? 'bg-emerald-50 text-emerald-600'
                              : 'bg-slate-100 text-slate-600',
                        ].join(' ')}
                      >
                        {isFailure ? (
                          <AlertTriangle className="h-5 w-5" />
                        ) : isTerminal ? (
                          <CheckCircle2 className="h-5 w-5" />
                        ) : (
                          <FileText className="h-5 w-5" />
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-slate-900">
                              {filename}
                            </div>
                            <div className="mt-1 truncate text-xs text-slate-500">
                              {entry.filepath}
                            </div>
                          </div>
                          <span
                            className={[
                              'shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium',
                              isFailure
                                ? 'border-red-100 bg-red-50 text-red-700'
                                : isTerminal
                                  ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
                                  : 'border-slate-200 bg-white text-slate-700',
                            ].join(' ')}
                          >
                            {entry.status}
                          </span>
                        </div>

                        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                          <span className="rounded-full bg-white px-2 py-1 uppercase tracking-wide text-slate-500">
                            {entry.kind}
                          </span>
                          <span className="truncate font-mono text-[11px] text-slate-400">
                            {entry.upload_id}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function UploadPromPage() {
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)
  const completionTimerRef = useRef(null)
  const progressPollRef = useRef(null)

  const [items, setItems] = useState([])
  const [uploaded, setUploaded] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState('')
  const [mode, setMode] = useState('idle') // 'idle' | 'queue'
  const [toasts, setToasts] = useState([])
  const [uploadType, setUploadType] = useState('prom')
  const [pendingConfirmation, setPendingConfirmation] = useState(null)
  const [isProgressOpen, setIsProgressOpen] = useState(false)
  const [progressEntries, setProgressEntries] = useState([])
  const [expectedProgressCount, setExpectedProgressCount] = useState(0)

  const target = UPLOAD_TARGETS[uploadType]

  const counts = useMemo(() => {
    let valid = 0
    let done = 0
    let uploading = 0
    let queued = 0
    for (const it of items) {
      valid += 1
      if (it.status === 'done') done += 1
      if (it.status === 'uploading') uploading += 1
      if (it.status === 'queued') queued += 1
    }
    return { valid, done, uploading, queued }
  }, [items])

  useEffect(() => {
    // resetUploadCounter()
  }, [])

  useEffect(() => {
    return () => {
      if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
      completionTimerRef.current = null
      if (progressPollRef.current) clearInterval(progressPollRef.current)
      progressPollRef.current = null
    }
  }, [])

  useEffect(() => {
    if (mode !== 'queue') return

    const toRegister = items.filter((it) => it.status === 'queued')
    if (toRegister.length === 0) return

    // Mark as uploading immediately to avoid duplicate requests on re-render.
    setItems((prev) =>
      prev.map((it) =>
        it.status === 'queued'
          ? { ...it, status: 'uploading', progress: 1, message: 'Uploading…' }
          : it,
      ),
    )

    toRegister.forEach(async (it) => {
      if (!it.file) {
        setItems((prev) =>
          prev.map((p) =>
            p.id === it.id
              ? { ...p, status: 'error', message: 'Missing file payload' }
              : p,
          ),
        )
        return
      }

      try {
        await uploadFile(it.file, it.path, target.route, (progress) => {
          setItems((prev) =>
            prev.map((p) =>
              p.id === it.id && p.status === 'uploading'
                ? { ...p, progress }
                : p,
            ),
          )
        })
        setItems((prev) =>
          prev.map((p) =>
            p.id === it.id
              ? {
                  ...p,
                  status: 'done',
                  progress: 100,
                  message: '',
                }
              : p,
          ),
        )
      } catch (e) {
        const rejectionReason =
          e?.payload?.status === 'Rejected'
            ? e.payload.reason || 'Upload rejected'
            : null
        setItems((prev) =>
          prev.map((p) =>
            p.id === it.id
              ? {
                  ...p,
                  status: rejectionReason ? 'rejected' : 'error',
                  progress: 100,
                  message: rejectionReason || 'Upload failed',
                }
              : p,
          ),
        )
      }
    })
  }, [items, mode, target.route])

  useEffect(() => {
    if (mode !== 'queue') return

    const hasActive = counts.uploading > 0 || counts.queued > 0
    const hasAny = items.length > 0
    if (!hasAny || hasActive) return

    const completed = items.filter((it) => it.status === 'done').map((it) => it.path)
    const hasRejectedOrErrored = items.some(
      (it) => it.status === 'rejected' || it.status === 'error',
    )
    if (completed.length === 0) {
      if (!hasRejectedOrErrored) {
        setItems([])
      }
      setMode('idle')
      return
    }

    if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
    completionTimerRef.current = setTimeout(() => {
      setUploaded((prev) => {
        return [
          ...completed.map((path) => ({ id: makeId(), path, at: Date.now() })),
          ...prev,
        ]
      })
      setExpectedProgressCount(completed.length)
      setProgressEntries([])
      setIsProgressOpen(true)
      setItems([])
      setMode('idle')
      completionTimerRef.current = null
    }, 650)

    return () => {
      if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
      completionTimerRef.current = null
    }
  }, [counts.queued, counts.uploading, items, mode])

  useEffect(() => {
    if (!isProgressOpen) {
      if (progressPollRef.current) clearInterval(progressPollRef.current)
      progressPollRef.current = null
      return
    }

    const poll = async () => {
      try {
        const response = await fetch('/upload/get', {
          method: 'GET',
          credentials: 'include',
        })

        if (!response.ok) {
          throw new Error(`Upload status request failed: ${response.status}`)
        }

        const data = await response.json()
        const nextEntries = normalizeUploadStatusItems(data || [], expectedProgressCount)
        setProgressEntries(nextEntries)

        if (
          nextEntries.length > 0 &&
          nextEntries.every((entry) => TERMINAL_UPLOAD_STATUSES.has(entry.status))
        ) {
          if (progressPollRef.current) clearInterval(progressPollRef.current)
          progressPollRef.current = null
        }
      } catch (error) {
        console.error('Upload status request error:', error)
      }
    }

    poll()
    progressPollRef.current = setInterval(poll, 50)

    return () => {
      if (progressPollRef.current) clearInterval(progressPollRef.current)
      progressPollRef.current = null
    }
  }, [expectedProgressCount, isProgressOpen])

  const addFileEntries = async (entries) => {
    setError('')
    if (completionTimerRef.current) {
      clearTimeout(completionTimerRef.current)
      completionTimerRef.current = null
    }

    const next = []
    let hasValid = false
    const resetBatch =
      mode === 'queue' &&
      counts.uploading === 0 &&
      counts.queued === 0

    for (const { file, path } of entries) {
      if (!path) continue
      const ext = getExtension(path)
      const isValid = target.extensions.includes(ext) && !!file
      if (!isValid) {
        const filename = path.split('/').pop() || path
        const toastId = makeId()
        setToasts((prev) => [
          ...prev,
          { id: toastId, message: `Removed invalid format: ${filename}` },
        ])
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== toastId))
        }, 3500)
        continue
      }

      hasValid = true
      next.push({
        id: makeId(),
        file,
        path,
        filename: path.split('/').pop() || path,
        ext,
        status: 'queued',
        progress: 0,
        message: '',
      })
    }

    if (next.length === 0) return

    setItems((prev) => {
      const existing = resetBatch ? new Set() : new Set(prev.map((p) => p.path))
      const inserted = next.filter((n) => !existing.has(n.path))
      return resetBatch ? inserted : [...inserted, ...prev]
    })

    if (hasValid) setMode('queue')
  }

  const stageEntriesForConfirmation = (entries, selectionKind) => {
    const staged = entries
      .filter((entry) => entry.path)
      .map((entry) => ({
        id: makeId(),
        ...entry,
      }))

    if (staged.length === 0) return

    setPendingConfirmation({
      selectionKind,
      entries: staged,
    })
  }

  const confirmPendingUpload = async () => {
    if (!pendingConfirmation) return
    const entries = pendingConfirmation.entries.map(({ id, file, path }) => ({
      file,
      path,
    }))
    setPendingConfirmation(null)
    await addFileEntries(entries)
  }

  const cancelPendingUpload = () => {
    setPendingConfirmation(null)
  }

  const removePendingEntry = (entryId) => {
    setPendingConfirmation((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        entries: prev.entries.filter((entry) => entry.id !== entryId),
      }
    })
  }

  const addFiles = (files) => {
    const entries = files
      .map((file) => ({ file, path: getDisplayPath(file) }))
      .filter((it) => it.path)
    const selectionKind = entries.some((entry) => entry.path.includes('/'))
      ? 'directory'
      : 'files'
    return stageEntriesForConfirmation(entries, selectionKind)
  }

  const onPickFiles = (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    addFiles(files)
  }

  const onDrop = async (e) => {
    e.preventDefault()
    setIsDragging(false)
    setError('')

    const dt = e.dataTransfer
    if (!dt) return

    const items = Array.from(dt.items || [])
    const canUseEntries = items.some((i) => i.webkitGetAsEntry)

    if (!canUseEntries) {
      addFiles(Array.from(dt.files || []))
      return
    }

    const collectedEntries = []

    const walkEntry = (entry, prefix = '') =>
      new Promise((resolve) => {
        if (!entry) return resolve()
        if (entry.isFile) {
          entry.file((file) => {
            collectedEntries.push({ file, path: `${prefix}${file.name}` })
            resolve()
          })
          return
        }
        if (entry.isDirectory) {
          const reader = entry.createReader()
          const readAll = async () => {
            reader.readEntries(async (entries) => {
              if (!entries || entries.length === 0) return resolve()
              for (const child of entries) {
                await walkEntry(child, `${prefix}${entry.name}/`)
              }
              readAll()
            })
          }
          readAll()
          return
        }
        resolve()
      })

    for (const it of items) {
      const entry = it.webkitGetAsEntry?.()
      if (!entry) continue
      await walkEntry(entry, '')
    }

    if (collectedEntries.length === 0) {
      setError(
        `Nothing to upload. Try dropping a folder with ${target.extensions.join(
          '/',
        )} files.`,
      )
      return
    }

    const selectionKind = collectedEntries.some((entry) => entry.path.includes('/'))
      ? 'directory'
      : 'files'
    stageEntriesForConfirmation(collectedEntries, selectionKind)
  }

  const clearAll = () => {
    // resetUploadCounter()
    if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
    completionTimerRef.current = null
    setItems([])
    setPendingConfirmation(null)
    setMode('idle')
  }

  const removeItem = (id) => {
    setItems((prev) => prev.filter((p) => p.id !== id))
  }

  const onChangeUploadType = async (nextType) => {
    setUploadType(nextType)
    setError('')
    setItems([])
    setUploaded([])
    setMode('idle')
    setPendingConfirmation(null)
    setIsProgressOpen(false)
    setProgressEntries([])
    setExpectedProgressCount(0)
    // await resetUploadCounter()
  }

  return (
    <div className="w-full max-w-6xl mx-auto h-full min-h-0 flex flex-col overflow-hidden">
      <UploadProgressModal
        isOpen={isProgressOpen}
        entries={progressEntries}
        onClose={() => setIsProgressOpen(false)}
      />

      <div className="flex items-start justify-between gap-4 mb-2 flex-none">
        <div>
          <div className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-red-700 bg-red-50 border border-red-100 px-3 py-1 rounded-full">
            {target.badge}
          </div>
          <h1 className="text-xl md:text-2xl font-semibold text-slate-900 mt-1.5">
            {target.title}
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            Accepted extension{target.extensions.length > 1 ? 's' : ''}:{' '}
            {target.extensions.map((ext) => (
              <span key={ext} className="font-medium mr-1.5">
                {ext}
              </span>
            ))}
            Folder upload is supported.
          </p>
        </div>

        <div className="shrink-0">
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Upload Type
          </label>
          <select
            value={uploadType}
            onChange={(e) => onChangeUploadType(e.target.value)}
            className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm text-slate-700"
          >
            <option value="prom">PROM</option>
            <option value="emails">Emails</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4 flex-1 min-h-0 h-full overflow-hidden">
        <div className="order-2 lg:order-2 lg:col-span-1 h-full min-h-0">
          <UploadedFilesPanel
            uploaded={uploaded}
            onClear={() => {
              // resetUploadCounter()
              setUploaded([])
            }}
          />
        </div>

        <div className="order-1 lg:order-1 lg:col-span-2 h-full min-h-0">
          <div
            className={[
              'relative overflow-hidden rounded-3xl border bg-white shadow-sm h-full min-h-0',
              isDragging ? 'border-red-300 ring-4 ring-red-100' : 'border-slate-200',
            ].join(' ')}
          >
            <ConfirmUploadModal
              isOpen={pendingConfirmation !== null}
              target={target}
              selectionKind={pendingConfirmation?.selectionKind}
              entries={pendingConfirmation?.entries || []}
              onConfirm={confirmPendingUpload}
              onCancel={cancelPendingUpload}
              onRemoveEntry={removePendingEntry}
            />
            <div className="absolute inset-0 bg-gradient-to-br from-red-50/40 via-white to-slate-50/70" />

            {/* Idle (dropzone) */}
            <div
              className={[
                'relative p-5 md:p-6 transition-all duration-300 h-full min-h-0 flex flex-col',
                mode === 'idle'
                  ? 'opacity-100 translate-y-0'
                  : 'opacity-0 -translate-y-2 pointer-events-none absolute inset-0',
              ].join(' ')}
            >
              <div
                onDragEnter={(e) => {
                  e.preventDefault()
                  setIsDragging(true)
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  setIsDragging(true)
                }}
                onDragLeave={(e) => {
                  e.preventDefault()
                  setIsDragging(false)
                }}
                onDrop={onDrop}
                className="flex-1 min-h-0 rounded-2xl border-2 border-dashed border-slate-200 bg-white/60 backdrop-blur-sm p-6 md:p-8 text-center flex flex-col items-center justify-center"
              >
                <div className="mx-auto w-12 h-12 rounded-2xl bg-gradient-to-br from-red-500 to-red-600 shadow-lg shadow-red-200 flex items-center justify-center mb-4">
                  <UploadCloud className="w-6 h-6 text-white" />
                </div>

                <h2 className="text-xl font-semibold text-slate-900">
                  Drag and drop files or a folder
                </h2>
                <p className="text-sm text-slate-600 mt-1.5">
                  This upload box is for{' '}
                  <span className="font-medium">{target.boxLabel}</span> only.
                  Accepted:{' '}
                  {target.extensions.map((ext) => (
                    <span key={ext} className="font-medium mr-1.5">
                      {ext}
                    </span>
                  ))}
                </p>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-2 mt-5">
                  <button
                    onClick={() => {
                      fileInputRef.current?.click()
                    }}
                    className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-red-600 text-white hover:bg-red-700 transition-colors inline-flex items-center justify-center gap-2"
                  >
                    <FileText className="w-4 h-4" />
                    {target.uploadButton}
                  </button>
                  <button
                    onClick={() => folderInputRef.current?.click()}
                    className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors inline-flex items-center justify-center gap-2"
                  >
                    <FolderUp className="w-4 h-4" />
                    {target.folderButton}
                  </button>
                </div>

                {error ? (
                  <div className="mt-5 text-sm text-red-700 bg-red-50 border border-red-100 rounded-xl px-4 py-3">
                    {error}
                  </div>
                ) : null}

                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={target.extensions.join(',')}
                  className="hidden"
                  onChange={onPickFiles}
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={onPickFiles}
                  {...{ webkitdirectory: '' }}
                />
              </div>

              <div className="mt-3 text-xs text-slate-500">
                Tip: dropping folders works best in Chromium-based browsers.
              </div>
            </div>

            {/* Queue (replaces dropzone while uploading) */}
            <div
              className={[
                'relative transition-all duration-300 h-full min-h-0 flex flex-col',
                mode === 'queue'
                  ? 'opacity-100 translate-y-0'
                  : 'opacity-0 translate-y-2 pointer-events-none absolute inset-0',
              ].join(' ')}
            >
              <div className="px-4 py-3 border-b border-slate-100 flex items-start justify-between bg-white/50 backdrop-blur-sm">
                  <div>
                  <div className="text-lg font-semibold text-slate-900">Upload queue</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    Uploading files to the server.
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-sm text-slate-500 tabular-nums">
                    {counts.done}/{counts.valid} completed
                  </div>
                  <button
                    onClick={clearAll}
                    className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-auto bg-white/30">
                {items.length === 0 ? (
                  <div className="px-6 py-10 text-sm text-slate-500">
                    Preparing upload…
                  </div>
                ) : (
                  <ul className="divide-y divide-slate-100">
                  {items.map((it) => {
                    const isDone = it.status === 'done'
                    const isRejected = it.status === 'rejected'
                    const isError = it.status === 'error'
                    const isFailure = isRejected || isError
                    const statusLabel = isDone
                      ? 'Completed'
                      : isRejected
                        ? 'Rejected'
                      : it.status === 'uploading'
                        ? 'Uploading'
                        : it.status === 'queued'
                          ? 'Queued'
                          : isError
                              ? 'Error'
                              : it.status

                      return (
                        <li key={it.id} className="px-4 py-2.5">
                          <div className="flex items-start gap-3">
                            <div
                              className={[
                                'mt-0.5 w-10 h-10 rounded-2xl flex items-center justify-center',
                                isDone
                                  ? 'bg-emerald-50 text-emerald-600'
                                  : isFailure
                                    ? 'bg-red-50 text-red-600'
                                    : 'bg-slate-50 text-slate-600',
                              ].join(' ')}
                            >
                              {isDone ? (
                                <CheckCircle2 className="w-5 h-5" />
                              ) : isFailure ? (
                                <AlertTriangle className="w-5 h-5" />
                              ) : (
                                <FileText className="w-5 h-5" />
                              )}
                            </div>

                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="text-sm font-medium text-slate-900 truncate">
                                    {it.filename}
                                  </div>
                                  <div className="text-xs text-slate-500 truncate mt-0.5">
                                    {it.path}
                                  </div>
                                </div>

                                <div className="flex items-center gap-3">
                                  <span
                                    className={[
                                      'text-xs px-2.5 py-1 rounded-full border',
                                      isDone
                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                                        : isFailure
                                          ? 'bg-red-50 text-red-700 border-red-100'
                                          : 'bg-slate-50 text-slate-700 border-slate-200',
                                    ].join(' ')}
                                  >
                                    {statusLabel}
                                  </span>
                                  <button
                                    onClick={() => removeItem(it.id)}
                                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
                                    aria-label={`Remove ${it.filename}`}
                                  >
                                    <X className="w-4 h-4" />
                                  </button>
                                </div>
                              </div>

                              <div className="mt-3">
                                <div className="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden">
                                  <div
                                    className={[
                                      'h-full rounded-full transition-[width] duration-200',
                                      isDone
                                        ? 'bg-emerald-500'
                                        : isFailure
                                          ? 'bg-red-400'
                                          : 'bg-gradient-to-r from-red-500 via-red-500 to-red-600',
                                    ].join(' ')}
                                    style={{
                                      width: `${isFailure ? 100 : it.progress}%`,
                                    }}
                                  />
                                </div>
                                <div className="flex items-center justify-between mt-1.5 text-xs text-slate-500">
                                  <div
                                    className={[
                                      'truncate',
                                      isRejected ? 'text-red-700' : '',
                                    ].join(' ')}
                                  >
                                    {it.message ? it.message : ' '}
                                  </div>
                                  <div className="tabular-nums">
                                    {isFailure ? '—' : `${it.progress}%`}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="fixed top-20 right-4 z-50 flex flex-col gap-2 w-[min(92vw,22rem)] pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto rounded-xl border border-red-200 bg-white shadow-lg px-3 py-2 text-sm text-red-700"
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  )
}
