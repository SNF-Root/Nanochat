import os
import json
import uuid
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from typing import AsyncGenerator, Optional
from openai import OpenAI
from preprocessing.database.pg import get_db_connection
from .prompts import (
    CONTINUATION_SYS_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    prom_prompt,
)

EMBEDDING_MODEL = "text-embedding-ada-002"
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")


SESSION_COOKIE = "session_id"
SESSION_TTL_SECONDS = 60 * 60 * 24 



@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await clear_all_context_history_keys()
        clear_uploaded_files_dir()


app = FastAPI(lifespan=lifespan)
redis_memory = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
redis_file_queue = redis.Redis(host="redis", port=6379, db=1)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_openai_client() -> OpenAI:
    api_key = os.getenv("STANFORD_API_KEY")
    if not api_key:
        raise RuntimeError("Missing STANFORD_API_KEY")

    base_url = "https://aiapi-prod.stanford.edu/v1"
    if os.getenv("STANFORD_API_KEY"):
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


client = create_openai_client()


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    text: str


class SearchResult(BaseModel):
    id: int
    title: str
    similarity: float


class SearchResponse(BaseModel):
    results: list[SearchResult]

class UploadRejectedFile(BaseModel):
    filename: str
    reason: str

class UploadFileResponse(BaseModel):
    filename: str
    path: str
    content_type : Optional[str] = None
    size_bytes : int
    status: str

class UploadCounterResetResponse(BaseModel):
    number_of_files_cleared: int
    status_of_queue: str


def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"


async def clear_all_context_history_keys() -> int:
    deleted_count = 0
    async for key in redis_memory.scan_iter(match="chat:session:*", count=100):
        deleted_count += await redis_memory.delete(key)
    print(f"[DEBUG] Cleared {deleted_count} context history keys on shutdown")
    return deleted_count


async def get_or_create_session_id(request: Request, response: Response) -> str:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        return session_id

    session_id = uuid.uuid4().hex
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=False,      
        samesite="lax",
        path="/",
    )
    return session_id




@app.get("/session/init")
async def home(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE)
    # if not session_id:
    #     session_id = await get_or_create_session_id(request, response)
    #     print("created session id")
    if session_id:
        await redis_memory.delete(_session_key(session_id))
        response.delete_cookie(key=SESSION_COOKIE, path = "/")
    session_id = await get_or_create_session_id(request, response)
    print("created session id")
    return {
        "ok": True,
        "has_session": True,
        "has_context": False
    }


# @app.get("/logout")
# async def logout(request: Request, response: Response):
#     session_id = request.cookies.get(SESSION_COOKIE)
#     if session_id:
#         await redis_memory.delete(_session_key(session_id))
#     response.delete_cookie(key=SESSION_COOKIE, path="/")
#     return {"ok": True, "logged_out": True}
    





VALID_PROM_UPLOAD_EXTENSIONS = [".pdf", ".docx"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "uploaded_files"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

def clear_uploaded_files_dir() -> None:
    if os.path.isdir(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)




@app.post("/upload/prom", response_model=UploadFileResponse)
async def upload_file(
    file: UploadFile = File(...),
    path: str = Form(...)
) -> UploadFileResponse:
    safe_filename = os.path.basename(file.filename or "upload.bin")
    stem, ext = os.path.splitext(safe_filename)
    unique_suffix = uuid.uuid4().hex[:8]
    stored_filename = f"prom_{stem}__{unique_suffix}{ext}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)
    #maybe use aiofiles and turn this blocking operation into async
    total_file_bytes = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
            total_file_bytes += len(chunk)
    await redis_file_queue.rpush("pending_prom_files", filepath)

    return UploadFileResponse(
        filename=file.filename,
        path = path,
        content_type = file.content_type,
        size_bytes = total_file_bytes,
        status = "queued"
    )

@app.post("/upload/emails", response_model=UploadFileResponse)
async def upload_email(file: UploadFile = File(...), path: str = Form(...)) -> UploadFileResponse:
    safe_filename = os.path.basename(file.filename or "upload.bin")
    stem, ext = os.path.splitext(safe_filename)
    unique_suffix = uuid.uuid4().hex[:8]
    stored_filename = f"email_{stem}__{unique_suffix}{ext}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)
    total_file_bytes = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024*1024):
            f.write(chunk)
            total_file_bytes += len(chunk)
    await redis_file_queue.rpush("pending_email_files", filepath)
    print("email file pushed to redis queue")

    return UploadFileResponse(
        filename = file.filename,
        path=path,
        content_type="email_threads",
        size_bytes=total_file_bytes,
        status="queued"
    )


@app.get("/upload/show-list")
async def show_list():
    prom_data_items = await redis_file_queue.lrange("pending_prom_files", 0, -1)
    emails_data_items = await redis_file_queue.lrange("pending_email_files", 0, -1)
    return_obj = {
        "prom_data_files": prom_data_items,
        "queued_email_files": emails_data_items
    }
    return return_obj


@app.get("/context/show-list")
async def show_context_list(request: Request):
    print(
        "[TRACE][/context/show-list]",
        {
            "referer": request.headers.get("referer"),
            "origin": request.headers.get("origin"),
            "user_agent": request.headers.get("user-agent"),
            "session_cookie_in": request.cookies.get(SESSION_COOKIE),
        },
    )
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return {
            "has_session": False,
            "context_length": 0,
            "context_history": [],
        }

    key = _session_key(session_id)
    raw_context = await redis_memory.get(key)
    context_history = json.loads(raw_context) if raw_context else []
    return {
        "has_session": True,
        "session_id": session_id,
        "context_length": len(context_history),
        "context_history": context_history,
    }

@app.post("/upload/reset_counter", response_model=UploadCounterResetResponse)
async def reset_upload_counter() -> UploadCounterResetResponse:
    key = "promfile_upload_counter"
    queue_name = "pending_files"
    len_of_queue = await redis_file_queue.llen(queue_name)
    await redis_memory.set(key, 0)
    await redis_file_queue.delete(queue_name)
    print(f"{key} set to 0")
    print(f"{queue_name} cleared")
    return UploadCounterResetResponse(number_of_files_cleared=len_of_queue, status_of_queue="cleared") 


def embed_query(text: str) -> list[float]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def chat_completion(system_prompt: str, user_payload: str) -> str:
    """Send a system + user message to the LLM and return the response text."""
    print(f"[DEBUG] Sending to chat completion (model={CHAT_MODEL})...")  
    completion = client.chat.completions.create(
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

    
async def stream_chat_completion_and_store(
    system_prompt: str,
    user_payload: str,
    request: Request,
    response: Response,
    context_entry: dict,
) -> AsyncGenerator[str, None]:
    full_response_text = ""
    try:
        print(f"[DEBUG] Starting streamed chat completion (model={CHAT_MODEL})...")
        stream = client.chat.completions.create(
            model=CHAT_MODEL,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.2,
        )
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content or ""
            if delta:
                full_response_text += delta
                yield delta
    except Exception as error:
        print(f"[ERROR] Streamed chat completion failed: {error}")
        if not full_response_text:
            full_response_text = "Sorry, something went wrong. Please try again."
            yield full_response_text
    finally:
        if full_response_text:
            await append_context_entry(
                request,
                response,
                {
                    **context_entry,
                    "assistant_text": full_response_text,
                },
            )




@app.post("/search/emails", response_model=SearchResponse)
def search_emails(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar email threads (llm_context + similarity)."""
    query = request.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    query_embedding = embed_query(query)

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
def search_proms(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar PROM requests (title + similarity only)."""
    query = request.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    query_embedding = embed_query(query)

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


@app.post("/embed/emails", response_model=EmbedResponse)
async def embed_emails(payload: EmbedRequest, request: Request, response: Response) -> EmbedResponse:
    query = payload.text.strip()
    print(f"[DEBUG][emails] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")
    context_history = await get_context(request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][emails] Embedding query...")
            query_embedding = embed_query(query)
            print(f"[DEBUG][emails] Embedding succeeded, dim={len(query_embedding)}")
        except Exception as error:
            print(f"[ERROR][emails] Embedding failed: {error}")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {error}") from error

        con = None
        try:
            print("[DEBUG][emails] Connecting to database...")
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
            print(f"[DEBUG][emails] DB query done. Row found: {row is not None}")
        except Exception as error:
            print(f"[ERROR][emails] DB query failed: {error}")
            raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
        finally:
            if con is not None:
                con.close()

        if row is None:
            return EmbedResponse(text="No relevant emails found.")

        (
            date, requestor, filename, prom_approval, prom_considerations,
            chemicals, processes, raw_thread, similarity,
        ) = row

        print(f"[DEBUG][emails] Best match: date={date}, requestor={requestor}, similarity={similarity:.4f}")

        user_payload = (
            "USER_QUESTION: Can you give me all the information on the email thread for this raw thread, don't summarize and be descriptive of important details such as considerations, safety concerns. do not give broad answer\n\n"
            "RAW_THREAD:\n"
            f"{raw_thread}\n\n"
            f"PROM_APPROVAL: {prom_approval}\n"
            f"PROM_CONSIDERATIONS: {prom_considerations}\n"
            f"CHEMICALS: {chemicals}\n"
            f"PROCESSES: {processes}\n"
        )

        try:
            response_text = chat_completion(EMAIL_SYSTEM_PROMPT, user_payload)
        except Exception as error:
            print(f"[ERROR][emails] Chat completion failed: {error}")
            raise HTTPException(status_code=500, detail=f"Chat completion failed: {error}") from error
    else:
        try:
            continuation_payload = {
                "current_user_message": query,
                "context_history": context_history,
            }
            response_text = chat_completion(
                CONTINUATION_SYS_PROMPT,
                json.dumps(continuation_payload),
            )
        except Exception as e:
            print(f"[ERROR][emails] Chat continuation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Chat continuation failed: {e}") from e

    await append_context_entry(
        request,
        response,
        {
            "route": "embed_emails",
            "user_text": query,
            "assistant_text": response_text,
        },
    )

    return EmbedResponse(text=response_text)


@app.post("/embed/emails/stream")
async def embed_emails_stream(payload: EmbedRequest, request: Request, response: Response):
    query = payload.text.strip()
    print(f"[DEBUG][emails][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][emails][stream] Embedding query...")
            query_embedding = embed_query(query)
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



async def append_context_entry(request: Request, response: Response, entry: dict) -> str:
    session_id = await get_or_create_session_id(request, response)
    key = _session_key(session_id)
    raw_context = await redis_memory.get(key)
    context_history = json.loads(raw_context) if raw_context else []
    context_history.append(entry)
    await redis_memory.set(key, json.dumps(context_history), ex=SESSION_TTL_SECONDS)
    return session_id

async def get_context(request: Request, response: Response):
    session_id = await get_or_create_session_id(request, response)
    key = _session_key(session_id)
    raw_context = await redis_memory.get(key)
    context_history = json.loads(raw_context) if raw_context else []
    return context_history

# async def context_length(request: Request, response: Response) -> int:
#     session_id = await get_or_create_session_id(request, response)
#     key = _session_key(session_id)
#     raw_context = await redis_memory.get(key)
#     context_history = json.loads(raw_context) if raw_context else []
#     return len(context_history)




@app.post("/embed/proms", response_model=EmbedResponse)
async def embed_proms(payload: EmbedRequest, request: Request, response: Response) -> EmbedResponse:
    query = payload.text.strip()
    print(f"[DEBUG][proms] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")
    context_history = await get_context(request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][proms] Embedding query...")
            query_embedding = embed_query(query)
            print(f"[DEBUG][proms] Embedding succeeded, dim={len(query_embedding)}")
        except Exception as error:
            print(f"[ERROR][proms] Embedding failed: {error}")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {error}") from error

        con = None
        try:
            print("[DEBUG][proms] Connecting to database...")
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
            print(f"[DEBUG][proms] DB query done. Row found: {row is not None}")
        except Exception as error:
            print(f"[ERROR][proms] DB query failed: {error}")
            raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
        finally:
            if con is not None:
                con.close()

        if row is None:
            return EmbedResponse(text="No relevant PROM requests found.")

        (
            request_title, chemicals_and_processes, request_reason,
            process_flow, amount_and_form, similarity,
        ) = row

        print(f"[DEBUG][proms] Best match: title={request_title}, similarity={similarity:.4f}")

        user_payload = (
            f"USER_QUESTION: {query}\n\n"
            f"REQUEST_TITLE: {request_title}\n"
            f"CHEMICALS_AND_PROCESSES: {chemicals_and_processes}\n"
            f"REQUEST_REASON: {request_reason}\n"
            f"PROCESS_FLOW: {process_flow}\n"
            f"AMOUNT_AND_FORM: {amount_and_form}\n"
        )
        

        try:
            response_text = chat_completion(
                prom_prompt(request_title or "Untitled Request"),
                user_payload,
            )
        except Exception as error:
            print(f"[ERROR][proms] Chat completion failed: {error}")
            raise HTTPException(status_code=500, detail=f"Chat completion failed: {error}") from error
    else:
        try:
            continuation_payload = {
                "current_user_message": query,
                "context_history": context_history,
            }
            response_text = chat_completion(
                CONTINUATION_SYS_PROMPT,
                json.dumps(continuation_payload),
            )
        except Exception as e:
            print(f"[ERROR][proms] Chat continuation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Chat continuation failed: {e}") from e
    

    await append_context_entry(
        request,
        response,
        {
            "route": "embed_proms",
            "user_text": query,
            "assistant_text": response_text,
        },
    )

    return EmbedResponse(text=response_text)


@app.post("/embed/proms/stream")
async def embed_proms_stream(payload: EmbedRequest, request: Request, response: Response):
    query = payload.text.strip()
    print(f"[DEBUG][proms][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][proms][stream] Embedding query...")
            query_embedding = embed_query(query)
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
