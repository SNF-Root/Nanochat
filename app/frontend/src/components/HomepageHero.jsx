import { useLayoutEffect, useRef, useState } from 'react'

function HomepageHero({
  query,
  setQuery,
  onSearch,
  isSearching,
}) {
  const inputRef = useRef(null)
  const [composerHeight, setComposerHeight] = useState(52)

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || isSearching) return
    onSearch(trimmed)
  }

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    handleSubmit(event)
  }

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return

    input.style.height = '0px'
    const nextHeight = Math.max(52, Math.min(input.scrollHeight, 220))
    input.style.height = `${nextHeight}px`
    setComposerHeight(nextHeight)
  }, [query])

  return (
    <section className="w-full flex-1 px-6 py-5 sm:px-8 lg:px-10 lg:py-5">
      <div className="mx-auto flex w-full max-w-[1880px] flex-col gap-7 lg:flex-row lg:items-start lg:gap-8">
        <div className="w-full lg:max-w-[24rem] lg:flex-[0_0_24rem]">
          <div className="relative min-h-[24rem] bg-[rgba(255,255,255,0.34)] lg:min-h-[34rem]">
            <div className="absolute left-0 top-0 h-8 w-8 border-l-[4px] border-t-[4px] border-[var(--snf-ink)]" />
            <div className="absolute right-0 top-0 h-8 w-8 border-r-[4px] border-t-[4px] border-[var(--snf-ink)]" />
            <div className="absolute bottom-0 left-0 h-8 w-8 border-b-[4px] border-l-[4px] border-[var(--snf-ink)]" />
            <div className="absolute bottom-0 right-0 h-8 w-8 border-b-[4px] border-r-[4px] border-[var(--snf-ink)]" />

            <div className="flex min-h-[24rem] items-center justify-center px-6 text-center lg:min-h-[34rem]">
              <p className="font-['IBM_Plex_Mono'] text-[0.62rem] uppercase tracking-[0.28em] text-[rgba(122,108,87,0.9)]">
                FILES APPEAR HERE
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
                <textarea
                  id="homepage-query"
                  ref={inputRef}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isSearching}
                  rows={1}
                  placeholder="show me proms discussing zno nanoparticles"
                  className="min-w-0 w-full translate-y-[0.62rem] resize-none overflow-hidden bg-transparent font-['IBM_Plex_Mono'] text-[1.25rem] leading-[1.35] tracking-[-0.02em] text-[rgba(237,231,219,0.82)] caret-[var(--snf-accent)] outline-none placeholder:text-[rgba(237,231,219,0.62)] disabled:cursor-not-allowed"
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
