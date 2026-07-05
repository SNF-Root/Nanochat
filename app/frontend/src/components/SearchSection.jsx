import { Paperclip, ArrowUp } from 'lucide-react'

function SearchSection({
  query,
  setQuery,
  onSearch,
  composerTabs,
}) {
  const handleSubmit = (e) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="w-full max-w-xl relative">
      {composerTabs && composerTabs.length > 0 ? (
        <div className="absolute left-6 top-0 z-20 flex -translate-y-[calc(100%-1px)] items-end gap-2">
          {composerTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={tab.onClick}
              className={[
                'rounded-t-[14px] border border-b-0 px-4 py-2 text-sm font-semibold tracking-[0.01em] transition-all duration-200',
                tab.isActive
                  ? 'border-[#9fb2cd] bg-[#dbe7f7] text-[#314763]'
                  : 'border-[#c8d3e4] bg-[#eef3fb] text-[#70839f] hover:bg-[#e2eaf7] hover:text-[#4a607e]',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      <form onSubmit={handleSubmit}>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-lg shadow-slate-200/50 transition-all duration-300 hover:border-slate-300 hover:shadow-xl">
          <div className="mb-3 flex items-start gap-3">
            <button
              type="button"
              className="mt-1 rounded-lg p-2 text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-600"
            >
              <Paperclip className="h-5 w-5" />
            </button>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about any past SNF internal document"
              rows={2}
              className="min-h-[3.5rem] max-h-40 flex-1 resize-none overflow-y-auto bg-transparent text-lg leading-7 text-slate-700 outline-none placeholder-slate-400 [overflow-wrap:anywhere]"
            />
          </div>

          <div className="flex items-center justify-end">
            <button
              type="submit"
              disabled={!query.trim()}
              className="rounded-full bg-slate-200 p-3 text-slate-400 transition-all duration-200 hover:bg-red-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ArrowUp className="h-5 w-5" />
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}

export default SearchSection
