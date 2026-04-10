import { useEffect, useState } from 'react'
import Header from './components/Header'
import SearchSection from './components/SearchSection'
import SuggestedQueries from './components/SuggestedQueries'
import Footer from './components/Footer'
import ChatView from './components/ChatView'
import UploadPromPage from './components/UploadPromPage'

function getSessionIdFromPath(pathname) {
  const match = pathname.match(/^\/session\/([^/]+)$/)
  return match ? match[1] : null
}

function App() {
  const isLogoutPath = window.location.pathname === '/logout'
  const [view, setView] = useState('search') // 'search' | 'upload'
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [isThinking, setIsThinking] = useState(false)
  const [searchMode, setSearchMode] = useState('emails')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [hasUserSession, setHasUserSession] = useState(true)
  const [isCheckingUserSession, setIsCheckingUserSession] = useState(true)
  const [isCreatingUserSession, setIsCreatingUserSession] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(() => getSessionIdFromPath(window.location.pathname))

  const appendAssistantChunk = (assistantId, chunk) => {
    setMessages((prev) => {
      const idx = prev.findIndex((message) => message.id === assistantId)
      if (idx === -1) {
        return [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            text: chunk,
            isStreaming: true,
          },
        ]
      }

      return prev.map((message) =>
        message.id === assistantId
          ? { ...message, text: message.text + chunk, isStreaming: true }
          : message
      )
    })
  }

  const setAssistantText = (assistantId, text) => {
    setMessages((prev) => {
      const idx = prev.findIndex((message) => message.id === assistantId)
      if (idx === -1) {
        return [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            text,
            isStreaming: false,
          },
        ]
      }

      return prev.map((message) =>
        message.id === assistantId ? { ...message, text, isStreaming: false } : message
      )
    })
  }

  const finalizeAssistantMessage = (assistantId) => {
    setMessages((prev) => {
      const idx = prev.findIndex((message) => message.id === assistantId)
      if (idx === -1) return prev

      return prev.map((message) =>
        message.id === assistantId ? { ...message, isStreaming: false } : message
      )
    })
  }

  const streamEmbedResponse = async (endpoint, text, onChunk) => {
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`)
    }

    if (!response.body) {
      const data = await response.json()
      const fallbackText = data.text || ''
      if (fallbackText) onChunk(fallbackText)
      return fallbackText
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      if (!chunk) continue
      fullText += chunk
      onChunk(chunk)
    }

    const tail = decoder.decode()
    if (tail) {
      fullText += tail
      onChunk(tail)
    }

    return fullText
  }

  useEffect(() => {
    if (isLogoutPath) {
      const logout = async () => {
        try {
          await fetch('/logout', {
            method: 'POST',
            credentials: 'include',
          })
        } catch (error) {
          console.error('Logout request failed:', error)
        } finally {
          window.location.replace('/')
        }
      }

      logout()
      return
    }

  }, [isLogoutPath])

  useEffect(() => {
    if (isLogoutPath) return

    const checkUserSession = async () => {
      try {
        const response = await fetch('/user/status', {
          method: 'GET',
          credentials: 'include',
        })

        if (!response.ok) {
          throw new Error(`User status request failed: ${response.status}`)
        }

        const data = await response.json()
        setHasUserSession(Boolean(data.has_user))
      } catch (error) {
        console.error('User status request error:', error)
      } finally {
        setIsCheckingUserSession(false)
      }
    }

    checkUserSession()
  }, [isLogoutPath])

  useEffect(() => {
    const handlePopState = () => {
      setCurrentSessionId(getSessionIdFromPath(window.location.pathname))
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  if (isLogoutPath) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-600">
        Signing out...
      </div>
    )
  }

  const createUserSession = async () => {
    setIsCreatingUserSession(true)

    try {
      const response = await fetch('/user/init', {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`User init failed: ${response.status}`)
      }

      setHasUserSession(true)
    } catch (error) {
      console.error('User init request error:', error)
    } finally {
      setIsCreatingUserSession(false)
    }
  }

  const handleLogout = async () => {
    try {
      await fetch('/logout', {
        method: 'POST',
        credentials: 'include',
      })
    } catch (error) {
      console.error('Logout request failed:', error)
    } finally {
      window.location.replace('/')
    }
  }

  const createChatSession = async () => {
    const response = await fetch('/session/init', {
      method: 'POST',
      credentials: 'include',
    })

    if (!response.ok) {
      throw new Error(`Session init failed: ${response.status}`)
    }

    const data = await response.json()
    if (!data.session_id) {
      throw new Error('Session init did not return a session_id')
    }

    const nextSessionId = data.session_id
    setCurrentSessionId(nextSessionId)
    window.history.pushState({}, '', `/session/${nextSessionId}`)
    return nextSessionId
  }

  // Lightweight search — returns top 5 results with titles
  const handleSearch = async (searchQuery) => {
    const trimmed = searchQuery.trim()
    if (!trimmed) return

    setIsSearching(true)
    setSearchResults([])

    try {
      const endpoint =
        searchMode === 'proms' ? '/search/proms' : '/search/emails'
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })

      if (!response.ok) {
        console.error('Search request failed:', response.status)
        return
      }

      const data = await response.json()
      setSearchResults(data.results || [])
    } catch (error) {
      console.error('Search request error:', error)
    } finally {
      setIsSearching(false)
    }
  }

  // Full embed + chat completion for a selected result
  const handleStartChat = async (result) => {
    if (!hasUserSession) return

    const userQuery = query.trim() || result.title
    setSearchResults([])
    setQuery('')

    // Show the original search query as the user message
    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        role: 'user',
        text: userQuery,
      },
    ])

    setIsThinking(true)
    const assistantId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    let firstChunkReceived = false

    try {
      const sessionId = await createChatSession()

      const endpoint =
        searchMode === 'proms'
          ? `/session/${sessionId}/embed/proms/stream`
          : `/session/${sessionId}/embed/emails/stream`

      await streamEmbedResponse(endpoint, result.title, (chunk) => {
        if (!firstChunkReceived) {
          firstChunkReceived = true
          setIsThinking(false)
        }
        appendAssistantChunk(assistantId, chunk)
      })
      finalizeAssistantMessage(assistantId)
    } catch (error) {
      console.error('Stream embed request error:', error)
      setAssistantText(assistantId, 'Could not reach the server. Please try again.')
    } finally {
      setIsThinking(false)
    }
  }

  // Send a follow-up message from within ChatView
  const sendChatMessage = async (text) => {
    if (!hasUserSession || !currentSessionId) return

    const trimmed = text.trim()
    if (!trimmed) return

    setMessages((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        role: 'user',
        text: trimmed,
      },
    ])
    setQuery('')
    setIsThinking(true)
    const assistantId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    let firstChunkReceived = false

    try {
      const endpoint =
        searchMode === 'proms'
          ? `/session/${currentSessionId}/embed/proms/stream`
          : `/session/${currentSessionId}/embed/emails/stream`

      await streamEmbedResponse(endpoint, trimmed, (chunk) => {
        if (!firstChunkReceived) {
          firstChunkReceived = true
          setIsThinking(false)
        }
        appendAssistantChunk(assistantId, chunk)
      })
      finalizeAssistantMessage(assistantId)
    } catch (error) {
      console.error('Stream embed request error:', error)
      setAssistantText(assistantId, 'Could not reach the server. Please try again.')
    } finally {
      setIsThinking(false)
    }
  }

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion)
    handleSearch(suggestion)
  }

  const hasMessages = messages.length > 0 || Boolean(currentSessionId)

  return (
    <div
      className={[
        'flex flex-col bg-gradient-to-b from-slate-50 to-slate-100',
        view === 'upload' ? 'h-screen overflow-hidden' : 'min-h-screen',
      ].join(' ')}
    >
      {!isCheckingUserSession && !hasUserSession ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-300/25 px-4 backdrop-blur-[10px]">
          <div className="w-full max-w-xl rounded-[32px] border border-slate-700/70 bg-slate-900 px-7 py-8 shadow-[0_24px_70px_rgba(15,23,42,0.28)] sm:px-8 sm:py-9">
              <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-red-950/60 ring-1 ring-red-900/60">
                <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
              </div>
              <h2 className="mt-6 max-w-lg text-[2rem] font-semibold leading-[1.12] tracking-[-0.04em] text-slate-50 sm:text-[2.4rem]">
                Create a user session before starting a chat.
              </h2>
              <div className="mt-8 flex items-center justify-between gap-4">
                <div className="hidden text-sm text-slate-400 sm:block">
                  Required once.
                </div>
                <div className="w-full sm:w-auto">
                  <button
                    type="button"
                    onClick={createUserSession}
                    disabled={isCreatingUserSession}
                    className="inline-flex w-full items-center justify-center gap-3 rounded-2xl bg-red-600 px-6 py-3.5 text-sm font-semibold text-white shadow-[0_14px_32px_rgba(220,38,38,0.22)] transition-all hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300 sm:w-auto"
                  >
                    <span>{isCreatingUserSession ? 'Creating session...' : 'Create user session'}</span>
                    <span className="text-lg leading-none" aria-hidden="true">
                      →
                    </span>
                  </button>
                </div>
              </div>
          </div>
        </div>
      ) : null}

      <Header view={view} setView={setView} hasUserSession={hasUserSession} onLogout={handleLogout} />

      <main
        className={`flex-1 flex flex-col px-4 ${
          view === 'upload'
            ? 'items-stretch py-2 min-h-0 overflow-hidden'
            : hasMessages
              ? 'items-stretch py-6'
              : 'items-center justify-center py-12'
        }`}
      >
        {view === 'upload' ? (
          <UploadPromPage />
        ) : hasMessages ? (
          <ChatView
            messages={messages}
            query={query}
            setQuery={setQuery}
            onSend={sendChatMessage}
            isThinking={isThinking}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
          />
        ) : (
          <>
            {/* Search Icon */}
            <div className="mb-8">
              <div className="w-20 h-20 bg-gradient-to-br from-red-500 to-red-600 rounded-2xl flex items-center justify-center shadow-lg shadow-red-200">
                <svg
                  className="w-10 h-10 text-white"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
            </div>

            {/* Title */}
            <h1 className="text-4xl font-semibold text-slate-800 mb-10">
              What are you searching for?
            </h1>

            {/* Search Section */}
            <SearchSection
              query={query}
              setQuery={setQuery}
              onSearch={handleSearch}
              searchMode={searchMode}
              setSearchMode={setSearchMode}
              searchResults={searchResults}
              isSearching={isSearching}
              onStartChat={handleStartChat}
            />

            {/* Suggested Queries */}
            <SuggestedQueries onSuggestionClick={handleSuggestionClick} />
          </>
        )}
      </main>

      {view === 'upload' ? null : <Footer />}
    </div>
  )
}

export default App
