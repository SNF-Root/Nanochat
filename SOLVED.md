# SOLVED

# Following issues have been solved

- **Global upload queue race condition (`pending_files`)**
  - Current upload flow uses one shared Redis queue for all users/sessions, so concurrent uploads can mix work across users.
  - Context: discussed in chat on 2026-03-26.
  - Affected files: `app/server/main.py`, `app/worker.py`.

- **Global queue reset can wipe in-flight work**
  - `/upload/reset_counter` resets queue state globally (`delete("pending_files")`), so one user can clear another user's pending uploads.
  - Context: discussed in chat on 2026-03-26.
  - Affected file: `app/server/main.py`.

- **Batch routing by first item type is only demo-safe**
  - Routing batch processing from only the first queued filepath assumes homogeneous batches; this can break under concurrent multi-user uploads.
  - Context: discussed in chat on 2026-03-26.
  - Affected file: `app/worker.py`.

- **Add multi-chat architecture after Stanford SSO**
  - Current design intentionally uses a single session-linked chat context per client. If multi-chat support is needed later, introduce explicit chat/conversation ids after Stanford SSO is in place so chats can be scoped to authenticated users cleanly.
  - Affected files:
    - `app/server/main.py`
    - `app/frontend/src/App.jsx`

- **Remove obsolete `REQUESTOR_NAMES`/`requestor_names` structure**
  - Source TODO: `#TODO: NO LONGER NEED REQUESTOR_NAMES, DICT THAT IS LARGE AND UNNECESSARY SINCE OUR MATCHING LOGIC HAS BEEN CHANGED`
  - File: `preprocessing/order_emails.py:102`.
