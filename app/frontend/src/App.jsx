import { useEffect, useState } from 'react'
import Header from './components/Header'
import SearchSection from './components/SearchSection'
import SuggestedQueries from './components/SuggestedQueries'
import Footer from './components/Footer'
import ChatView from './components/ChatView'
import UploadPromPage from './components/UploadPromPage'

function App() {
  const isLogoutPath = window.location.pathname === '/logout'
  const [view, setView] = useState('search') // 'search' | 'upload'
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [isThinking, setIsThinking] = useState(false)
  const [searchMode, setSearchMode] = useState('emails')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)

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
          },
        ]
      }

      return prev.map((message) =>
        message.id === assistantId
          ? { ...message, text: message.text + chunk }
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
          },
        ]
      }

      return prev.map((message) =>
        message.id === assistantId ? { ...message, text } : message
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

    const initializeSession = async () => {
      try {
        await fetch('/session/init', {
          method: 'GET',
          credentials: 'include',
        })
      } catch (error) {
        console.error('Session init request failed:', error)
      }
    }

    initializeSession()
  }, [isLogoutPath])

  if (isLogoutPath) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-600">
        Signing out...
      </div>
    )
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
      const endpoint =
        searchMode === 'proms' ? '/embed/proms/stream' : '/embed/emails/stream'

      await streamEmbedResponse(endpoint, result.title, (chunk) => {
        if (!firstChunkReceived) {
          firstChunkReceived = true
          setIsThinking(false)
        }
        appendAssistantChunk(assistantId, chunk)
      })
    } catch (error) {
      console.error('Stream embed request error:', error)
      try {
        const fallbackEndpoint =
          searchMode === 'proms' ? '/embed/proms' : '/embed/emails'
        const fallbackResponse = await fetch(fallbackEndpoint, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: result.title }),
        })
        if (!fallbackResponse.ok) throw new Error(`Fallback request failed: ${fallbackResponse.status}`)
        const data = await fallbackResponse.json()
        setAssistantText(assistantId, data.text)
      } catch (fallbackError) {
        setAssistantText(assistantId, 'Could not reach the server. Please try again.')
      }
    } finally {
      setIsThinking(false)
    }
  }

  // Send a follow-up message from within ChatView
  const sendChatMessage = async (text) => {
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
        searchMode === 'proms' ? '/embed/proms/stream' : '/embed/emails/stream'

      await streamEmbedResponse(endpoint, trimmed, (chunk) => {
        if (!firstChunkReceived) {
          firstChunkReceived = true
          setIsThinking(false)
        }
        appendAssistantChunk(assistantId, chunk)
      })
    } catch (error) {
      try {
        const fallbackEndpoint =
          searchMode === 'proms' ? '/embed/proms' : '/embed/emails'
        const fallbackResponse = await fetch(fallbackEndpoint, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: trimmed }),
        })
        if (!fallbackResponse.ok) throw new Error(`Fallback request failed: ${fallbackResponse.status}`)
        const data = await fallbackResponse.json()
        setAssistantText(assistantId, data.text)
      } catch (fallbackError) {
        setAssistantText(assistantId, 'Could not reach the server. Please try again.')
      }
    } finally {
      setIsThinking(false)
    }
  }

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion)
    handleSearch(suggestion)
  }

  const hasMessages = messages.length > 0

  return (
    <div
      className={[
        'flex flex-col bg-gradient-to-b from-slate-50 to-slate-100',
        view === 'upload' ? 'h-screen overflow-hidden' : 'min-h-screen',
      ].join(' ')}
    >
      <Header view={view} setView={setView} />

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
