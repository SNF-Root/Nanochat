import { useLayoutEffect, useRef, useState } from 'react'

function WaferToggle({ label, active, onClick, compact = false }) {
  const sizeClass = 'h-[5.5rem] w-[5.5rem]'
  const labelClass = compact ? 'text-[0.76rem]' : 'text-[0.9rem]'
  const outerStroke = active ? 'rgba(191,142,69,0.95)' : 'rgba(214,204,186,0.9)'
  const outerGlow = active
    ? 'shadow-[0_0_0_3px_rgba(191,142,69,0.16),0_10px_26px_rgba(43,38,32,0.16)]'
    : 'shadow-[0_0_0_1px_rgba(214,204,186,0.75)] opacity-80'

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'relative flex items-center justify-center rounded-full bg-transparent transition-all',
        sizeClass,
        outerGlow,
      ].join(' ')}
      aria-pressed={active}
    >
      <svg viewBox="0 0 100 100" className="h-full w-full">
        <circle cx="50" cy="50" r="47" fill="rgba(255,255,255,0.08)" stroke={outerStroke} strokeWidth="4" />
        <circle cx="50" cy="50" r="36" fill="#ddd3c2" stroke="rgba(43,38,32,0.28)" strokeWidth="1.8" />
        <path d="M 50 14 A 36 36 0 0 0 29 21 L 38 31 A 22 22 0 0 1 50 28 Z" fill="rgba(43,38,32,0.34)" />
        <line x1="50" y1="14" x2="50" y2="86" stroke="rgba(43,38,32,0.28)" strokeWidth="1.4" />
        <line x1="14" y1="50" x2="86" y2="50" stroke="rgba(43,38,32,0.28)" strokeWidth="1.4" />
        <line x1="24" y1="24" x2="76" y2="24" stroke="rgba(43,38,32,0.18)" strokeWidth="1.2" />
        <line x1="24" y1="76" x2="76" y2="76" stroke="rgba(43,38,32,0.18)" strokeWidth="1.2" />
        <line x1="24" y1="24" x2="24" y2="76" stroke="rgba(43,38,32,0.18)" strokeWidth="1.2" />
        <line x1="76" y1="24" x2="76" y2="76" stroke="rgba(43,38,32,0.18)" strokeWidth="1.2" />
        <text
          x="50"
          y="56"
          textAnchor="middle"
          className={`font-['IBM_Plex_Mono'] font-semibold uppercase tracking-[-0.03em] ${labelClass}`}
          fill="#2b2620"
        >
          {label}
        </text>
      </svg>
    </button>
  )
}

function HomepageHero({
  query,
  setQuery,
  onSearch,
  searchMode,
  setSearchMode,
  isSearching,
}) {
  const inputRef = useRef(null)
  const markerRef = useRef(null)
  const [caretIndex, setCaretIndex] = useState(0)
  const [caretPosition, setCaretPosition] = useState({ left: 0, top: 0 })
  const [composerHeight, setComposerHeight] = useState(52)

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || isSearching) return
    onSearch(trimmed)
  }

  const syncCaretFromInput = () => {
    const nextIndex = inputRef.current?.selectionStart ?? query.length
    setCaretIndex(nextIndex)
  }

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    handleSubmit(event)
  }

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return

    const nextIndex = Math.min(caretIndex, query.length)
    if (nextIndex !== caretIndex) {
      setCaretIndex(nextIndex)
      return
    }

    input.style.height = '0px'
    const nextHeight = Math.max(52, Math.min(input.scrollHeight, 220))
    input.style.height = `${nextHeight}px`
    setComposerHeight(nextHeight)

    const inputRect = input.getBoundingClientRect()
    const markerRect = markerRef.current?.getBoundingClientRect()

    if (!markerRect) return

    setCaretPosition({
      left: Math.max(0, markerRect.left - inputRect.left),
      top: Math.max(0, markerRect.top - inputRect.top),
    })
  }, [caretIndex, query])

  return (
    <section className="w-full flex-1 px-6 py-5 sm:px-8 lg:px-10 lg:py-5">
      <div className="mx-auto flex w-full max-w-[1880px] flex-col gap-7 lg:flex-row lg:items-start lg:gap-8">
        <div className="w-full lg:max-w-[24rem] lg:flex-[0_0_24rem]">
          <div className="mb-4 flex items-center justify-center gap-5 lg:justify-start lg:pl-[5.7rem]">
            <WaferToggle
              label="PROMS"
              active={searchMode === 'proms'}
              onClick={() => setSearchMode('proms')}
            />
            <WaferToggle
              label="EMAILS"
              active={searchMode === 'emails'}
              onClick={() => setSearchMode('emails')}
              compact
            />
          </div>

          <div className="relative min-h-[24rem] bg-[rgba(255,255,255,0.34)] lg:min-h-[34rem]">
            <div className="absolute left-0 top-0 h-8 w-8 border-l-[4px] border-t-[4px] border-[var(--snf-ink)]" />
            <div className="absolute right-0 top-0 h-8 w-8 border-r-[4px] border-t-[4px] border-[var(--snf-ink)]" />
            <div className="absolute bottom-0 left-0 h-8 w-8 border-b-[4px] border-l-[4px] border-[var(--snf-ink)]" />
            <div className="absolute bottom-0 right-0 h-8 w-8 border-b-[4px] border-r-[4px] border-[var(--snf-ink)]" />

            <div className="flex min-h-[24rem] items-center justify-center px-6 text-center lg:min-h-[34rem]">
              <p className="font-['IBM_Plex_Mono'] text-[0.62rem] uppercase tracking-[0.28em] text-[rgba(122,108,87,0.9)]">
                {searchMode === 'emails' ? 'EMAILS APPEAR HERE' : 'PROMS APPEAR HERE'}
              </p>
            </div>
          </div>
        </div>

        <div className="flex w-full flex-1 flex-col pt-0 lg:pt-1">
          <h1 className="max-w-[15ch] text-[1.95rem] font-semibold leading-[0.96] tracking-[-0.06em] text-[var(--snf-ink)] sm:text-[2.65rem]">
            Query the fab archive.
          </h1>

          <p className="mt-3 max-w-[58rem] font-['IBM_Plex_Mono'] text-[0.68rem] leading-[1.08] tracking-[0.03em] text-[rgba(107,97,82,0.95)] sm:text-[0.76rem]">
            A conversational interface to historical prom requests and the email discussions that informed their approval or denial.
          </p>

          <form onSubmit={handleSubmit} className="mt-7 w-full">
            <label htmlFor="homepage-query" className="sr-only">
              Search the fab archive
            </label>
            <div
              className="flex items-start gap-5 rounded-[1.55rem] bg-[var(--snf-panel)] px-8 pt-4 pb-2.5 shadow-[0_14px_26px_rgba(43,38,32,0.15)] ring-1 ring-[rgba(255,255,255,0.03)]"
              style={{ minHeight: `${composerHeight + 12}px` }}
            >
              <span className="translate-y-[0.42rem] font-['IBM_Plex_Mono'] text-[1.9rem] font-medium leading-none text-[var(--snf-accent)]">
                [
              </span>
              <div className="relative min-w-0 flex-1">
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 overflow-hidden font-['IBM_Plex_Mono'] text-[1.25rem] leading-[1.35] tracking-[-0.02em]"
                >
                  <div className="absolute inset-0 translate-y-[0.62rem] whitespace-pre-wrap break-words text-[rgba(237,231,219,0.82)]">
                    {query}
                  </div>
                  <div className="translate-y-[0.62rem] whitespace-pre-wrap break-words text-transparent">
                    {query.slice(0, caretIndex)}
                    <span
                      ref={markerRef}
                      className="inline-block h-[1.7rem] w-0 align-top"
                    />
                  </div>
                  <span
                    className="snf-caret absolute h-7 w-[0.52rem] rounded-[1px] bg-[var(--snf-accent)]"
                    style={{
                      left: `${caretPosition.left}px`,
                      top: query ? `${caretPosition.top}px` : '0.62rem',
                    }}
                  />
                  {!query ? (
                    <span className="absolute left-0 top-0 translate-y-[0.62rem] whitespace-nowrap text-[rgba(237,231,219,0.62)]">
                      show me proms discussing zno nanoparticles
                    </span>
                  ) : null}
                </div>
                <textarea
                  id="homepage-query"
                  ref={inputRef}
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value)
                    setCaretIndex(event.target.selectionStart ?? event.target.value.length)
                  }}
                  onClick={syncCaretFromInput}
                  onKeyDown={handleKeyDown}
                  onKeyUp={syncCaretFromInput}
                  onSelect={syncCaretFromInput}
                  onFocus={syncCaretFromInput}
                  disabled={isSearching}
                  rows={1}
                  className="min-w-0 w-full translate-y-[0.62rem] resize-none overflow-hidden bg-transparent font-['IBM_Plex_Mono'] text-[1.25rem] leading-[1.35] tracking-[-0.02em] text-transparent caret-transparent outline-none disabled:cursor-not-allowed"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
              <span className="translate-y-[0.42rem] font-['IBM_Plex_Mono'] text-[1.9rem] font-medium leading-none text-[var(--snf-accent)]">
                ]
              </span>
              <button type="submit" className="sr-only">
                Search
              </button>
            </div>
          </form>
        </div>
      </div>
    </section>
  )
}

export default HomepageHero
