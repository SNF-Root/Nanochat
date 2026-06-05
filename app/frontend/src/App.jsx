import { useEffect, useState } from 'react'
import Header from './components/Header'
import SearchSection from './components/SearchSection'
import SuggestedQueries from './components/SuggestedQueries'
import Footer from './components/Footer'
import ChatView from './components/ChatView'
import UploadPromPage from './components/UploadPromPage'
import TestChatPage from './components/TestChatPage'
import FileViewerModal from './components/FileViewerModal'

const TEST_CHAT_SEED_MESSAGES = [
  {
    id: 'test-user-1',
    role: 'user',
    text: 'I opened Ashutosh Divekar\'s PROM for the polymer-metal centrifugation request. What is the core request and who submitted it?',
    isStreaming: false,
  },
  {
    id: 'test-assistant-1',
    role: 'assistant',
    text: 'The PROM is a Process or Materials Review Request Form for the centrifugation of a polymer-metal complex. The requestor listed on the form is Dr. Ashutosh Divekar.',
    isStreaming: false,
  },
  {
    id: 'test-user-2',
    role: 'user',
    text: 'Pull out the date, company, and badge ID from the form as well.',
    isStreaming: false,
  },
  {
    id: 'test-assistant-2',
    role: 'assistant',
    text: 'The form is dated `06/27/2023`. The company name or PI field lists `Evoloh inc.` and the badge ID field shows `ashutosh.divekar@evoloh.com`.',
    isStreaming: false,
  },
  {
    id: 'test-user-3',
    role: 'user',
    text: 'What should the operations team review first before approving this PROM?',
    isStreaming: false,
  },
  {
    id: 'test-assistant-3',
    role: 'assistant',
    text: 'Start with the chemical or material description, then verify the handling and process details, and finally confirm whether the requested centrifugation workflow introduces any safety, contamination, or equipment compatibility concerns.',
    isStreaming: false,
  },
  {
    id: 'test-user-4',
    role: 'user',
    text: 'Frame that as a short decision-ready summary for the internal committee.',
    isStreaming: false,
  },
  {
    id: 'test-assistant-4',
    role: 'assistant',
    text: 'Committee summary: This PROM requests review of a centrifugation process involving a polymer-metal complex submitted by Dr. Ashutosh Divekar of Evoloh inc. Before approval, the committee should validate the material composition, confirm compatibility with SNF equipment and handling protocols, and check whether the process creates unusual safety or contamination risks.',
    isStreaming: false,
  },
]

function getSessionIdFromPath(pathname) {
  const match = pathname.match(/^\/session\/([^/]+)$/)
  return match ? match[1] : null
}

function getSearchEndpoint() {
  return '/search/all'
}

function getStreamEndpoint(sessionId) {
  return `/session/${sessionId}/embed/all/stream`
}

function getAttachedPromsStorageKey(sessionId) {
  return `attached_proms:${sessionId}`
}

function readAttachedPromsFromStorage(sessionId) {
  if (!sessionId) return []

  try {
    const raw = window.localStorage.getItem(getAttachedPromsStorageKey(sessionId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch (error) {
    console.error('Could not read attached PROMs from localStorage:', error)
    return []
  }
}

function writeAttachedPromsToStorage(sessionId, attachedProms) {
  if (!sessionId) return

  try {
    window.localStorage.setItem(
      getAttachedPromsStorageKey(sessionId),
      JSON.stringify(attachedProms),
    )
  } catch (error) {
    console.error('Could not write attached PROMs to localStorage:', error)
  }
}

function EmailViewerModal({
  sessionId,
  onClose,
  onSessionExpired,
}) {
  const [emailsState, setEmailsState] = useState({
    isLoading: true,
    error: '',
    entries: [],
  })
  const [activeEntryKey, setActiveEntryKey] = useState('')
  const [activeEmailKey, setActiveEmailKey] = useState('')

  useEffect(() => {
    let cancelled = false

    const loadEmails = async () => {
      if (!sessionId) {
        setEmailsState({
          isLoading: false,
          error: '',
          entries: [],
        })
        return
      }

      setEmailsState({
        isLoading: true,
        error: '',
        entries: [],
      })

      try {
        const response = await fetch(`/emails/retrieve_emails/${sessionId}`, {
          method: 'GET',
          credentials: 'include',
        })

        if (onSessionExpired(response)) return

        if (!response.ok) {
          throw new Error(`Email retrieval failed: ${response.status}`)
        }

        const data = await response.json()
        const entries = Object.entries(data || {})
          .map(([entryKey, entryValue]) => {
            const emails = ['email_1', 'email_2', 'email_3']
              .map((key, index) => {
                const rawThread = entryValue?.[key]
                if (!rawThread) return null
                return {
                  key,
                  label: `Email ${index + 1}`,
                  rawThread,
                }
              })
              .filter(Boolean)

            if (!emails.length) return null
            return {
              key: entryKey,
              entryId: entryValue?.entry_id ?? Number(entryKey),
              requestTitle: entryValue?.request_title || `PROM ${entryKey}`,
              emails,
            }
          })
          .filter(Boolean)

        if (cancelled) return

        setEmailsState({
          isLoading: false,
          error: '',
          entries,
        })
      } catch (error) {
        if (cancelled) return
        setEmailsState({
          isLoading: false,
          error: error instanceof Error ? error.message : 'Could not load emails.',
          entries: [],
        })
      }
    }

    loadEmails()

    return () => {
      cancelled = true
    }
  }, [onSessionExpired, sessionId])

  useEffect(() => {
    if (!emailsState.entries.length) {
      setActiveEntryKey('')
      setActiveEmailKey('')
      return
    }

    if (!activeEntryKey || !emailsState.entries.some((entry) => entry.key === activeEntryKey)) {
      setActiveEntryKey(emailsState.entries[0].key)
    }
  }, [activeEntryKey, emailsState.entries])

  const activeEntry =
    emailsState.entries.find((entry) => entry.key === activeEntryKey) || emailsState.entries[0] || null

  useEffect(() => {
    if (!activeEntry?.emails?.length) {
      setActiveEmailKey('')
      return
    }

    if (!activeEmailKey || !activeEntry.emails.some((email) => email.key === activeEmailKey)) {
      setActiveEmailKey(activeEntry.emails[0].key)
    }
  }, [activeEmailKey, activeEntry])

  const activeEmail =
    activeEntry?.emails?.find((email) => email.key === activeEmailKey) || activeEntry?.emails?.[0] || null

  return (
    <div className="absolute inset-x-0 top-6 z-40 mx-auto w-full max-w-5xl rounded-[24px] border border-[#d9e2ef] bg-white/95 shadow-[0_24px_60px_rgba(44,62,89,0.16)] backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <div className="text-sm font-semibold uppercase tracking-[0.14em] text-[#556987]">
            Emails
          </div>
          <div className="mt-1 text-xs text-slate-500">
            Review the email threads tied to this PROM result.
          </div>
        </div>
        <button
          type="button"
          aria-label="Close emails"
          onClick={onClose}
          className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
        >
          X
        </button>
      </div>

      <div className="h-[min(72vh,860px)] overflow-hidden p-5">
        {emailsState.isLoading ? (
          <div className="flex h-full items-center justify-center rounded-[20px] border border-slate-200 bg-slate-50 px-6 text-sm text-slate-500">
            Pulling the email threads into view...
          </div>
        ) : emailsState.error ? (
          <div className="flex h-full items-center justify-center rounded-[20px] border border-red-100 bg-red-50/70 px-6 text-center">
            <div>
              <p className="text-base font-semibold text-red-800">Could not load emails.</p>
              <p className="mt-2 text-sm text-red-700">{emailsState.error}</p>
            </div>
          </div>
        ) : emailsState.entries.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-[20px] border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-rose-50 px-6 text-center">
            <div className="max-w-lg">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-100 text-2xl">
                :(
              </div>
              <p className="mt-4 text-lg font-semibold text-slate-900">
                Sorry, we could not find relevant emails for this PROM request.
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                This one showed up without any linked email threads. A lonely little PROM, for now.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex h-full flex-col overflow-hidden rounded-[20px] border border-slate-200 bg-slate-50/70">
            <div className="border-b border-slate-200 bg-white/90 px-4 py-3">
              <div className="flex flex-wrap gap-2">
                {emailsState.entries.map((entry, index) => (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => setActiveEntryKey(entry.key)}
                    className={[
                      'rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors',
                      entry.key === activeEntry?.key
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    {entry.requestTitle || `PROM ${index + 1}`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5">
              <article className="mx-auto max-w-4xl rounded-[18px] border border-slate-200 bg-white px-6 py-5 shadow-sm">
                <div className="mb-4 border-b border-slate-100 pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        {activeEntry?.requestTitle}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Entry ID {activeEntry?.entryId}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {activeEntry?.emails?.map((email) => (
                      <button
                        key={email.key}
                        type="button"
                        onClick={() => setActiveEmailKey(email.key)}
                        className={[
                          'rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors',
                          email.key === activeEmail?.key
                            ? 'border-red-200 bg-red-50 text-red-700'
                            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                        ].join(' ')}
                      >
                        {email.label}
                      </button>
                    ))}
                  </div>
                </div>
                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 text-slate-700">
                  {activeEmail?.rawThread}
                </pre>
              </article>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function App() {
  const isLogoutPath = window.location.pathname === '/logout'
  const isExpiredPath = window.location.pathname === '/chat/expired'
  const isForbiddenPath = window.location.pathname === '/chat/forbidden'
  const isTestChatPath = window.location.pathname === '/test-chat-page'
  const [view, setView] = useState('search') // 'search' | 'upload'
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [isThinking, setIsThinking] = useState(false)
  const [searchMode, setSearchMode] = useState('all')
  const [activeComposerTab, setActiveComposerTab] = useState('')
  const [activePanel, setActivePanel] = useState('')
  const [promFilename, setPromFilename] = useState('')
  const [attachedPromTitles, setAttachedPromTitles] = useState([])
  const [attachedProms, setAttachedProms] = useState([])
  const [attachedPromSessionId, setAttachedPromSessionId] = useState(() => getSessionIdFromPath(window.location.pathname))
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [hasUserSession, setHasUserSession] = useState(true)
  const [isCheckingUserSession, setIsCheckingUserSession] = useState(true)
  const [isCreatingUserSession, setIsCreatingUserSession] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(() => getSessionIdFromPath(window.location.pathname))

  const setAttachedPromsForSession = (sessionId, nextProms) => {
    setAttachedProms(nextProms)
    setAttachedPromSessionId(sessionId)
    setAttachedPromTitles(nextProms.map((item) => item.title).filter(Boolean))
    setPromFilename(nextProms[0]?.prom_filename || '')
  }

  const attachPromsForSession = (sessionId, proms) => {
    if (!sessionId || !Array.isArray(proms) || !proms.length) return
    setAttachedProms((prev) => {
      const next = [...prev]
      for (const prom of proms) {
        if (!next.some((item) => item.id === prom.id)) {
          next.push(prom)
        }
      }
      setAttachedPromTitles(next.map((item) => item.title).filter(Boolean))
      if (!promFilename && next[0]?.prom_filename) {
        setPromFilename(next[0].prom_filename)
      }
      return next
    })
    setAttachedPromSessionId(sessionId)
  }

  const handleSessionState = (response) => {
    const redirectedToExpired =
      response.redirected &&
      response.url &&
      new URL(response.url, window.location.origin).pathname === '/chat/expired'
    const redirectedToForbidden =
      response.redirected &&
      response.url &&
      new URL(response.url, window.location.origin).pathname === '/chat/forbidden'

    if (response.status === 401) {
      window.location.assign('/auth/saml/login')
      return true
    }
    if (redirectedToExpired) {
      window.location.replace('/chat/expired')
      return true
    }
    if (response.status === 403 || redirectedToForbidden) {
      window.location.replace('/chat/forbidden')
      return true
    }
    return false
  }

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

  const streamEmbedResponse = async (endpoint, text, onChunk, entryId = null) => {
    const body = { text }
    if (entryId !== null && entryId !== undefined) {
      body.entry_id = entryId
    }
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (handleSessionState(response)) {
      throw new Error('Session expired')
    }

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
    if (isLogoutPath || isExpiredPath || isForbiddenPath || isTestChatPath) return

    const checkUserSession = async () => {
      try {
        const response = await fetch('/user/status', {
          method: 'GET',
          credentials: 'include',
        })

        if (handleSessionState(response)) return

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
  }, [isExpiredPath, isForbiddenPath, isLogoutPath, isTestChatPath])

  useEffect(() => {
    const handlePopState = () => {
      setCurrentSessionId(getSessionIdFromPath(window.location.pathname))
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (!currentSessionId) {
      setAttachedProms([])
      setAttachedPromSessionId(null)
      setAttachedPromTitles([])
      setPromFilename('')
      return
    }

    const storedProms = readAttachedPromsFromStorage(currentSessionId)
    if (!storedProms.length && attachedPromSessionId === currentSessionId && attachedProms.length) {
      return
    }
    setAttachedProms(storedProms)
    setAttachedPromSessionId(currentSessionId)
    setAttachedPromTitles(storedProms.map((item) => item.title).filter(Boolean))
    setPromFilename(storedProms[0]?.prom_filename || '')
  }, [currentSessionId])

  useEffect(() => {
    if (!currentSessionId) return
    writeAttachedPromsToStorage(currentSessionId, attachedProms)
  }, [attachedProms, currentSessionId])

  useEffect(() => {
    if (isLogoutPath || isExpiredPath || isForbiddenPath || isTestChatPath || !currentSessionId) return

    const rehydrateChat = async () => {
      try {
        const response = await fetch(`/api/session/${currentSessionId}`, {
          method: 'GET',
          credentials: 'include',
        })

        if (handleSessionState(response)) return

        if (!response.ok) {
          throw new Error(`Rehydrate request failed: ${response.status}`)
        }

        const contextHistory = await response.json()
        console.log("[rehydrate] raw context payload:", contextHistory)
        if (!Array.isArray(contextHistory)) {
          setMessages([])
          return
        }

        const rehydratedMessages = []
        contextHistory.forEach((entry, idx) => {
          if (entry?.user_text) {
            rehydratedMessages.push({
              id: `rehydrate-user-${idx}`,
              role: 'user',
              text: String(entry.user_text),
              isStreaming: false,
            })
          }
          if (entry?.assistant_text) {
            rehydratedMessages.push({
              id: `rehydrate-assistant-${idx}`,
              role: 'assistant',
              text: String(entry.assistant_text),
              isStreaming: false,
            })
          }
        })

        console.log("[rehydrate] mapped message count:", rehydratedMessages.length)
        setMessages(rehydratedMessages)
      } catch (error) {
        console.error('Rehydrate request error:', error)
      }
    }

    rehydrateChat()
  }, [currentSessionId, isExpiredPath, isForbiddenPath, isLogoutPath, isTestChatPath])

  if (isLogoutPath) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-600">
        Signing out...
      </div>
    )
  }

  if (isExpiredPath) {
    return (
      <div className="min-h-screen flex flex-col bg-gradient-to-b from-slate-50 to-slate-100">
        <Header view={view} setView={setView} hasUserSession={hasUserSession} onLogout={handleLogout} />
        <main className="flex-1 flex items-center justify-center px-4">
          <div className="w-full max-w-2xl bg-white shadow-lg shadow-slate-200/50 border border-slate-200 rounded-2xl p-8 sm:p-10">
            <div className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-red-700 bg-red-50 border border-red-100 px-3 py-1 rounded-full">
              Session Expired
            </div>
            <h1 className="mt-4 text-4xl font-semibold text-slate-800 tracking-tight">
              Your chat took a coffee break and never came back.
            </h1>
            <p className="mt-4 text-base text-slate-700 leading-7">
              Your chat session expired from inactivity. We are in beta right now, and we plan to move
              chat storage to PostgreSQL so your context can be preserved long-term.
            </p>
            
            <button
              type="button"
              onClick={() => window.location.replace('/')}
              className="mt-6 px-4 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors"
            >
              Return Home
            </button>
          </div>
        </main>
        <Footer />
      </div>
    )
  }

  if (isForbiddenPath) {
    return (
      <div className="min-h-screen flex flex-col bg-gradient-to-b from-slate-50 to-slate-100">
        <Header view={view} setView={setView} hasUserSession={hasUserSession} onLogout={handleLogout} />
        <main className="flex-1 flex items-center justify-center px-4">
          <div className="w-full max-w-2xl bg-white shadow-lg shadow-slate-200/50 border border-slate-200 rounded-2xl p-8 sm:p-10">
            <div className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-amber-700 bg-amber-50 border border-amber-100 px-3 py-1 rounded-full">
              Access Denied
            </div>
            <h1 className="mt-4 text-4xl font-semibold text-slate-800 tracking-tight">
              That chat was not yours to reopen.
            </h1>
            <p className="mt-4 text-base text-slate-700 leading-7">
              You tried to access a chat session that does not belong to your account, so the app blocked
              the request.
            </p>
            <p className="mt-3 text-sm text-slate-600 leading-6">
              Return home and start from search to open a chat that belongs to your current session.
            </p>
            <button
              type="button"
              onClick={() => window.location.replace('/')}
              className="mt-6 px-4 py-2.5 rounded-xl bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 transition-colors"
            >
              Return Home
            </button>
          </div>
        </main>
        <Footer />
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

      if (response.status === 401) {
        const data = await response.json().catch(() => null)
        const detail = data?.detail
        if (
          detail &&
          typeof detail === 'object' &&
          detail.error === 'saml_required' &&
          typeof detail.login_path === 'string'
        ) {
          window.location.assign(detail.login_path)
          return
        }
      }

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

  async function handleLogout() {
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

    if (handleSessionState(response)) {
      throw new Error('Session expired')
    }

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
      // Fast path: create a session + return top match so we can immediately stream chat (no "Chat" click).
      const response = await fetch('/search/start', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })

      if (handleSessionState(response)) return

      if (!response.ok) {
        console.error('Search request failed:', response.status)
        return
      }

      const data = await response.json()
      const {
        session_id: sessionId,
        entry_id: entryId,
        query: echoedQuery,
        prom_filename: nextPromFilename,
        request_title: requestTitle,
      } = data || {}
      if (!sessionId || entryId === undefined || entryId === null) {
        console.error('Search start did not return session_id/entry_id:', data)
        return
      }

      setAttachedPromsForSession(sessionId, [
        {
          id: entryId,
          title: requestTitle || 'Untitled PROM',
          prom_filename: nextPromFilename || '',
        },
      ])
      setCurrentSessionId(sessionId)
      window.history.pushState({}, '', `/session/${sessionId}`)

      // Show the user query as the user message.
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
          role: 'user',
          text: echoedQuery || trimmed,
        },
      ])
      setQuery('')

      setIsThinking(true)
      const assistantId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
      let firstChunkReceived = false
      const streamEndpoint = getStreamEndpoint(sessionId, searchMode)

      await streamEmbedResponse(
        streamEndpoint,
        echoedQuery || trimmed,
        (chunk) => {
          if (!firstChunkReceived) {
            firstChunkReceived = true
            setIsThinking(false)
          }
          appendAssistantChunk(assistantId, chunk)
        },
        entryId
      )
      finalizeAssistantMessage(assistantId)
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

      const endpoint = getStreamEndpoint(sessionId)

      await streamEmbedResponse(endpoint, result.title, (chunk) => {
        if (!firstChunkReceived) {
          firstChunkReceived = true
          setIsThinking(false)
        }
        appendAssistantChunk(assistantId, chunk)
      }, result.id)
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
      const endpoint = getStreamEndpoint(currentSessionId)

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

  const handleAddContextProms = async (results) => {
    if (!currentSessionId || !Array.isArray(results) || !results.length) return

    const response = await fetch(`/add/context/${currentSessionId}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entry_ids: results.map((result) => result.id),
      }),
    })

    if (handleSessionState(response)) {
      throw new Error('Session expired')
    }

    if (!response.ok) {
      throw new Error(`Add context failed: ${response.status}`)
    }

    attachPromsForSession(
      currentSessionId,
      results.map((result) => ({
        id: result.id,
        title: result.title || 'Untitled PROM',
        prom_filename: result.prom_filename || '',
      })),
    )
  }

  const hasMessages = messages.length > 0 || Boolean(currentSessionId)
  const testChatMessages = messages.length > 0 ? messages : TEST_CHAT_SEED_MESSAGES
  const promFiles = attachedProms
    .filter((item) => item && item.prom_filename)
    .map((item) => ({
      key: `${item.id}:${item.prom_filename}`,
      label: item.title || item.prom_filename,
      fileName: item.prom_filename,
      fileUrl: `/files/retrieve_files?file_name=${encodeURIComponent(item.prom_filename)}`,
    }))
  const composerTabs = [
    {
      key: 'PROM',
      label: 'PROM',
      isActive: activeComposerTab === 'PROM',
      onClick: async () => {
        setActiveComposerTab('PROM')
        if (!promFiles.length) {
          console.warn('PROM tab clicked before prom_filename was set.')
          return
        }
        setActivePanel('PROM')
      },
    },
    {
      key: 'emails',
      label: 'emails',
      isActive: activeComposerTab === 'emails',
      onClick: async () => {
        setActiveComposerTab('emails')
        setActivePanel('emails')
      },
    },
  ]

  const sendTestChatMessage = async (text) => {
    if (currentSessionId) {
      await sendChatMessage(text)
      return
    }

    const trimmed = text.trim()
    if (!trimmed) return

    const idBase = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    setMessages((prev) => [
      ...prev,
      {
        id: `test-user-${idBase}`,
        role: 'user',
        text: trimmed,
        isStreaming: false,
      },
      {
        id: `test-assistant-${idBase}`,
        role: 'assistant',
        text: 'Presentation route response: this page is using the live chat UI shell with demo content layered underneath the PROM and emails panels.',
        isStreaming: false,
      },
    ])
    setQuery('')
  }

  if (isTestChatPath) {
    return (
      <div className="min-h-screen flex flex-col bg-gradient-to-b from-slate-50 to-slate-100">
        <Header view={view} setView={setView} hasUserSession={true} onLogout={handleLogout} />
        <main className="flex-1 flex flex-col px-4 py-6">
          <TestChatPage
            messages={testChatMessages}
            query={query}
            setQuery={setQuery}
            onSend={sendTestChatMessage}
            isThinking={isThinking}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
          />
        </main>
        <Footer />
      </div>
    )
  }

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
              ? 'items-stretch py-6 min-h-0'
              : 'items-center justify-center py-12'
        }`}
      >
        {view === 'upload' ? (
          <UploadPromPage />
        ) : hasMessages ? (
          <div className="relative flex-1 min-h-0">
            <div
              className={[
                'h-full transition-all duration-200',
                activePanel ? 'pointer-events-none select-none blur-[5px]' : '',
              ].join(' ')}
              aria-hidden={Boolean(activePanel)}
            >
              <ChatView
                messages={messages}
                query={query}
                setQuery={setQuery}
                onSend={sendChatMessage}
                isThinking={isThinking}
                searchMode={searchMode}
                setSearchMode={setSearchMode}
                composerTabs={composerTabs}
                attachedPromTitles={attachedPromTitles}
                attachedPromIds={attachedProms.map((p) => p.id)}
                sessionId={currentSessionId}
                onAddContextProms={handleAddContextProms}
              />
            </div>

            {activePanel === 'PROM' ? (
              <FileViewerModal
                title="PROM"
                files={promFiles}
                onClose={() => {
                  setActivePanel('')
                  setActiveComposerTab('')
                }}
              />
            ) : null}

            {activePanel === 'emails' ? (
              <EmailViewerModal
                sessionId={currentSessionId}
                onSessionExpired={handleSessionState}
                onClose={() => {
                  setActivePanel('')
                  setActiveComposerTab('')
                }}
              />
            ) : null}
          </div>
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
