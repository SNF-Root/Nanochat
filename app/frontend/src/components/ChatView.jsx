import { useEffect, useMemo, useRef } from 'react'

function renderExecutedCommand(step) {
  if (step.action_type === 'sql_query' && step.sql_params) {
    const targetColumns = step.sql_params.target_columns || []
    const targetStrings = step.sql_params.target_string || []
    return `SQL search ${step.sql_params.target_table || 'table'} for ${targetStrings.join(', ') || 'matching rows'} -> ${targetColumns.join(', ') || 'columns'}`
  }

  if (step.action_type === 'semantic_search' && step.semantic_params) {
    return `Semantic search ${step.semantic_params.target_table || 'archive'} for "${step.semantic_params.query_str || 'query'}"`
  }

  return 'Preparing retrieval step'
}

function getStepReason(step) {
  return step?.step_reasoning || step?.step_reason || step?.reason_for_step || 'Reasoning through the next retrieval step'
}

function getCommandParts(step, phase) {
  if (!step || phase === 'thinking') {
    return {
      action: 'PLANNING',
      source: 'retrieval route',
      query: 'choosing search strategy',
      status: 'running',
    }
  }

  if (step.action_type === 'semantic_search' && step.semantic_params) {
    return {
      action: 'SEMANTIC SEARCH',
      source: step.semantic_params.target_table || 'archive',
      query: step.semantic_params.query_str || 'query',
      status: Array.isArray(step.query_results) ? `${step.query_results.length} rows` : 'running',
    }
  }

  if (step.action_type === 'sql_query' && step.sql_params) {
    const targetStrings = step.sql_params.target_string || []
    return {
      action: 'SQL',
      source: step.sql_params.target_table || 'table',
      query: targetStrings.join(', ') || step.sql_params.column_to_search_target_string || 'filtered query',
      status: Array.isArray(step.query_results) ? `${step.query_results.length} rows` : 'running',
    }
  }

  return {
    action: 'RETRIEVAL',
    source: 'archive',
    query: renderExecutedCommand(step),
    status: 'running',
  }
}

function renderInlineMarkdown(text, keyPrefix) {
  const nodes = []
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let lastIndex = 0
  let match
  let index = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))

    const token = match[0]
    if (token.startsWith('**')) {
      nodes.push(
        <strong key={`${keyPrefix}-strong-${index}`} className="font-semibold text-[var(--snf-ink)]">
          {token.slice(2, -2)}
        </strong>
      )
    } else {
      nodes.push(
        <code key={`${keyPrefix}-code-${index}`} className="rounded bg-[rgba(43,38,32,0.08)] px-1.5 py-0.5 font-['IBM_Plex_Mono'] text-[0.9em]">
          {token.slice(1, -1)}
        </code>
      )
    }

    lastIndex = pattern.lastIndex
    index += 1
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function renderMarkdown(text) {
  const lines = String(text || '').split('\n')
  const blocks = []
  let paragraph = []
  let listItems = []

  const flushParagraph = () => {
    const value = paragraph.join(' ').trim()
    if (value) {
      blocks.push(
        <p key={`p-${blocks.length}`} className="leading-7">
          {renderInlineMarkdown(value, `p-${blocks.length}`)}
        </p>
      )
    }
    paragraph = []
  }

  const flushList = () => {
    if (!listItems.length) return
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="list-disc space-y-1 pl-5">
        {listItems.map((item, index) => (
          <li key={index}>{renderInlineMarkdown(item, `li-${blocks.length}-${index}`)}</li>
        ))}
      </ul>
    )
    listItems = []
  }

  lines.forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushParagraph()
      flushList()
      return
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      const HeadingTag = `h${Math.min(headingMatch[1].length + 2, 4)}`
      blocks.push(
        <HeadingTag key={`h-${blocks.length}`} className="font-semibold leading-7 text-[var(--snf-ink)]">
          {renderInlineMarkdown(headingMatch[2], `h-${blocks.length}`)}
        </HeadingTag>
      )
      return
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/)
    if (bulletMatch) {
      flushParagraph()
      listItems.push(bulletMatch[1])
      return
    }

    flushList()
    paragraph.push(trimmed)
  })

  flushParagraph()
  flushList()
  return blocks.length ? blocks : text
}

function ResultRack({ retrievedEntries, onRetrievedEntryClick }) {
  const results = useMemo(() => Array.isArray(retrievedEntries) ? retrievedEntries : [], [retrievedEntries])
  return (
    <aside className="sticky top-5 self-start w-full shrink-0 lg:w-[23rem] xl:w-[26rem]">
      <div className="relative min-h-[34rem] bg-[rgba(255,255,255,0.34)] px-5 py-9">
        <div className="absolute left-0 top-0 h-9 w-9 border-l-[4px] border-t-[4px] border-[var(--snf-ink)]" />
        <div className="absolute right-0 top-0 h-9 w-9 border-r-[4px] border-t-[4px] border-[var(--snf-ink)]" />
        <div className="absolute bottom-0 left-0 h-9 w-9 border-b-[4px] border-l-[4px] border-[var(--snf-ink)]" />
        <div className="absolute bottom-0 right-0 h-9 w-9 border-b-[4px] border-r-[4px] border-[var(--snf-ink)]" />

        <div className="font-['IBM_Plex_Mono'] text-[0.7rem] uppercase tracking-[0.22em] text-[rgba(122,108,87,0.78)]">
          {results.length ? `${results.length} retrieved files` : 'retrieved files'}
        </div>

        <div className="mt-8 max-h-[27rem] space-y-5 overflow-y-auto px-1 pt-5 [scrollbar-color:rgba(43,38,32,0.22)_transparent] [scrollbar-width:thin]">
          {results.length ? (
            results.map((result, index) => (
              <button
                key={`${result.table}-${result.row_id}-${index}`}
                type="button"
                onClick={() => onRetrievedEntryClick?.(result)}
                className="relative block w-full rounded-[0.35rem] border border-[#b79a4b] bg-[#dec77f] px-4 py-4 text-left shadow-[0_6px_12px_rgba(43,38,32,0.18)] transition-transform duration-150 hover:-translate-y-2 hover:rotate-[-0.5deg] hover:shadow-[0_12px_22px_rgba(43,38,32,0.22)]"
              >
                <div className="absolute -top-4 left-4 z-10 rounded-t-[0.3rem] border border-b-0 border-[#b79a4b] bg-[#dec77f] px-4 py-1 font-['IBM_Plex_Mono'] text-[0.68rem] uppercase tracking-[0.16em] text-[rgba(43,38,32,0.72)]">
                  {result.kind || 'FILE'}
                </div>
                <h3 className="mt-2 text-[0.92rem] font-semibold leading-snug text-[var(--snf-ink)]">
                  {result.request_title || 'Untitled retrieval'}
                </h3>
                {result.requestor ? (
                  <p className="mt-2 text-[0.78rem] text-[rgba(43,38,32,0.66)]">{result.requestor}</p>
                ) : null}
                {result.date ? (
                  <p className="mt-1 font-['IBM_Plex_Mono'] text-[0.68rem] uppercase tracking-[0.12em] text-[rgba(43,38,32,0.54)]">{result.date}</p>
                ) : null}
              </button>
            ))
          ) : (
            <div className="flex min-h-[24rem] items-center justify-center text-center font-['IBM_Plex_Mono'] text-[0.72rem] uppercase tracking-[0.28em] text-[rgba(122,108,87,0.78)]">
              FILES APPEAR HERE
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

function AgentStatus({ phase, steps }) {
  const latestStep = steps?.[steps.length - 1]
  const command = getCommandParts(latestStep, phase)

  return (
    <div className="flex min-h-[4.7rem] items-center gap-3 rounded-[1rem] bg-[var(--snf-panel)] px-7 font-['IBM_Plex_Mono'] text-[0.92rem] text-[rgba(237,231,219,0.72)] shadow-[0_14px_26px_rgba(43,38,32,0.15)]">
      <span className="text-[1.35rem] text-[var(--snf-accent)]">[</span>
      <span className="rounded-[0.35rem] border border-[rgba(211,160,90,0.5)] bg-[rgba(211,160,90,0.12)] px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[var(--snf-accent)]">
        {command.action}
      </span>
      <span className="text-[rgba(237,231,219,0.45)]">·</span>
      <span className="max-w-[14rem] truncate text-[rgba(237,231,219,0.64)]">{command.source}</span>
      <span className="text-[rgba(237,231,219,0.45)]">·</span>
      <span className="min-w-0 flex-1 truncate text-[rgba(237,231,219,0.88)]">"{command.query}"</span>
      <span className="text-[rgba(237,231,219,0.45)]">·</span>
      <span className="inline-flex gap-1">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--snf-accent)]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--snf-accent)] [animation-delay:160ms]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--snf-accent)] [animation-delay:320ms]" />
      </span>
      <span className="shrink-0 text-[rgba(237,231,219,0.64)]">{command.status}</span>
      <span className="text-[1.35rem] text-[var(--snf-accent)]">]</span>
    </div>
  )
}

function BottomComposer({ query, setQuery, onSend, disabled }) {
  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
  }

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    handleSubmit(event)
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="flex min-h-[4.7rem] items-center gap-4 rounded-[1rem] bg-[var(--snf-panel)] px-7 font-['IBM_Plex_Mono'] text-[1rem] shadow-[0_14px_26px_rgba(43,38,32,0.15)]">
        <span className="text-[1.4rem] text-[var(--snf-accent)]">[</span>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="ask a follow-up question..."
          disabled={disabled}
          className="min-h-[1.7rem] flex-1 resize-none bg-transparent text-[rgba(237,231,219,0.86)] outline-none placeholder:text-[rgba(237,231,219,0.62)] disabled:cursor-not-allowed"
        />
        <span className="text-[1.4rem] text-[var(--snf-accent)]">]</span>
      </div>
    </form>
  )
}

function ChatMessage({ message, isInitialUserMessage }) {
  if (message.role === 'user') {
    return (
      <div className={['flex justify-end', isInitialUserMessage ? 'pt-8' : ''].join(' ')}>
        <div className="mr-2 max-w-[62%] text-right font-['IBM_Plex_Mono'] text-[0.95rem] font-semibold leading-7 text-[rgba(43,38,32,0.9)] [overflow-wrap:anywhere]">
          {message.text}
          <span className="ml-3 text-[var(--snf-accent)]">&lt;</span>
        </div>
      </div>
    )
  }

  return (
    <article className="flex max-w-[76%] gap-3 text-left text-[var(--snf-ink)]">
      <span className="mt-1 shrink-0 font-['IBM_Plex_Mono'] text-[0.95rem] font-semibold text-[var(--snf-accent)]">&gt;</span>
      <div className="space-y-3 text-[1rem] leading-7 [overflow-wrap:anywhere]">
        {renderMarkdown(message.text)}
      </div>
    </article>
  )
}

function ChatView({
  messages,
  query,
  setQuery,
  onSend,
  isThinking,
  agentPhase,
  agentSteps,
  retrievedEntries,
  onRetrievedEntryClick,
}) {
  const scrollRef = useRef(null)
  const isAgentBusy = isThinking || agentPhase === 'thinking' || agentPhase === 'running'

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [messages, agentPhase, agentSteps])

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-[118rem] gap-8 px-8 py-5">
      <ResultRack retrievedEntries={retrievedEntries} onRetrievedEntryClick={onRetrievedEntryClick} />

      <section className="flex min-w-0 flex-1 flex-col">
        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-2 [scrollbar-color:rgba(43,38,32,0.22)_transparent] [scrollbar-width:thin]"
        >
          {messages.map((message, index) => (
            <ChatMessage
              key={message.id}
              message={message}
              isInitialUserMessage={index === 0 && message.role === 'user'}
            />
          ))}

          {isAgentBusy ? (
            <div className="space-y-3 font-['IBM_Plex_Mono'] text-[0.86rem] leading-6 text-[rgba(43,38,32,0.72)]">
              <div className="font-semibold uppercase tracking-[0.16em] text-[rgba(43,38,32,0.58)]">
                <span className="mr-3 text-[var(--snf-accent)]">&gt;</span>
                agent retrieving
              </div>
              <div className="space-y-2 pl-7">
                {agentSteps.length ? (
                  agentSteps.map((step, index) => (
                    <div key={`${step.step_number}-${index}`}>
                      <span className="mr-2 text-[var(--snf-accent)]">&gt;</span>
                      {getStepReason(step)}
                    </div>
                  ))
                ) : (
                  <div>
                    <span className="mr-2 text-[var(--snf-accent)]">&gt;</span>
                    planning retrieval route
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>

        <div className="sticky bottom-0 mt-5 shrink-0 pb-4 pt-2">
          {isAgentBusy ? (
            <AgentStatus phase={agentPhase} steps={agentSteps} />
          ) : (
            <BottomComposer query={query} setQuery={setQuery} onSend={onSend} disabled={isAgentBusy} />
          )}
        </div>
      </section>
    </div>
  )
}

export default ChatView
