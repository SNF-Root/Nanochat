import SearchSection from './SearchSection'

function sanitizeMarkdownForDisplay(text) {
  return text.replace(/^(#{4,})\s+/gm, '### ')
}

function renderInlineMarkdown(text, keyPrefix) {
  const nodes = []
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let lastIndex = 0
  let match
  let index = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }

    const token = match[0]
    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong key={`${keyPrefix}-strong-${index}`} className="font-semibold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      )
    } else if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(
        <code
          key={`${keyPrefix}-code-${index}`}
          className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-slate-800"
        >
          {token.slice(1, -1)}
        </code>
      )
    }

    lastIndex = pattern.lastIndex
    index += 1
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes
}

function renderMarkdown(text) {
  console.log('Rendering markdown for completed assistant message')
  const lines = sanitizeMarkdownForDisplay(text).split('\n')
  const blocks = []
  let paragraphLines = []
  let listType = null
  let listItems = []
  let codeBlockLines = []
  let inCodeBlock = false

  const flushParagraph = () => {
    if (!paragraphLines.length) return
    const paragraphText = paragraphLines.join(' ').trim()
    if (paragraphText) {
      blocks.push(
        <p key={`p-${blocks.length}`} className="leading-7">
          {renderInlineMarkdown(paragraphText, `p-${blocks.length}`)}
        </p>
      )
    }
    paragraphLines = []
  }

  const flushList = () => {
    if (!listItems.length || !listType) return
    const ListTag = listType === 'ol' ? 'ol' : 'ul'
    const listClassName =
      listType === 'ol' ? 'list-decimal space-y-1 pl-5' : 'list-disc space-y-1 pl-5'

    blocks.push(
      <ListTag key={`list-${blocks.length}`} className={listClassName}>
        {listItems.map((item, index) => (
          <li
            key={`item-${index}`}
            style={item.indentLevel > 0 ? { marginLeft: `${item.indentLevel * 1.25}rem` } : undefined}
          >
            {renderInlineMarkdown(item.text, `list-${blocks.length}-${index}`)}
          </li>
        ))}
      </ListTag>
    )

    listType = null
    listItems = []
  }

  const flushCodeBlock = () => {
    if (!codeBlockLines.length) return
    blocks.push(
      <pre
        key={`code-${blocks.length}`}
        className="overflow-x-auto rounded-xl bg-slate-900 px-4 py-3 text-sm leading-6 text-slate-100"
      >
        <code>{codeBlockLines.join('\n')}</code>
      </pre>
    )
    codeBlockLines = []
  }

  lines.forEach((line) => {
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      flushParagraph()
      flushList()
      if (inCodeBlock) {
        flushCodeBlock()
        inCodeBlock = false
      } else {
        inCodeBlock = true
      }
      return
    }

    if (inCodeBlock) {
      codeBlockLines.push(line)
      return
    }

    if (!trimmed) {
      flushParagraph()
      flushList()
      return
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      const level = headingMatch[1].length
      const headingText = headingMatch[2]
      const className =
        level === 1
          ? 'text-xl font-semibold text-slate-900'
          : level === 2
            ? 'text-lg font-semibold text-slate-900'
            : 'text-base font-semibold text-slate-900'
      const HeadingTag = `h${level}`
      blocks.push(
        <HeadingTag key={`heading-${blocks.length}`} className={className}>
          {renderInlineMarkdown(headingText, `heading-${blocks.length}`)}
        </HeadingTag>
      )
      return
    }

    const leadingWhitespace = line.match(/^\s*/)?.[0].length ?? 0
    const indentLevel = Math.floor(leadingWhitespace / 2)

    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      flushParagraph()
      if (listType && listType !== 'ol') flushList()
      listType = 'ol'
      listItems.push({ text: orderedMatch[1], indentLevel })
      return
    }

    const unorderedMatch = trimmed.match(/^[-*]\s+(.*)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (listType && listType !== 'ul') flushList()
      listType = 'ul'
      listItems.push({ text: unorderedMatch[1], indentLevel })
      return
    }

    if (listType) {
      flushList()
    }
    paragraphLines.push(trimmed)
  })

  flushParagraph()
  flushList()
  if (inCodeBlock) {
    flushCodeBlock()
  }

  return blocks.length ? blocks : text
}

function ChatView({ messages, query, setQuery, onSend, isThinking, searchMode, setSearchMode }) {
  return (
    <div className="flex-1 w-full max-w-4xl mx-auto flex flex-col">
      <div className="flex-1 overflow-y-auto space-y-4 pb-6">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm sm:text-base break-words [overflow-wrap:anywhere] ${
                message.role === 'user'
                  ? 'bg-red-500 text-white'
                  : 'bg-slate-50 text-slate-700 border border-transparent'
              }`}
            >
              {message.role === 'assistant' && !message.isStreaming ? (
                <div className="space-y-3 break-words [overflow-wrap:anywhere]">{renderMarkdown(message.text)}</div>
              ) : message.role === 'assistant' ? (
                <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{message.text}</div>
              ) : (
                <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{message.text}</div>
              )}
            </div>
          </div>
        ))}

        {isThinking && (
          <div className="flex justify-start">
            <div className="px-4 py-3 text-sm text-slate-400 italic animate-pulse">
              Thinking...
            </div>
          </div>
        )}
      </div>

      <div className="pt-2 flex justify-center">
        <SearchSection query={query} setQuery={setQuery} onSearch={onSend} searchMode={searchMode} setSearchMode={setSearchMode} />
      </div>
    </div>
  )
}

export default ChatView
