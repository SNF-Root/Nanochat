
# IMPORTANT
- Add rate limiting to email pipeline

- Source TODO: #TODO: ADD RATE LIMITING, AI DO NOT IMPLEMENT
- File: preprocessing/email_pipeline.py:57
- Tasks

# Fix Chat Response formatting
 - Super clunky, too much all at once. 
 - Format with spacing, headers, no emojis, potentially in container JS formatting for lists, etc
 - JSON format from the model to then process on the JS side, potentially error bound
 - Highlight what file it comes from better


## Tasks

# Need to finish failure upload notification system portion
  - Complete the failure-path upload status notifications so the frontend can reflect worker-side processing failures alongside success states.
  - Affected files: app/worker.py, app/server/main.py, app/frontend/src/components/UploadPromPage.jsx.
# Batch embedding requests on server-side endpoints
  - Aggregate compatible embedding inputs into batched embedding API calls to reduce per-request overhead and improve throughput.
  - Affected file: app/server/main.py.
# Implement PostgreSQL batch inserts (instead of per-row commit)
  - Current insert path does one INSERT + commit() per record, which is slower and increases transaction overhead.
- Files:
- preprocessing/models/insert.py
- preprocessing/embed_emails.py
- preprocessing/prom_pipeline.py


## Minor
- **Queue prioritization does not scale to more than 2 queues right now, fix later**
  - Current worker queue-priority logic is tailored to two queues and will need a more general scheduling approach if additional queue types are added.
  - Affected file: `app/worker.py`.

- **Optimize chat completions on server-side endpoints**
  - Explore completion-path optimizations (e.g., concurrency limits, request coalescing, caching, or prompt/token trimming) to reduce latency and cost.
  - Affected file: `app/server/main.py`.

- **Make queue-clearing logic user-scoped**
  - Clearing upload queue state must operate per user rather than emptying the shared queue, otherwise one user's reset can interfere with another user's in-flight upload.
 - Remove both from queue, and also remove from DATABASE, going to need USER_SESSION_ID as col, TIMESTAMP (assumption that deletion that happens during upload requires the insertions to be pretty recent. there is no remove the data button anywhere else).
- Queue, clear can only happen during insertion. In order to remove insertion into the DB;
- Context: discussed in chat on 2026-04-01.
  - Affected files: `app/server/main.py`, `app/worker.py`.

- **Make a third table**
  - Omniti

- **SQL Injection
  - Clearing up