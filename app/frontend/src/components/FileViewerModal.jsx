import { useEffect, useMemo, useRef, useState } from 'react'
import { renderAsync } from 'docx-preview'
import mammoth from 'mammoth/mammoth.browser'

function getFileExtension(fileName) {
  const idx = fileName.lastIndexOf('.')
  if (idx === -1) return ''
  return fileName.slice(idx + 1).toLowerCase()
}

function getArrayBufferKind(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer.slice(0, 8))
  const signature = Array.from(bytes).map((byte) => String.fromCharCode(byte)).join('')
  if (signature.startsWith('%PDF')) return 'pdf'
  if (signature.startsWith('PK')) return 'docx'
  return 'unknown'
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
  const docxContainerRef = useRef(null)
  const [docxHtml, setDocxHtml] = useState('')
  const [docxError, setDocxError] = useState('')
  const [docxPreviewReady, setDocxPreviewReady] = useState(false)
  const [fallbackText, setFallbackText] = useState('')
  const [detectedKind, setDetectedKind] = useState('')
  const [objectUrl, setObjectUrl] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    let nextObjectUrl = ''

    setDocxHtml('')
    setDocxError('')
    setDocxPreviewReady(false)
    setFallbackText('')
    setDetectedKind('')
    setObjectUrl('')
    if (docxContainerRef.current) {
      docxContainerRef.current.innerHTML = ''
    }

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
        const kind = getArrayBufferKind(arrayBuffer)
        if (cancelled) return
        setDetectedKind(kind)

        if (kind === 'pdf') {
          nextObjectUrl = URL.createObjectURL(new Blob([arrayBuffer], { type: 'application/pdf' }))
          setObjectUrl(nextObjectUrl)
          return
        }

        if (kind !== 'docx') {
          const text = new TextDecoder('utf-8', { fatal: false }).decode(arrayBuffer)
          setFallbackText(text.slice(0, 20000))
          setDocxError('This file is not a valid DOCX package.')
          return
        }

        if (!docxContainerRef.current) {
          throw new Error('Document preview container was not available.')
        }

        try {
          docxContainerRef.current.innerHTML = ''
          await renderAsync(arrayBuffer, docxContainerRef.current, null, {
            className: 'snf-docx-preview',
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            ignoreFonts: false,
            breakPages: true,
            renderHeaders: true,
            renderFooters: true,
          })
          if (cancelled) return
          setDocxPreviewReady(true)
          return
        } catch (previewError) {
          console.warn('[DOCX_PREVIEW] Falling back to Mammoth renderer.', previewError)
        }

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
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl)
    }
  }, [extension, activeFileUrl])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(43,38,32,0.38)] px-4 py-6 backdrop-blur-[8px]">
      <div className="w-full max-w-5xl rounded-[1.1rem] border border-[rgba(43,38,32,0.18)] bg-[rgba(245,241,232,0.96)] shadow-[0_28px_80px_rgba(43,38,32,0.28)]">
        <div className="flex items-center justify-between border-b border-[rgba(43,38,32,0.14)] px-6 py-5">
          <div className="font-['IBM_Plex_Mono'] text-[0.82rem] font-semibold uppercase tracking-[0.24em] text-[rgba(43,38,32,0.68)]">{title}</div>
          <button
            type="button"
            aria-label={`Close ${title}`}
            onClick={onClose}
            className="flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.42)] font-['IBM_Plex_Mono'] text-sm font-semibold text-[rgba(43,38,32,0.72)] transition-colors hover:bg-[rgba(255,255,255,0.72)]"
          >
            X
          </button>
        </div>

        <div className="h-[min(76vh,860px)] overflow-hidden p-6">
          {normalizedFiles.length > 1 ? (
            <div className="mb-4 flex flex-wrap gap-2">
              {normalizedFiles.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setActiveKey(f.key)}
                  className={[
                    'max-w-full truncate rounded-[0.35rem] border px-3 py-1 font-[IBM_Plex_Mono] text-xs font-semibold uppercase tracking-[0.1em] transition-colors',
                    f.key === (activeFile?.key || '')
                      ? 'border-[var(--snf-ink)] bg-[var(--snf-ink)] text-[rgba(245,241,232,0.95)]'
                      : 'border-[rgba(43,38,32,0.16)] bg-[rgba(255,255,255,0.4)] text-[rgba(43,38,32,0.72)] hover:bg-[rgba(255,255,255,0.7)]',
                  ].join(' ')}
                  title={f.label}
                >
                  {f.label}
                </button>
              ))}
            </div>
          ) : null}

          <div className="h-full rounded-[0.8rem] border border-[#b79a4b] bg-[#dec77f] p-5 shadow-[0_10px_22px_rgba(43,38,32,0.16)]">
            {extension === 'pdf' ? (
              <div className="h-full overflow-hidden rounded-[0.65rem] border border-[rgba(43,38,32,0.16)] bg-[rgba(245,241,232,0.72)]">
                <iframe title={activeFileName} src={activeFileUrl} className="h-full w-full" />
              </div>
            ) : extension === 'docx' ? (
              <div className="h-full overflow-y-auto rounded-[0.65rem] border border-[rgba(43,38,32,0.16)] bg-[rgba(245,241,232,0.72)] p-7 text-[var(--snf-ink)] [scrollbar-color:rgba(43,38,32,0.22)_transparent] [scrollbar-width:thin]">
                {detectedKind === 'pdf' && objectUrl ? (
                  <iframe title={activeFileName} src={objectUrl} className="h-full min-h-[60vh] w-full rounded-[0.5rem]" />
                ) : docxError ? (
                  <div className="text-sm leading-7 text-[#9a2f24]">
                    {docxError}{' '}
                    <a className="underline" href={activeFileUrl} target="_blank" rel="noreferrer">
                      Open directly
                    </a>
                    .
                    {fallbackText ? (
                      <pre className="mt-5 max-h-[52vh] overflow-auto whitespace-pre-wrap rounded-[0.5rem] border border-[rgba(43,38,32,0.12)] bg-[rgba(245,241,232,0.75)] p-4 text-[0.9rem] leading-6 text-[rgba(43,38,32,0.76)]">
                        {fallbackText}
                      </pre>
                    ) : null}
                  </div>
                ) : (
                  <>
                    {isLoading && !docxPreviewReady && !docxHtml ? (
                      <div className="mb-4 font-['IBM_Plex_Mono'] text-sm uppercase tracking-[0.16em] text-[rgba(43,38,32,0.52)]">Loading document...</div>
                    ) : null}
                    <div
                      ref={docxContainerRef}
                      className={[
                        'snf-docx-preview-shell text-[rgba(43,38,32,0.86)]',
                        docxPreviewReady ? 'block' : 'hidden',
                      ].join(' ')}
                    />
                    {docxHtml ? (
                      // Mammoth is retained as a fallback when layout-oriented DOCX preview fails.
                      <div className="max-w-none leading-7 text-[rgba(43,38,32,0.82)]" dangerouslySetInnerHTML={{ __html: docxHtml }} />
                    ) : null}
                    {!isLoading && !docxPreviewReady && !docxHtml ? (
                      <div className="text-sm text-[rgba(43,38,32,0.58)]">
                        No content to display.{' '}
                        <a className="underline" href={activeFileUrl} target="_blank" rel="noreferrer">
                          Open directly
                        </a>
                        .
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            ) : (
              <div className="h-full overflow-y-auto rounded-[0.65rem] border border-[rgba(43,38,32,0.16)] bg-[rgba(245,241,232,0.72)] p-7">
                <p className="text-sm text-[rgba(43,38,32,0.76)]">
                  Preview not supported for{' '}
                  <code className="rounded bg-[rgba(43,38,32,0.08)] px-1 py-0.5 font-mono">{extension || 'unknown'}</code>.
                </p>
                <p className="mt-3 text-sm text-[rgba(43,38,32,0.76)]">
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
    </div>
  )
}

export default FileViewerModal
