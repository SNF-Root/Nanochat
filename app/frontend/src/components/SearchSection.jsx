import { useState } from 'react'
import { Paperclip, ArrowUp, MessageSquare, Loader2, X } from 'lucide-react'

function SearchSection({
  query,
  setQuery,
  onSearch,
  searchResults,
  isSearching,
  onStartChat,
  composerTabs,
  enableAddContext,
  attachedPromTitles,
  attachedPromIds,
  sessionId,
  onAddContextProms,
}) {
  const [isAddContextOpen, setIsAddContextOpen] = useState(false)
  const [contextQuery, setContextQuery] = useState('')
  const [contextResults, setContextResults] = useState([])
  const [isContextSearching, setIsContextSearching] = useState(false)
  const [selectedContextResults, setSelectedContextResults] = useState([])
  const [isAddingContext, setIsAddingContext] = useState(false)

  const runContextSearch = async (text) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setIsContextSearching(true)
    setContextResults([])
    try {
      const response = await fetch('/search/all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })
      if (!response.ok) {
        console.error('Context search failed:', response.status)
        return
      }
      const data = await response.json()
      setContextResults(data.results || [])
    } catch (error) {
      console.error('Context search error:', error)
    } finally {
      setIsContextSearching(false)
    }
  }

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
  const attachedIdSet = new Set(attachedPromIds || [])
  const selectedContextIdSet = new Set(selectedContextResults.map((result) => result.id))

  const resetAddContextModal = () => {
    setIsAddContextOpen(false)
    setContextQuery('')
    setContextResults([])
    setSelectedContextResults([])
    setIsAddingContext(false)
  }

  const toggleContextSelection = (result) => {
    if (attachedIdSet.has(result.id)) return
    setSelectedContextResults((prev) => {
      const exists = prev.some((item) => item.id === result.id)
      if (exists) {
        return prev.filter((item) => item.id !== result.id)
      }
      return [...prev, result]
    })
  }

  const submitAddContext = async () => {
    if (!sessionId || !selectedContextResults.length || !onAddContextProms) return

    setIsAddingContext(true)
    try {
      await onAddContextProms(selectedContextResults)
      resetAddContextModal()
    } catch (error) {
      console.error('Add context request failed:', error)
    } finally {
      setIsAddingContext(false)
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

          <div className="flex items-center justify-between">
            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={!query.trim()}
                className="p-3 bg-slate-200 text-slate-400 rounded-full hover:bg-red-500 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
              >
                <ArrowUp className="w-5 h-5" />
              </button>
              {enableAddContext ? (
                <button
                type="button"
                onClick={() => setIsAddContextOpen(true)}
                className="ml-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50"
              >
                Add Context
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </form>

      {enableAddContext && isAddContextOpen ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-900/35 px-4 py-6 backdrop-blur-[10px]">
          <div className="w-full max-w-2xl overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.28)]">
            <div className="flex items-start justify-between border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-red-50/30 px-5 py-5">
              <div className="text-[2rem] font-semibold tracking-[-0.04em] text-slate-900 sm:text-[2.35rem]">
                Add context
              </div>
              <button
                type="button"
                aria-label="Close add context"
                onClick={resetAddContextModal}
                className="rounded-full border border-slate-200 bg-white p-2 text-slate-600 transition-colors hover:bg-slate-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 pt-4">
              <input
                value={contextQuery}
                onChange={(e) => setContextQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    runContextSearch(contextQuery)
                  }
                }}
                placeholder="Search more PROMs to add"
                className="w-full rounded-2xl border border-slate-200 bg-white px-5 py-4 text-[15px] font-medium text-slate-800 shadow-sm outline-none transition-colors placeholder:font-normal placeholder:text-slate-400 focus:border-slate-300"
              />

              <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                {isContextSearching ? (
                  <div className="flex items-center justify-center gap-2 px-4 py-5 text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Searching…</span>
                  </div>
                ) : contextResults.length ? (
                  <div className="divide-y divide-slate-200 max-h-[50vh] overflow-y-auto">
                    {contextResults.map((result) => (
                      <div key={result.id} className="px-4 py-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold tracking-[-0.01em] text-slate-800 truncate">{result.title}</div>
                          <div className="mt-1 text-xs font-medium text-slate-500">
                            {(result.similarity * 100).toFixed(0)}% match
                          </div>
                        </div>
                        <button
                          type="button"
                          disabled={!sessionId || attachedIdSet.has(result.id)}
                          onClick={() => toggleContextSelection(result)}
                          className="flex-shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {attachedIdSet.has(result.id)
                            ? 'Attached'
                            : selectedContextIdSet.has(result.id)
                              ? 'Selected'
                              : 'Select'}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : contextQuery.trim() ? (
                  <div className="px-4 py-5 text-sm text-slate-500">
                    No matching PROMs found.
                  </div>
                ) : null}
              </div>

              <div className="mt-4 flex items-center justify-between gap-3">
                <div className="text-sm text-slate-500">
                  {selectedContextResults.length
                    ? `${selectedContextResults.length} PROM${selectedContextResults.length === 1 ? '' : 's'} selected`
                    : 'Select one or more PROMs to add to this chat.'}
                </div>
                <button
                  type="button"
                  disabled={!sessionId || !selectedContextResults.length || !onAddContextProms || isAddingContext}
                  onClick={submitAddContext}
                  className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isAddingContext ? 'Adding...' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

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
