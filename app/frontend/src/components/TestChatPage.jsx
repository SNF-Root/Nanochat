import { useState } from 'react'
import ChatView from './ChatView'

const SAMPLE_EMAIL = {
  from: 'alex.rivera@snf.com',
  to: 'strategy-team@snf.com',
  subject: 'Draft launch narrative for Q3 review',
  date: 'May 13, 2026',
  body: `Hi team,

Attached is the first-pass launch narrative draft. Please focus feedback on clarity, customer framing, and KPI strength before Friday.

Thanks,
Alex`,
}

const PROM_PDF_SRC = '/promForms/ashutoshPROM.pdf'

function TestChatPage({
  messages,
  query,
  setQuery,
  onSend,
  isThinking,
  searchMode,
  setSearchMode,
}) {
  const [activePanel, setActivePanel] = useState('')

  const composerTabs = [
    {
      key: 'PROM',
      label: 'PROM',
      isActive: activePanel === 'PROM',
      onClick: () => setActivePanel('PROM'),
    },
    {
      key: 'emails',
      label: 'emails',
      isActive: activePanel === 'emails',
      onClick: () => setActivePanel('emails'),
    },
  ]

  return (
    <div className="mx-auto flex min-h-[calc(100vh-15rem)] w-full max-w-4xl flex-1 flex-col">
      <div className="relative flex-1">
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
            onSend={onSend}
            isThinking={isThinking}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
            composerTabs={composerTabs}
          />
        </div>

        {activePanel ? (
          <div className="absolute inset-x-0 top-6 z-40 mx-auto w-full max-w-4xl rounded-[24px] border border-[#d9e2ef] bg-white/95 shadow-[0_24px_60px_rgba(44,62,89,0.16)] backdrop-blur-md">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div className="text-sm font-semibold uppercase tracking-[0.14em] text-[#556987]">
                {activePanel}
              </div>
              <button
                type="button"
                aria-label={`Close ${activePanel}`}
                onClick={() => setActivePanel('')}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
              >
                X
              </button>
            </div>

            <div className="h-[min(68vh,860px)] overflow-hidden p-5">
              {activePanel === 'PROM' ? (
                <div className="h-full overflow-hidden rounded-[20px] border border-slate-200 bg-slate-50">
                  <iframe
                    title="Attached PROM PDF"
                    src={PROM_PDF_SRC}
                    className="h-full w-full"
                  />
                </div>
              ) : null}

              {activePanel === 'emails' ? (
                <article className="h-full overflow-y-auto rounded-[20px] border border-slate-200 bg-slate-50 p-5 text-sm text-slate-700 shadow-sm">
                  <div className="grid gap-3 border-b border-slate-200 pb-4">
                    <p>
                      <span className="mr-2 font-semibold text-slate-900">From</span>
                      {SAMPLE_EMAIL.from}
                    </p>
                    <p>
                      <span className="mr-2 font-semibold text-slate-900">To</span>
                      {SAMPLE_EMAIL.to}
                    </p>
                    <p>
                      <span className="mr-2 font-semibold text-slate-900">Subject</span>
                      {SAMPLE_EMAIL.subject}
                    </p>
                    <p>
                      <span className="mr-2 font-semibold text-slate-900">Date</span>
                      {SAMPLE_EMAIL.date}
                    </p>
                  </div>
                  <div className="pt-5">
                    <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#7187a6]">
                      Attached email
                    </p>
                    <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-700">
                      {SAMPLE_EMAIL.body}
                    </p>
                  </div>
                </article>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default TestChatPage
