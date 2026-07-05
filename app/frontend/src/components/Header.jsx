import { LogOut } from 'lucide-react'

function Header({ view, setView, hasUserSession, onLogout }) {
  return (
    <header className="border-b border-[rgba(255,255,255,0.04)] bg-[var(--snf-topbar)] px-5 py-3 sm:px-6 lg:px-8">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <a
            href="/"
            className="rounded-[0.35rem] border border-[rgba(237,231,219,0.24)] px-3 py-1.5 font-['IBM_Plex_Mono'] text-[0.82rem] font-semibold tracking-[0.24em] text-[var(--snf-topbar-text)]"
          >
            nanochat
          </a>
        </div>

        {typeof setView === 'function' ? (
          <div className="mx-auto hidden md:block">
            <div className="flex items-center rounded-[0.72rem] border border-[rgba(169,125,64,0.42)] bg-[rgba(245,241,232,0.98)] p-1 shadow-[0_6px_16px_rgba(43,38,32,0.16)]">
              <button
                onClick={() => setView('search')}
                className={[
                  'relative min-w-[7rem] overflow-hidden rounded-[0.56rem] px-5 py-2.5 font-[\'IBM_Plex_Mono\'] text-[0.8rem] font-medium uppercase tracking-[0.18em] transition-colors',
                  view === 'search'
                    ? 'text-[var(--snf-ink)]'
                    : 'text-[rgba(107,97,82,0.88)] hover:text-[var(--snf-ink)]',
                ].join(' ')}
              >
                {view === 'search' ? (
                  <span
                    aria-hidden="true"
                    className="snf-wafer-grid absolute inset-0 rounded-[0.7rem] border border-[rgba(169,125,64,0.78)] bg-[linear-gradient(180deg,#e3dccd_0%,#d7ccb7_100%)]"
                  />
                ) : null}
                <span className="relative z-10">Search</span>
              </button>
              <button
                onClick={() => setView('upload')}
                className={[
                  'relative min-w-[7rem] overflow-hidden rounded-[0.56rem] px-5 py-2.5 font-[\'IBM_Plex_Mono\'] text-[0.8rem] font-medium uppercase tracking-[0.18em] transition-colors',
                  view === 'upload'
                    ? 'text-[var(--snf-ink)]'
                    : 'text-[rgba(107,97,82,0.88)] hover:text-[var(--snf-ink)]',
                ].join(' ')}
              >
                {view === 'upload' ? (
                  <span
                    aria-hidden="true"
                    className="snf-wafer-grid absolute inset-0 rounded-[0.7rem] border border-[rgba(169,125,64,0.78)] bg-[linear-gradient(180deg,#e3dccd_0%,#d7ccb7_100%)]"
                  />
                ) : null}
                <span className="relative z-10">Upload</span>
              </button>
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          {hasUserSession ? (
            <button
              type="button"
              onClick={onLogout}
              className="hidden rounded-[0.7rem] border border-[rgba(237,231,219,0.16)] px-3 py-2 font-['IBM_Plex_Mono'] text-[0.6rem] uppercase tracking-[0.14em] text-[rgba(237,231,219,0.78)] transition-colors hover:text-white sm:inline-flex sm:items-center sm:gap-2"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Logout</span>
            </button>
          ) : null}

          <div className="flex h-[2.8rem] w-[2.8rem] items-center justify-center rounded-[0.7rem] bg-[var(--snf-topbar-text)] font-['IBM_Plex_Mono'] text-[0.7rem] font-semibold text-[var(--snf-ink)]">
            JD
          </div>
        </div>
      </div>

      {typeof setView === 'function' ? (
        <div className="mt-4 flex justify-center md:hidden">
          <div className="flex w-full max-w-[22rem] items-center rounded-[0.9rem] border border-[rgba(169,125,64,0.42)] bg-[rgba(245,241,232,0.98)] p-1 shadow-[0_6px_16px_rgba(43,38,32,0.16)]">
            <button
              onClick={() => setView('search')}
              className={[
                'relative flex-1 overflow-hidden rounded-[0.7rem] px-4 py-3 font-[\'IBM_Plex_Mono\'] text-sm uppercase tracking-[0.16em] transition-colors',
                view === 'search'
                  ? 'text-[var(--snf-ink)]'
                  : 'text-[rgba(107,97,82,0.88)]',
              ].join(' ')}
            >
              {view === 'search' ? (
                <span
                  aria-hidden="true"
                  className="snf-wafer-grid absolute inset-0 rounded-[0.7rem] border border-[rgba(169,125,64,0.78)] bg-[linear-gradient(180deg,#e3dccd_0%,#d7ccb7_100%)]"
                />
              ) : null}
              <span className="relative z-10">Search</span>
            </button>
            <button
              onClick={() => setView('upload')}
              className={[
                'relative flex-1 overflow-hidden rounded-[0.7rem] px-4 py-3 font-[\'IBM_Plex_Mono\'] text-sm uppercase tracking-[0.16em] transition-colors',
                view === 'upload'
                  ? 'text-[var(--snf-ink)]'
                  : 'text-[rgba(107,97,82,0.88)]',
              ].join(' ')}
            >
              {view === 'upload' ? (
                <span
                  aria-hidden="true"
                  className="snf-wafer-grid absolute inset-0 rounded-[0.7rem] border border-[rgba(169,125,64,0.78)] bg-[linear-gradient(180deg,#e3dccd_0%,#d7ccb7_100%)]"
                />
              ) : null}
              <span className="relative z-10">Upload</span>
            </button>
          </div>
        </div>
      ) : null}
    </header>
  )
}

export default Header
