import { useEffect, useRef, useState } from 'react'
import Header from './components/Header'
import Footer from './components/Footer'
import ChatView from './components/ChatView'
import UploadPromPage from './components/UploadPromPage'
import TestChatPage from './components/TestChatPage'
import FileViewerModal from './components/FileViewerModal'
import HomepageHero from './components/HomepageHero'

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

const AGENT_RETRIEVAL_ERROR_TEXT = 'Nano is not feeling well right now, please try again with a similar query.'

function getSessionIdFromPath(pathname) {
  const match = pathname.match(/^\/session\/([^/]+)$/)
  return match ? match[1] : null
}

function getAgentRetrievalEndpoint(sessionId) {
  return `/session/${sessionId}/agent/retrieval`
}

function getAgentRetrievalLimitFinalizeEndpoint(sessionId) {
  return `/session/${sessionId}/agent/retrieval/finalize_limit`
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function getAttachedPromsStorageKey(sessionId) {
  return `retrieved_entries:${sessionId}`
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

function parseRawEmailThread(rawThread) {
  const raw = String(rawThread || '').trim()
  if (!raw) return []

  const parts = raw.split(/\n-{20,}\nMSGID:\s*([^\n]+)\n-{20,}\n/g)
  if (parts.length < 3) {
    return [{ id: 'email-message-1', label: 'Message 1', body: raw }]
  }

  const messages = []
  for (let index = 1; index < parts.length; index += 2) {
    const msgid = parts[index]?.trim()
    const body = parts[index + 1]?.trim()
    if (!body) continue
    messages.push({
      id: msgid || `email-message-${messages.length + 1}`,
      label: `Message ${messages.length + 1}`,
      msgid,
      body,
    })
  }

  return messages.length ? messages : [{ id: 'email-message-1', label: 'Message 1', body: raw }]
}

function EmailViewerModal({
  sessionId,
  selectedEntry,
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
      if (selectedEntry?.raw_thread) {
        setEmailsState({
          isLoading: false,
          error: '',
          entries: [{
            key: `${selectedEntry.table}:${selectedEntry.row_id}`,
            entryId: selectedEntry.row_id,
            requestTitle: selectedEntry.request_title || 'Email thread',
            emails: [{
              key: 'email_1',
              label: 'Email',
              rawThread: selectedEntry.raw_thread,
            }],
          }],
        })
        return
      }

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
  }, [onSessionExpired, selectedEntry, sessionId])

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
  const activeEmailMessages = parseRawEmailThread(activeEmail?.rawThread)

  return (
    <div className="absolute inset-x-0 top-6 z-40 mx-auto w-full max-w-5xl rounded-[1.1rem] border border-[rgba(43,38,32,0.18)] bg-[rgba(245,241,232,0.96)] shadow-[0_28px_80px_rgba(43,38,32,0.28)] backdrop-blur-[8px]">
      <div className="flex items-center justify-between border-b border-[rgba(43,38,32,0.14)] px-6 py-5">
        <div>
          <div className="font-['IBM_Plex_Mono'] text-[0.82rem] font-semibold uppercase tracking-[0.24em] text-[rgba(43,38,32,0.68)]">
            Emails
          </div>
          <div className="mt-1 font-['IBM_Plex_Mono'] text-[0.68rem] uppercase tracking-[0.12em] text-[rgba(43,38,32,0.46)]">
            Retrieved thread
          </div>
        </div>
        <button
          type="button"
          aria-label="Close emails"
          onClick={onClose}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.42)] font-['IBM_Plex_Mono'] text-sm font-semibold text-[rgba(43,38,32,0.72)] transition-colors hover:bg-[rgba(255,255,255,0.72)]"
        >
          X
        </button>
      </div>

      <div className="h-[min(72vh,860px)] overflow-hidden p-6">
        {emailsState.isLoading ? (
          <div className="flex h-full items-center justify-center rounded-[0.9rem] border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.42)] px-6 font-['IBM_Plex_Mono'] text-sm uppercase tracking-[0.16em] text-[rgba(43,38,32,0.52)]">
            Pulling the email threads into view...
          </div>
        ) : emailsState.error ? (
          <div className="flex h-full items-center justify-center rounded-[0.9rem] border border-[#b96c5b]/25 bg-[#f3d8cf]/45 px-6 text-center">
            <div>
              <p className="font-['IBM_Plex_Mono'] text-sm font-semibold uppercase tracking-[0.16em] text-[#9a2f24]">Could not load emails.</p>
              <p className="mt-2 text-sm text-[#9a2f24]">{emailsState.error}</p>
            </div>
          </div>
        ) : emailsState.entries.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-[0.9rem] border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.42)] px-6 text-center">
            <div className="max-w-lg">
              <p className="font-['IBM_Plex_Mono'] text-sm font-semibold uppercase tracking-[0.16em] text-[var(--snf-ink)]">
                Sorry, we could not find relevant emails for this PROM request.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex h-full flex-col overflow-hidden rounded-[0.9rem] border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.32)]">
            <div className="border-b border-[rgba(43,38,32,0.12)] bg-[rgba(255,255,255,0.24)] px-4 py-3">
              <div className="flex flex-wrap gap-2">
                {emailsState.entries.map((entry, index) => (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => setActiveEntryKey(entry.key)}
                    className={[
                      "max-w-full truncate rounded-[0.35rem] border px-3 py-1.5 font-['IBM_Plex_Mono'] text-xs font-semibold uppercase tracking-[0.1em] transition-colors",
                      entry.key === activeEntry?.key
                        ? 'border-[var(--snf-ink)] bg-[var(--snf-ink)] text-[rgba(245,241,232,0.95)]'
                        : 'border-[rgba(43,38,32,0.16)] bg-[rgba(255,255,255,0.38)] text-[rgba(43,38,32,0.72)] hover:bg-[rgba(255,255,255,0.7)]',
                    ].join(' ')}
                  >
                    {entry.requestTitle || `PROM ${index + 1}`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-6 [scrollbar-color:rgba(43,38,32,0.22)_transparent] [scrollbar-width:thin]">
              <article className="mx-auto max-w-4xl rounded-[0.8rem] border border-[#b79a4b] bg-[#dec77f] px-6 py-5 shadow-[0_10px_22px_rgba(43,38,32,0.16)]">
                <div className="mb-5 border-b border-[rgba(43,38,32,0.14)] pb-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[1rem] font-semibold leading-snug text-[var(--snf-ink)]">
                        {activeEntry?.requestTitle}
                      </p>
                      <p className="mt-2 font-['IBM_Plex_Mono'] text-[0.68rem] uppercase tracking-[0.12em] text-[rgba(43,38,32,0.54)]">
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
                          "rounded-[0.35rem] border px-3 py-1.5 font-['IBM_Plex_Mono'] text-xs font-semibold uppercase tracking-[0.1em] transition-colors",
                          email.key === activeEmail?.key
                            ? 'border-[var(--snf-ink)] bg-[var(--snf-ink)] text-[rgba(245,241,232,0.95)]'
                            : 'border-[rgba(43,38,32,0.16)] bg-[rgba(255,255,255,0.32)] text-[rgba(43,38,32,0.72)] hover:bg-[rgba(255,255,255,0.55)]',
                        ].join(' ')}
                      >
                        {email.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-5">
                  {activeEmailMessages.map((message) => (
                    <section
                      key={message.id}
                      className="rounded-[0.65rem] border border-[rgba(43,38,32,0.16)] bg-[rgba(245,241,232,0.72)] px-5 py-4"
                    >
                      <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-[rgba(43,38,32,0.12)] pb-3">
                        <span className="rounded-[0.35rem] border border-[rgba(43,38,32,0.14)] bg-[rgba(255,255,255,0.3)] px-3 py-1 font-['IBM_Plex_Mono'] text-xs font-semibold uppercase tracking-[0.1em] text-[rgba(43,38,32,0.72)]">
                          {message.label}
                        </span>
                        {message.msgid ? (
                          <span className="min-w-0 truncate font-mono text-[0.72rem] text-[rgba(43,38,32,0.42)]">
                            {message.msgid}
                          </span>
                        ) : null}
                      </div>
                      <pre className="whitespace-pre-wrap break-words font-sans text-[0.95rem] leading-7 text-[rgba(43,38,32,0.78)]">
                        {message.body}
                      </pre>
                    </section>
                  ))}
                </div>
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
  const isTestChatPath = window.location.pathname === '/test-chat-page'
  const [view, setView] = useState('search') // 'search' | 'upload'
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [isThinking, setIsThinking] = useState(false)
  const [searchMode, setSearchMode] = useState('proms')
  const [activePanel, setActivePanel] = useState('')
  const [attachedProms, setAttachedProms] = useState([])
  const [attachedPromSessionId, setAttachedPromSessionId] = useState(() => getSessionIdFromPath(window.location.pathname))
  const [selectedRetrievedEntry, setSelectedRetrievedEntry] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const [agentPhase, setAgentPhase] = useState('idle')
  const [agentSteps, setAgentSteps] = useState([])
  const [hasUserSession, setHasUserSession] = useState(true)
  const [isCheckingUserSession, setIsCheckingUserSession] = useState(true)
  const [isCreatingUserSession, setIsCreatingUserSession] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(() => getSessionIdFromPath(window.location.pathname))
  const skipRehydrateSessionIdsRef = useRef(new Set())

  const setAttachedPromsForSession = (sessionId, nextProms) => {
    setAttachedProms(nextProms)
    setAttachedPromSessionId(sessionId)
  }

  const loadRetrievedEntriesFromBackend = async (sessionId) => {
    if (!sessionId) return []
    const response = await fetch(`/session/${sessionId}/retrieved_entries`, {
      method: 'GET',
      credentials: 'include',
    })
    if (handleSessionExpired(response)) {
      throw new Error('Session expired')
    }
    if (!response.ok) {
      throw new Error(`Retrieved entries request failed: ${response.status}`)
    }
    const data = await response.json()
    const entries = Array.isArray(data) ? data : []
    setAttachedPromsForSession(sessionId, entries)
    return entries
  }

  const handleSessionExpired = (response) => {
    const redirectedToExpired =
      response.redirected &&
      response.url &&
      new URL(response.url, window.location.origin).pathname === '/chat/expired'

    if (response.status === 401 || redirectedToExpired) {
      window.location.replace('/chat/expired')
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

  const handleAgentRetrievalFailure = (assistantId) => {
    setAgentPhase('idle')
    setAgentSteps([])
    setIsThinking(false)
    setIsSearching(false)
    setAssistantText(assistantId, AGENT_RETRIEVAL_ERROR_TEXT)
    finalizeAssistantMessage(assistantId)
  }

  const runAgentRetrieval = async (sessionId, text) => {
    const response = await fetch(getAgentRetrievalEndpoint(sessionId), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })

    if (handleSessionExpired(response)) {
      throw new Error('Session expired')
    }

    if (!response.ok) {
      throw new Error(`Agent retrieval failed: ${response.status}`)
    }

    return response.json()
  }

  const finalizeLimitedAgentRetrieval = async (sessionId, text) => {
    const response = await fetch(getAgentRetrievalLimitFinalizeEndpoint(sessionId), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })

    if (handleSessionExpired(response)) {
      throw new Error('Session expired')
    }

    if (!response.ok) {
      throw new Error(`Agent retrieval finalization failed: ${response.status}`)
    }

    return response.json()
  }

  const runAgentRetrievalFlow = async (sessionId, text, assistantId) => {
    setAgentPhase('thinking')
    setAgentSteps([])
    const seenStepKeys = new Set()
    const maxRounds = 4

    for (let round = 0; round < maxRounds; round += 1) {
      const data = await runAgentRetrieval(sessionId, text)
      const executedSteps = Array.isArray(data.list_of_executed_steps)
        ? data.list_of_executed_steps
        : []

      setAgentPhase('running')
      for (const step of executedSteps) {
        const stepKey = `${round}:${step.step_number}:${step.reason_for_step}`
        if (seenStepKeys.has(stepKey)) continue
        seenStepKeys.add(stepKey)
        setAgentSteps((prev) => [...prev, step])
        await sleep(420)
      }

      if (data.done) {
        setAgentPhase('idle')
        if (Array.isArray(data.retrieved_entries) && data.retrieved_entries.length) {
          setAttachedPromsForSession(sessionId, data.retrieved_entries)
        }
        const finalText = data.text || 'The agent completed retrieval but did not return a final answer.'
        setAssistantText(assistantId, finalText)
        finalizeAssistantMessage(assistantId)
        return finalText
      }

      setAgentPhase('thinking')
      await sleep(350)
    }

    setAgentPhase('thinking')
    const data = await finalizeLimitedAgentRetrieval(sessionId, text)
    setAgentPhase('idle')
    if (Array.isArray(data.retrieved_entries) && data.retrieved_entries.length) {
      setAttachedPromsForSession(sessionId, data.retrieved_entries)
    }
    const fallbackText = data.text || 'The agent searched the data store but could not produce a supported final answer.'
    setAssistantText(assistantId, fallbackText)
    finalizeAssistantMessage(assistantId)
    return fallbackText
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
    if (isLogoutPath || isExpiredPath || isTestChatPath) return

    const checkUserSession = async () => {
      try {
        const response = await fetch('/user/status', {
          method: 'GET',
          credentials: 'include',
        })

        if (handleSessionExpired(response)) return

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
  }, [isExpiredPath, isLogoutPath, isTestChatPath])

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
      setSelectedRetrievedEntry(null)
      return
    }

    const storedProms = readAttachedPromsFromStorage(currentSessionId)
    if (!storedProms.length && attachedPromSessionId === currentSessionId && attachedProms.length) {
      return
    }
    if (storedProms.length) {
      setAttachedPromsForSession(currentSessionId, storedProms)
      return
    }

    loadRetrievedEntriesFromBackend(currentSessionId).catch((error) => {
      console.error('Retrieved entries fallback failed:', error)
      setAttachedPromsForSession(currentSessionId, [])
    })
  }, [currentSessionId])

  useEffect(() => {
    if (!currentSessionId) return
    writeAttachedPromsToStorage(currentSessionId, attachedProms)
  }, [attachedProms, currentSessionId])

  useEffect(() => {
    if (isLogoutPath || isExpiredPath || isTestChatPath || !currentSessionId) return
    if (skipRehydrateSessionIdsRef.current.has(currentSessionId)) {
      skipRehydrateSessionIdsRef.current.delete(currentSessionId)
      return
    }

    const rehydrateChat = async () => {
      try {
        const response = await fetch(`/api/session/${currentSessionId}`, {
          method: 'GET',
          credentials: 'include',
        })

        if (handleSessionExpired(response)) return

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
  }, [currentSessionId, isExpiredPath, isLogoutPath, isTestChatPath])

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

  const createUserSession = async () => {
    setIsCreatingUserSession(true)

    try {
      const response = await fetch('/user/init', {
        method: 'POST',
        credentials: 'include',
      })

      if (handleSessionExpired(response)) return

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

    if (handleSessionExpired(response)) {
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

  const handleSearch = async (searchQuery) => {
    const trimmed = searchQuery.trim()
    if (!trimmed) return

    setIsSearching(true)
    let assistantId = null
    try {
      // Fast path: create a session + return top match so we can immediately stream chat (no "Chat" click).
      const response = await fetch('/search/start', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })

      if (handleSessionExpired(response)) return

      if (!response.ok) {
        console.error('Search request failed:', response.status)
        return
      }

      const data = await response.json()
      const {
        session_id: sessionId,
        query: echoedQuery,
      } = data || {}
      if (!sessionId) {
        console.error('Search start did not return session_id:', data)
        return
      }

      skipRehydrateSessionIdsRef.current.add(sessionId)
      setAttachedPromsForSession(sessionId, [])
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
      assistantId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
      setIsThinking(false)
      await runAgentRetrievalFlow(sessionId, echoedQuery || trimmed, assistantId)
    } catch (error) {
      console.error('Search request error:', error)
      if (assistantId) {
        handleAgentRetrievalFailure(assistantId)
      }
    } finally {
      setIsSearching(false)
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

    try {
      setIsThinking(false)
      await runAgentRetrievalFlow(currentSessionId, trimmed, assistantId)
    } catch (error) {
      console.error('Stream embed request error:', error)
      handleAgentRetrievalFailure(assistantId)
    } finally {
      setIsThinking(false)
    }
  }

  const hasMessages = messages.length > 0 || Boolean(currentSessionId)
  const testChatMessages = messages.length > 0 ? messages : TEST_CHAT_SEED_MESSAGES
  const selectedPromFile = selectedRetrievedEntry?.kind === 'PROM' && currentSessionId
    ? [{
        key: `${selectedRetrievedEntry.table}:${selectedRetrievedEntry.row_id}`,
        label: selectedRetrievedEntry.request_title || 'PROM',
        fileName: selectedRetrievedEntry.filename,
        fileUrl: `/session/${currentSessionId}/retrieve_file?filename=${encodeURIComponent(selectedRetrievedEntry.filename)}`,
      }]
    : []
  const handleRetrievedEntryClick = (entry) => {
    setSelectedRetrievedEntry(entry)
    setActivePanel(entry?.kind === 'EMAIL' ? 'EMAIL' : 'PROM')
  }

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
        'snf-page-grid flex flex-col text-[var(--snf-ink)]',
        view === 'upload' ? 'h-screen overflow-hidden' : 'min-h-screen',
      ].join(' ')}
    >
      {!isCheckingUserSession && !hasUserSession ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[rgba(43,38,32,0.28)] px-4 backdrop-blur-[4px]">
          <div className="w-full max-w-xl rounded-[1rem] border border-[rgba(43,38,32,0.16)] bg-[rgba(245,241,232,0.96)] px-7 py-7 shadow-[0_24px_70px_rgba(43,38,32,0.24)] sm:px-9 sm:py-8">
            <div className="font-['IBM_Plex_Mono'] text-[0.72rem] uppercase tracking-[0.22em] text-[rgba(43,38,32,0.52)]">
              nanochat access
            </div>
            <h2 className="mt-4 font-['IBM_Plex_Mono'] text-[1.65rem] font-semibold leading-tight tracking-[-0.03em] text-[var(--snf-ink)] sm:text-[2rem]">
              Authenticate to continue.
            </h2>
            <p className="mt-3 max-w-md text-[0.98rem] leading-7 text-[rgba(43,38,32,0.68)]">
              Create a user session to search the SNF archive and continue your conversation.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="font-['IBM_Plex_Mono'] text-[0.72rem] uppercase tracking-[0.16em] text-[rgba(43,38,32,0.46)]">
                Required once
              </div>
              <button
                type="button"
                onClick={createUserSession}
                disabled={isCreatingUserSession}
                className="inline-flex w-full items-center justify-center rounded-[0.7rem] bg-[var(--snf-ink)] px-6 py-3.5 font-['IBM_Plex_Mono'] text-[0.82rem] font-semibold uppercase tracking-[0.13em] text-[rgba(245,241,232,0.95)] shadow-[0_14px_28px_rgba(43,38,32,0.18)] transition-all hover:-translate-y-0.5 hover:bg-[#17140f] disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                {isCreatingUserSession ? 'Authenticating' : 'Authenticate'}
              </button>
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
              ? 'items-stretch p-0 min-h-0'
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
                agentPhase={agentPhase}
                agentSteps={agentSteps}
                retrievedEntries={attachedProms}
                onRetrievedEntryClick={handleRetrievedEntryClick}
              />
            </div>

            {activePanel === 'PROM' ? (
              <FileViewerModal
                title="PROM"
                files={selectedPromFile}
                onClose={() => {
                  setActivePanel('')
                  setSelectedRetrievedEntry(null)
                }}
              />
            ) : null}

            {activePanel === 'EMAIL' ? (
              <EmailViewerModal
                sessionId={currentSessionId}
                selectedEntry={selectedRetrievedEntry}
                onSessionExpired={handleSessionExpired}
                onClose={() => {
                  setActivePanel('')
                  setSelectedRetrievedEntry(null)
                }}
              />
            ) : null}
          </div>
        ) : (
          <>
            <HomepageHero
              query={query}
              setQuery={setQuery}
              onSearch={handleSearch}
              searchMode={searchMode}
              setSearchMode={setSearchMode}
              isSearching={isSearching}
            />
          </>
        )}
      </main>

      {view === 'upload' ? null : <Footer />}
    </div>
  )
}

export default App
