## TODO
 **Merge with SAML**
  - Make sure all endpoints require SAML Auth
  - Merge with current worker code

 **Replace shared worker DB connection with pooled ownership**
  - Current workers still share a global synchronous Postgres connection, while some helper functions open their own connections ad hoc.
  - Rework DB access so worker tasks borrow connections from a pool with clearer ownership, then revisit async Postgres migration later.
  - Affected files: `app/worker.py`, `preprocessing/models/insert.py`, DB access layer.

 **Come prep-prepared with uploaded files**
  - Upload the data from the drive
  - Come with this next week
  - use new stanford api key

## Minor

- **Hyper-optimize email→PROM matching for `all_embeddings`**
  - Update the email extraction system prompt so `chemicals_mentioned` captures broader material/entity terms (e.g., nanoparticles), not only strict chemical names.
  - Expand `processes_mentioned` to include fabrication steps, machine/tool mentions, and process-equipment context when explicitly present.
  - Refocus `llm_context` to concise subject-matter context centered on the actual request topic (example: ZnO nanoparticles), instead of generic filler.
  - Redesign email `embedded_string` format to align structurally and semantically with PROM embed strings to improve nearest-neighbor quality.
  - Re-evaluate similarity threshold and top-k behavior in `find_email_matches` after prompt/string changes; validate match precision on known PROM-email pairs.
  - Affected files: `preprocessing/embed_emails.py`, `preprocessing/models/insert.py`, `app/worker.py`, PROM-to-email evaluation flow.

- **Revisit `llm_context` inside email embedding string**
  - Current email matching embeds `llm_context` alongside the extracted request, chemicals, and processes.
  - This may be diluting PROM-to-email similarity because `llm_context` is model-generated enrichment rather than direct thread evidence.
  - Test variants that remove or reduce `llm_context` and rely more on `prom_request`, `prom_considerations`, `chemicals`, and `processes`.
  - Affected files: `preprocessing/embed_emails.py`, PROM-to-email matching path.

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
- **Queue prioritization does not scale to more than 2 queues right now, fix later**
  - Current worker queue-priority logic is tailored to two queues and will need a more general scheduling approach if additional queue types are added.
  - Affected file: `app/worker.py`.

- **Retry ownership is process-local and breaks on worker restart**
  - Current retry ownership for `prom_retry_ids` relies on in-memory worker state (`inserted_prom_ids`), which is lost if a worker crashes/restarts.
  - Move ownership/claim tracking to Redis (shared state) so retry processing and `ZREM` behavior remain correct across worker restarts.
  - Affected file: `app/worker.py`.

- **Queue prioritization does not scale to more than 2 queues right now, fix later**
  - Current worker queue-priority logic is tailored to two queues and will need a more general scheduling approach if additional queue types are added.
  - Affected file: `app/worker.py`.

- **Optimize chat completions on server-side endpoints**
  - Explore completion-path optimizations (e.g., concurrency limits, request coalescing, caching, or prompt/token trimming) to reduce latency and cost.
  - Affected file: `app/server/main.py`.

-
