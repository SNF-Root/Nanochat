## Features I'd like to build before the end of the weekend.

**TODO**

-**Need better logic for switching worker roles**
    - Right now, the worker will just switch back to prom_retry after 10 seconds
    - Let's make this smarter by making it switch when the upload_queue is empty
    - When the event loop switches to the retry_worker, if there is anything in the upload queue switch back to upload_role

-**You don't need the workers to retry the PROMS constantly**
    - You only need to retry the proms when we have new emails
    - Save computational resources, the BLPOP is efficient, constantly zpopping and then checking when there is nothing new to check against is not

-**Have to change retry logic**
    -PROMs without matching emails should be uploaded in to the database immediately.
    -Worker should query PROMs without matching emails using SQL query; Then retry those
    -This allows PROM's to still be queried even if they don't have matching emails; allowing for a larger data store
    -Use a PG lock so that two workers can't claim the same row
-**Worker for .docx -> .pdf**
    -Looks super ugly when rendering .docx
    -Maybe conversion to pdf in pipeline,
    -Since pipeline is enacted by worker processes wont hang server


**In Progress**
- **Create a better embedding strategy**
    - We want to make it so that PROM that have an existing email match in the database must be linked
    - Try to create a 1:1 embed content between PROMs and Emails
    - Look at the performance gains between ada-002 and ada-003
    - Use 2019 folder and 2019 emails as testing zone
    - ZNO Particles : We want that link with thread
        - **Able to get the link**
        - I want to make the LLM response better by giving the proper context to GPT
        - Save the request title of the email in the database and pull that
        - Use LLM context
        - **Update the worker logic**
        - Increasing the sim threshold to 0.85 > 
        - We want it to retry the entries that don't have all emails filled.
- **Update the UI**
    - Allow a user to look for PROMs, attach them as context 
    - Allow them to ask a question as well with those proms
- **Optimize Forward Pass**
    - Use HNSW Index after creating a better embedding strategy
    - Use a pool of SQL connections that requests can just use instead of establishing sql connection every time

- **Track PROM Upload Fails**
    - Will let us manually input the information
    - Option to send to LLM
    - Make sure this only works for Non-Duplicates

- **Fix Duplicate entries**
    - Same req title, same requestor, but different date can cause duplicate entries
    - ON CONFLICT(col1, col2, col3) acts like AND; needs all to be true to apply

