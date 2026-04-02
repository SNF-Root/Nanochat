import { LogOut } from 'lucide-react'

function Header({ view, setView, hasUserSession, onLogout }) {
  return (
    <header className="w-full px-6 py-4 flex items-center justify-between bg-white/80 backdrop-blur-sm border-b border-slate-100">
      <div className="flex items-center gap-3">
        <a href="/" className="text-2xl font-bold text-red-600">
          SNF
        </a>
        <span className="text-slate-300">|</span>
        <button className="flex items-center gap-2 text-slate-600 hover:text-slate-800 transition-colors">
          <span className="font-medium">Internal RAG 1.0</span>
        </button>

        {typeof setView === 'function' ? (
          <div className="ml-4 hidden sm:flex items-center gap-1 rounded-2xl bg-slate-100 p-1 border border-slate-200">
            <button
              onClick={() => setView('search')}
              className={[
                'px-3 py-1.5 text-sm rounded-xl transition-colors',
                view === 'search'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900',
              ].join(' ')}
            >
              Search
            </button>
            <button
              onClick={() => setView('upload')}
              className={[
                'px-3 py-1.5 text-sm rounded-xl transition-colors',
                view === 'upload'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900',
              ].join(' ')}
            >
              Upload
            </button>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-4">
        {hasUserSession ? (
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900"
          >
            <LogOut className="w-4 h-4" />
            <span>Logout</span>
          </button>
        ) : null}
        <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center text-red-600 font-semibold cursor-pointer hover:bg-red-200 transition-colors">
          JD
        </div>
      </div>
    </header>
  )
}

export default Header
