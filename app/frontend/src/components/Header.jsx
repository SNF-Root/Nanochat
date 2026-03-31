import { ChevronDown, Maximize2, Bell } from 'lucide-react'

function Header({ view, setView }) {
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
        {/* <button className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-all">
          <Maximize2 className="w-5 h-5" />
        </button>
        <button className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-all relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full"></span>
        </button> */}
        <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center text-red-600 font-semibold cursor-pointer hover:bg-red-200 transition-colors">
          JD
        </div>
      </div>
    </header>
  )
}

export default Header
