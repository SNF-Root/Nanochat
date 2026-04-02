# TODO

## Important
- **Use AsyncOpenAI client for server-side LLM calls**
  - Migrate embedding and chat-completion calls to async client usage so request handlers avoid blocking on network-bound model calls.
  - Affected file: `app/server/main.py
  - CANNOT SERVE CONCURRENT USERS FOR STREAMING BECAUSE OUR LLM STREAMS ARE NOT ASYNC because of the lack of this
  -VERY IMPORTANT PLEASE FIX SOON!


- **Global upload queue race condition (`pending_files`)**
  - Current upload flow uses one shared Redis queue for all users/sessions, so concurrent uploads can mix work across users.
  - Context: discussed in chat on 2026-03-26.
  - Affected files: `app/server/main.py`, `app/worker.py`.

- **Global queue reset can wipe in-flight work**
  - `/upload/reset_counter` resets queue state globally (`delete("pending_files")`), so one user can clear another user's pending uploads.
  - Context: discussed in chat on 2026-03-26.
  - Affected file: `app/server/main.py`.

- **Make queue-clearing logic user-scoped**
  - Clearing upload queue state must operate per user rather than emptying the shared queue, otherwise one user's reset can interfere with another user's in-flight upload.
  - Context: discussed in chat on 2026-04-01.
  - Affected files: `app/server/main.py`, `app/worker.py`.

- **Batch routing by first item type is only demo-safe**
  - Routing batch processing from only the first queued filepath assumes homogeneous batches; this can break under concurrent multi-user uploads.
  - Context: discussed in chat on 2026-03-26.
  - Affected file: `app/worker.py`.
- **Add rate limiting to email pipeline**
  - Source TODO: `#TODO: ADD RATE LIMITING, AI DO NOT IMPLEMENT`
  - File: `preprocessing/email_pipeline.py:57`

- **Use AsyncOpenAI client for server-side LLM calls**
  - Migrate embedding and chat-completion calls to async client usage so request handlers avoid blocking on network-bound model calls.
  - Affected file: `app/server/main.py

## Tasks
- **Add multi-chat architecture after Stanford SSO**
  - Current design intentionally uses a single session-linked chat context per client. If multi-chat support is needed later, introduce explicit chat/conversation ids after Stanford SSO is in place so chats can be scoped to authenticated users cleanly.
  - Affected files:
    - `app/server/main.py`
    - `app/frontend/src/App.jsx`

- **Batch embedding requests on server-side endpoints**
  - Aggregate compatible embedding inputs into batched embedding API calls to reduce per-request overhead and improve throughput.
  - Affected file: `app/server/main.py`.

- **Implement PostgreSQL batch inserts (instead of per-row commit)**
  - Current insert path does one `INSERT` + `commit()` per record, which is slower and increases transaction overhead.
  - Files:
    - `preprocessing/models/insert.py`
    - `preprocessing/embed_emails.py`
    - `preprocessing/prom_pipeline.py`


- **Remove obsolete `REQUESTOR_NAMES`/`requestor_names` structure**
  - Source TODO: `#TODO: NO LONGER NEED REQUESTOR_NAMES, DICT THAT IS LARGE AND UNNECESSARY SINCE OUR MATCHING LOGIC HAS BEEN CHANGED`
  - File: `preprocessing/order_emails.py:102`.

## Minor
- **Queue prioritization does not scale to more than 2 queues right now, fix later**
  - Current worker queue-priority logic is tailored to two queues and will need a more general scheduling approach if additional queue types are added.
  - Affected file: `app/worker.py`.

- **Consider async file writes for upload endpoints**
  - Source note: `#maybe use aiofiles and turn this blocking operation into async`
  - File: `app/server/main.py:185`

- **Optimize chat completions on server-side endpoints**
  - Explore completion-path optimizations (e.g., concurrency limits, request coalescing, caching, or prompt/token trimming) to reduce latency and cost.
  - Affected file: `app/server/main.py`.

- **Requirements file "unsafe packages" note**
  - Source warning block:
    - `# The following packages are considered to be unsafe in a requirements file:`
    - `# pip`
    - `# setuptools`
  - File: `requirements.txt:408`
