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
    await fetch('/upload/reset_counter', { method: 'POST' })
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
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`Upload failed (${xhr.status})`))
        return
      }
      let payload = null
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        payload = null
      }
      resolve(payload)
    }

    xhr.send(formData)
  })

const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

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

export default function UploadPromPage() {
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)
  const completionTimerRef = useRef(null)

  const [items, setItems] = useState([])
  const [uploaded, setUploaded] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState('')
  const [mode, setMode] = useState('idle') // 'idle' | 'queue'
  const [toasts, setToasts] = useState([])
  const [uploadType, setUploadType] = useState('prom')

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
    resetUploadCounter()
  }, [])

  useEffect(() => {
    return () => {
      if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
      completionTimerRef.current = null
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
        setItems((prev) =>
          prev.map((p) =>
            p.id === it.id
              ? {
                  ...p,
                  status: 'error',
                  message: 'Upload failed',
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
    if (completed.length === 0) {
      setItems([])
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
      setItems([])
      setMode('idle')
      completionTimerRef.current = null
    }, 650)

    return () => {
      if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
      completionTimerRef.current = null
    }
  }, [counts.queued, counts.uploading, items, mode])

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

  const addFiles = (files) => {
    const entries = files
      .map((file) => ({ file, path: getDisplayPath(file) }))
      .filter((it) => it.path)
    return addFileEntries(entries)
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

    addFileEntries(collectedEntries)
  }

  const clearAll = () => {
    resetUploadCounter()
    if (completionTimerRef.current) clearTimeout(completionTimerRef.current)
    completionTimerRef.current = null
    setItems([])
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
    await resetUploadCounter()
  }

  return (
    <div className="w-full max-w-6xl mx-auto h-full min-h-0 flex flex-col overflow-hidden">
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
              resetUploadCounter()
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
                    onClick={async () => {
                      await resetUploadCounter()
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
                    const isError = it.status === 'error'
                    const statusLabel = isDone
                      ? 'Completed'
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
                                  : isError
                                    ? 'bg-red-50 text-red-600'
                                    : 'bg-slate-50 text-slate-600',
                              ].join(' ')}
                            >
                              {isDone ? (
                                <CheckCircle2 className="w-5 h-5" />
                              ) : isError ? (
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
                                        : isError
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
                                        : isError
                                          ? 'bg-red-400'
                                          : 'bg-gradient-to-r from-red-500 via-red-500 to-red-600',
                                    ].join(' ')}
                                    style={{
                                      width: `${isError ? 100 : it.progress}%`,
                                    }}
                                  />
                                </div>
                                <div className="flex items-center justify-between mt-1.5 text-xs text-slate-500">
                                  <div className="truncate">
                                    {it.message ? it.message : ' '}
                                  </div>
                                  <div className="tabular-nums">
                                    {isError ? '—' : `${it.progress}%`}
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
