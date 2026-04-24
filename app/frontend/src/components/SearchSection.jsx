import { Paperclip, Mic, ArrowUp, MessageSquare, Loader2 } from 'lucide-react'

function SearchSection({
  query,
  setQuery,
  onSearch,
  searchMode,
  setSearchMode,
  searchResults,
  isSearching,
  onStartChat,
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

  const hasResults = searchResults && searchResults.length > 0

  return (
    <div className="w-full max-w-xl relative">
      <form onSubmit={handleSubmit}>
        <div
          className={`bg-white shadow-lg shadow-slate-200/50 border border-slate-200 p-4 hover:shadow-xl hover:border-slate-300 transition-all duration-300 ${
            hasResults || isSearching
              ? 'rounded-t-2xl rounded-b-none border-b-0'
              : 'rounded-2xl'
          }`}
        >
          {/* Input Row */}
          <div className="flex items-start gap-3 mb-3">
            <button
              type="button"
              className="mt-1 p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all"
            >
              <Paperclip className="w-5 h-5" />
            </button>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about any past SNF internal document"
              rows={2}
              className="flex-1 min-h-[3.5rem] max-h-40 resize-none overflow-y-auto bg-transparent text-slate-700 placeholder-slate-400 outline-none text-lg leading-7 [overflow-wrap:anywhere]"
            />
          </div>

          {/* Bottom Row */}
          <div className="flex items-center justify-between">
            {/* Mode Toggle */}
            <div className="flex items-center bg-slate-100 rounded-lg border border-slate-200 p-0.5">
              <button
                type="button"
                onClick={() => setSearchMode('emails')}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-all duration-200 ${
                  searchMode === 'emails'
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                Emails
              </button>
              <button
                type="button"
                onClick={() => setSearchMode('proms')}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-all duration-200 ${
                  searchMode === 'proms'
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                PROMs
              </button>
              <button
                type="button"
                onClick={() => setSearchMode('all')}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-all duration-200 ${
                  searchMode === 'all'
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                All
              </button>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="p-3 bg-slate-800 text-white rounded-full hover:bg-slate-700 transition-colors"
              >
                <Mic className="w-5 h-5" />
              </button>
              <button
                type="submit"
                disabled={!query.trim()}
                className="p-3 bg-slate-200 text-slate-400 rounded-full hover:bg-red-500 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
              >
                <ArrowUp className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* Search Results Dropdown */}
      {(hasResults || isSearching) && (
        <div className="absolute left-0 right-0 z-50 bg-white border border-t-0 border-slate-200 rounded-b-2xl shadow-lg shadow-slate-200/50 overflow-hidden">
          {isSearching ? (
            <div className="flex items-center justify-center gap-2 py-4 text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Searching...</span>
            </div>
          ) : (
            <div className="divide-y divide-slate-100 max-h-[400px] overflow-y-auto">
              {searchResults.map((result) => (
                <div
                  key={result.id}
                  className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50 transition-colors group"
                >
                  <button
                    onClick={() => onStartChat(result)}
                    className="flex-shrink-0 mt-0.5 flex items-center gap-1.5 px-3 py-1.5 bg-red-500 text-white text-xs font-medium rounded-lg hover:bg-red-600 transition-colors shadow-sm"
                  >
                    <MessageSquare className="w-3.5 h-3.5" />
                    Chat
                  </button>
                  <p className="flex-1 text-sm font-semibold text-slate-700 leading-relaxed group-hover:text-slate-900">
                    {result.title}
                  </p>
                  <span className="flex-shrink-0 mt-0.5 text-xs text-slate-400 font-mono">
                    {(result.similarity * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default SearchSection
