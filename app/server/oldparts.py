async def chat_completion(system_prompt: str, user_payload: str) -> str:
    """Send a system + user message to the LLM and return the response text."""
    print(f"[DEBUG] Sending to chat completion (model={CHAT_MODEL})...")  
    completion = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        temperature=0.2,
    )
    response_text = completion.choices[0].message.content or ""
    print(f"[DEBUG] Chat completion succeeded, response length: {len(response_text)}")
    return response_text.strip() or "No summary returned."




@app.post("/session/{session_id}/embed/proms/stream")
async def embed_proms_stream(session_id: str, payload: EmbedRequest, request: Request, response: Response):
    query = payload.text.strip()
    print(f"[DEBUG][proms][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(session_id, request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][proms][stream] Embedding query...")
            query_embedding = await embed_query(query)
            print(f"[DEBUG][proms][stream] Embedding succeeded, dim={len(query_embedding)}")
        except Exception as error:
            print(f"[ERROR][proms][stream] Embedding failed: {error}")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {error}") from error

        con = None
        try:
            print("[DEBUG][proms][stream] Connecting to database...")
            con = get_db_connection()
            cursor = con.cursor()
            cursor.execute(
                """
                SELECT
                    request_title,
                    chemicals_and_processes,
                    request_reason,
                    process_flow,
                    amount_and_form,
                    1 - (request_embedding <=> %s::vector) AS similarity
                FROM prom_embeddings
                ORDER BY request_embedding <=> %s::vector
                LIMIT 1
                """,
                (query_embedding, query_embedding),
            )
            row = cursor.fetchone()
            print(f"[DEBUG][proms][stream] DB query done. Row found: {row is not None}")
        except Exception as error:
            print(f"[ERROR][proms][stream] DB query failed: {error}")
            raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
        finally:
            if con is not None:
                con.close()

        if row is None:
            async def no_prom_results():
                text = "No relevant PROM requests found."
                await append_context_entry(
                    session_id,
                    request,
                    response,
                    {
                        "route": "embed_proms_stream",
                        "user_text": query,
                        "assistant_text": text,
                    },
                )
                yield text

            return StreamingResponse(no_prom_results(), media_type="text/plain")

        (
            request_title, chemicals_and_processes, request_reason,
            process_flow, amount_and_form, similarity,
        ) = row

        print(f"[DEBUG][proms][stream] Best match: title={request_title}, similarity={similarity:.4f}")

        system_prompt = prom_prompt(request_title or "Untitled Request")
        user_payload = (
            f"USER_QUESTION: {query}\n\n"
            f"REQUEST_TITLE: {request_title}\n"
            f"CHEMICALS_AND_PROCESSES: {chemicals_and_processes}\n"
            f"REQUEST_REASON: {request_reason}\n"
            f"PROCESS_FLOW: {process_flow}\n"
            f"AMOUNT_AND_FORM: {amount_and_form}\n"
        )
    else:
        system_prompt = CONTINUATION_SYS_PROMPT
        user_payload = json.dumps(
            {
                "current_user_message": query,
                "context_history": context_history,
            }
        )

    stream = stream_chat_completion_and_store(
        session_id,
        system_prompt=system_prompt,
        user_payload=user_payload,
        request=request,
        response=response,
        context_entry={
            "route": "embed_proms_stream",
            "user_text": query,
        },
    )
    return StreamingResponse(stream, media_type="text/plain")



@app.post("/session/{session_id}/embed/emails/stream")
async def embed_emails_stream(session_id: str, payload: EmbedRequest, request: Request, response: Response):

    query = payload.text.strip()
    print(f"[DEBUG][emails][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(session_id, request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][emails][stream] Embedding query...")
            query_embedding = await embed_query(query)
            print(f"[DEBUG][emails][stream] Embedding succeeded, dim={len(query_embedding)}")
        except Exception as error:
            print(f"[ERROR][emails][stream] Embedding failed: {error}")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {error}") from error

        con = None
        try:
            print("[DEBUG][emails][stream] Connecting to database...")
            con = get_db_connection()
            cursor = con.cursor()
            cursor.execute(
                """
                SELECT
                    date,
                    requestor,
                    filename,
                    prom_approval,
                    prom_considerations,
                    chemicals,
                    processes,
                    raw_thread,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM email_embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT 1
                """,
                (query_embedding, query_embedding),
            )
            row = cursor.fetchone()
            print(f"[DEBUG][emails][stream] DB query done. Row found: {row is not None}")
        except Exception as error:
            print(f"[ERROR][emails][stream] DB query failed: {error}")
            raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
        finally:
            if con is not None:
                con.close()

        if row is None:
            async def no_email_results():
                text = "No relevant emails found."
                await append_context_entry(
                    session_id,
                    request,
                    response,
                    {
                        "route": "embed_emails_stream",
                        "user_text": query,
                        "assistant_text": text,
                    },
                )
                yield text

            return StreamingResponse(no_email_results(), media_type="text/plain")

        (
            date, requestor, filename, prom_approval, prom_considerations,
            chemicals, processes, raw_thread, similarity,
        ) = row

        print(f"[DEBUG][emails][stream] Best match: date={date}, requestor={requestor}, similarity={similarity:.4f}")

        system_prompt = EMAIL_SYSTEM_PROMPT
        user_payload = (
            "USER_QUESTION: Can you give me all the information on the email thread for this raw thread, don't summarize and be descriptive of important details such as considerations, safety concerns. do not give broad answer\n\n"
            "RAW_THREAD:\n"
            f"{raw_thread}\n\n"
            f"PROM_APPROVAL: {prom_approval}\n"
            f"PROM_CONSIDERATIONS: {prom_considerations}\n"
            f"CHEMICALS: {chemicals}\n"
            f"PROCESSES: {processes}\n"
        )
    else:
        system_prompt = CONTINUATION_SYS_PROMPT
        user_payload = json.dumps(
            {
                "current_user_message": query,
                "context_history": context_history,
            }
        )

    stream = stream_chat_completion_and_store(
        session_id,
        system_prompt=system_prompt,
        user_payload=user_payload,
        request=request,
        response=response,
        context_entry={
            "route": "embed_emails_stream",
            "user_text": query,
        },
    )
    return StreamingResponse(stream, media_type="text/plain")


@app.post("/search/emails", response_model=SearchResponse)
async def search_emails(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar email threads (llm_context + similarity)."""
    query = request.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    query_embedding = await embed_query(query)

    con = None
    try:
        con = get_db_connection()
        cursor = con.cursor()
        cursor.execute(
            """
            SELECT
                email_id,
                llm_context,
                1 - (embedding <=> %s::vector) AS similarity
            FROM email_embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT 5
            """,
            (query_embedding, query_embedding),
        )
        rows = cursor.fetchall()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
    finally:
        if con is not None:
            con.close()

    results = [
        SearchResult(id=row[0], title=row[1] or "No context available", similarity=float(row[2]))
        for row in rows
    ]
    return SearchResponse(results=results)


@app.post("/search/proms", response_model=SearchResponse)
async def search_proms(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar PROM requests (title + similarity only)."""
    query = request.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    query_embedding = await embed_query(query)

    con = None
    try:
        con = get_db_connection()
        cursor = con.cursor()
        cursor.execute(
            """
            SELECT
                prom_id,
                request_title,
                1 - (request_embedding <=> %s::vector) AS similarity
            FROM prom_embeddings
            ORDER BY request_embedding <=> %s::vector
            LIMIT 5
            """,
            (query_embedding, query_embedding),
        )
        rows = cursor.fetchall()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
    finally:
        if con is not None:
            con.close()

    results = [
        SearchResult(id=row[0], title=row[1] or "Untitled Request", similarity=float(row[2]))
        for row in rows
    ]
    return SearchResponse(results=results)

