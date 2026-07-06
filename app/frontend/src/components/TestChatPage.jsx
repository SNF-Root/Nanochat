import ChatView from './ChatView'

function TestChatPage({
  messages,
  query,
  setQuery,
  onSend,
  isThinking,
  searchMode,
  setSearchMode,
}) {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-15rem)] w-full max-w-4xl flex-1 flex-col">
      <div className="relative flex-1">
        <ChatView
          messages={messages}
          query={query}
          setQuery={setQuery}
          onSend={onSend}
          isThinking={isThinking}
          searchMode={searchMode}
          setSearchMode={setSearchMode}
          retrievedEntries={[]}
        />
      </div>
    </div>
  )
}

export default TestChatPage
