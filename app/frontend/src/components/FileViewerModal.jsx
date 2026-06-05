import { useEffect, useMemo, useState } from 'react'
import mammoth from 'mammoth/mammoth.browser'

function getFileExtension(fileName) {
  const idx = fileName.lastIndexOf('.')
  if (idx === -1) return ''
  return fileName.slice(idx + 1).toLowerCase()
}

function FileViewerModal({ title, files, fileUrl, fileName, onClose }) {
  const normalizedFiles = useMemo(() => {
    if (Array.isArray(files) && files.length) return files
    if (fileUrl && fileName) return [{ key: fileName, label: fileName, fileUrl, fileName }]
    return []
  }, [files, fileUrl, fileName])

  const [activeKey, setActiveKey] = useState(() => normalizedFiles[0]?.key || '')
  const activeFile = useMemo(() => {
    if (!normalizedFiles.length) return null
    const found = normalizedFiles.find((f) => f.key === activeKey)
    return found || normalizedFiles[0]
  }, [activeKey, normalizedFiles])

  useEffect(() => {
    // Keep selection valid when the file set changes.
    if (!normalizedFiles.length) {
      setActiveKey('')
      return
    }
    if (!activeKey || !normalizedFiles.some((f) => f.key === activeKey)) {
      setActiveKey(normalizedFiles[0].key)
    }
  }, [activeKey, normalizedFiles])

  const activeFileName = activeFile?.fileName || ''
  const activeFileUrl = activeFile?.fileUrl || ''
  const extension = useMemo(() => getFileExtension(activeFileName), [activeFileName])
  const [docxHtml, setDocxHtml] = useState('')
  const [docxError, setDocxError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false

    if (extension !== 'docx') {
      setDocxHtml('')
      setDocxError('')
      return () => {
        cancelled = true
      }
    }

    const run = async () => {
      setIsLoading(true)
      setDocxError('')
      setDocxHtml('')

      try {
        const response = await fetch(activeFileUrl, { method: 'GET', credentials: 'include' })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const arrayBuffer = await response.arrayBuffer()
        const result = await mammoth.convertToHtml({ arrayBuffer })
        if (cancelled) return
        setDocxHtml(result.value || '')
      } catch (error) {
        if (cancelled) return
        setDocxError(error instanceof Error ? error.message : 'Failed to load document')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [extension, activeFileUrl])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 px-4 py-6 backdrop-blur-[10px]">
      <div className="w-full max-w-4xl rounded-[24px] border border-[#d9e2ef] bg-white/95 shadow-[0_24px_60px_rgba(44,62,89,0.16)]">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="text-sm font-semibold uppercase tracking-[0.14em] text-[#556987]">{title}</div>
          <button
            type="button"
            aria-label={`Close ${title}`}
            onClick={onClose}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
          >
            X
          </button>
        </div>

        <div className="h-[min(76vh,860px)] overflow-hidden p-5">
          {normalizedFiles.length > 1 ? (
            <div className="mb-4 flex flex-wrap gap-2">
              {normalizedFiles.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setActiveKey(f.key)}
                  className={[
                    'max-w-full truncate rounded-full border px-3 py-1 text-xs font-semibold transition-colors',
                    f.key === (activeFile?.key || '')
                      ? 'border-slate-300 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                  ].join(' ')}
                  title={f.label}
                >
                  {f.label}
                </button>
              ))}
            </div>
          ) : null}

          {extension === 'pdf' ? (
            <div className="h-full overflow-hidden rounded-[20px] border border-slate-200 bg-slate-50">
              <iframe title={activeFileName} src={activeFileUrl} className="h-full w-full" />
            </div>
          ) : extension === 'docx' ? (
            <div className="h-full overflow-y-auto rounded-[20px] border border-slate-200 bg-white p-6 text-slate-800">
              {isLoading ? (
                <div className="text-sm text-slate-500">Loading document…</div>
              ) : docxError ? (
                <div className="text-sm text-red-700">
                  Could not render DOCX ({docxError}).{' '}
                  <a className="underline" href={activeFileUrl} target="_blank" rel="noreferrer">
                    Open directly
                  </a>
                  .
                </div>
              ) : docxHtml ? (
                // Mammoth outputs HTML; we render it as-is inside the modal.
                <div className="max-w-none leading-7" dangerouslySetInnerHTML={{ __html: docxHtml }} />
              ) : (
                <div className="text-sm text-slate-500">
                  No content to display.{' '}
                  <a className="underline" href={activeFileUrl} target="_blank" rel="noreferrer">
                    Open directly
                  </a>
                  .
                </div>
              )}
            </div>
          ) : (
            <div className="h-full overflow-y-auto rounded-[20px] border border-slate-200 bg-white p-6">
              <p className="text-sm text-slate-700">
                Preview not supported for{' '}
                <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">{extension || 'unknown'}</code>.
              </p>
              <p className="mt-3 text-sm text-slate-700">
                <a className="underline" href={activeFileUrl} target="_blank" rel="noreferrer">
                  Open directly
                </a>
                .
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default FileViewerModal
