from typing import Dict, List, Set
import json
import uuid
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from typing import AsyncGenerator, Optional, Tuple
from openai import AsyncOpenAI
from preprocessing.database.pg import get_db_connection
from .prompts import (
    ALL_SYSTEM_PROMPT,
    CONTINUATION_SYS_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    prom_prompt,
)
from .models.server_classes import EmbedRequest, EmbedResponse, SearchResponse, SearchResult, UploadCounterResetResponse, UploadFileResponse, FileObject
import os


EMBEDDING_MODEL = "text-embedding-ada-002"
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.2")


USER_COOKIE = "user_id"
SESSION_TTL_SECONDS = 60 * 60 * 24 

VALID_PROM_UPLOAD_EXTENSIONS = [".pdf", ".docx"]
VALID_EMAIL_UPLOAD_EXTENSIONS = [".txt"]


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "uploaded_files"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await clear_all_user_keys()
        clear_uploaded_files_dir() 


app = FastAPI(lifespan=lifespan)
redis_chat_context = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
redis_file_queue = redis.Redis(host="redis", port=6379, db=1)
redis_uids_sids = redis.Redis(host="redis", port=6379, db=2)
redis_file_status_store = redis.Redis(host="redis", port=6379, db=3, decode_responses=True)


#called only on server shutdown
async def clear_all_user_keys() -> int:
    deleted_count = 0
    async for key in redis_uids_sids.scan_iter():
        deleted_count += await redis_uids_sids.delete(key)
    async for key in redis_file_queue.scan_iter():
        await redis_file_queue.delete(key)
    print(f"[DEBUG] Cleared {deleted_count} context history keys on shutdown")
    return deleted_count


async def create_user_id(request: Request, response: Response) -> str:
    user_id = uuid.uuid4().hex
    response.set_cookie(
        key=USER_COOKIE,
        value=user_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=False,      
        samesite="lax",
        path="/"
    )
    return user_id



async def create_add_session_id(request: Request, response: Response) -> str:
    user_id = request.cookies.get(USER_COOKIE)
    session_id = uuid.uuid4().hex
    added = await redis_uids_sids.sadd(_user_key(user_id), _session_key(session_id))
    return session_id, added 

async def get_session_ids(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    return await redis_uids_sids.smembers(_user_key(user_id))





#TODO: please change this to an async client for the love of concurrent streaming
def create_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    return AsyncOpenAI(api_key=api_key)



def clear_uploaded_files_dir() -> None:
    try:
        if os.path.isdir(UPLOAD_DIR):
            shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    except Exception as e:
        return f"Could not clear uploaded files {e}"
    

def _user_key(user_id: str) -> str:
    return f"user:{user_id}:session_ids"

def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"


def _upload_status_key(user_id: str) -> str:
    return f"user:upload_file_status:{user_id}"





client = create_openai_client()




#should happen during upon entering home

@app.post("/user/init")
async def set_user_cookie(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    if user_id:
        has_context = True
        sids: Set[str] = await redis_uids_sids.smembers(_user_key(user_id))
        if not sids:
            has_context = False
        print(f"user id {user_id} is {sids}")
        return {
            "created_session": False,
            "has_context": has_context,
            "session_ids" : sids
        }
    user_id = await create_user_id(request, response)
    print("created session id")
    return {
        "created_session": True,
        "has_context": False,
        "session_ids": ()
    }


@app.get("/user/status")
async def user_status(request: Request):
    user_id = request.cookies.get(USER_COOKIE)
    return {
        "has_user": bool(user_id),
    }


@app.post("/session/init")
async def set_session_id(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    if user_id:
        session_id, added = await create_add_session_id(request, response)#needs to be some type of random uuid
        user_session_set = await redis_uids_sids.smembers(_user_key(user_id))
        cleaned_session_id = session_id.removeprefix("chat:session:")
        if not added:
            return {
                "created_user": False,
                "added": False,
                "reason": "Duplicate element exists in set",
                "session_id": None
            }
        return {
            "created_user": False,
            "added" : True,
            "reason": f"Successful add to {user_id} where set is {user_session_set}",
            "session_id": cleaned_session_id
        }
    else:
        user_id = await create_user_id(request, response)
        session_id, added = await create_add_session_id(request, response)
        cleaned_session_id = session_id.removeprefix("chat:session:")
        user_session_set = await redis_uids_sids.smembers(_user_key(user_id))
        return {
            "created_user": True,
            "added" : True,
            "reason": f"Successful add to {user_id} where set is {user_session_set}",
            "session_id": cleaned_session_id
        }



@app.post("/logout")
async def logout(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    if user_id:
        await redis_uids_sids.delete(_user_key(user_id))
    response.delete_cookie(key=USER_COOKIE, path="/")
    return {"ok": True, "logged_out": True}
    



@app.post("/upload/prom", response_model=UploadFileResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
    ) -> UploadFileResponse:
    user_id: str = request.cookies.get(USER_COOKIE)
    safe_filename = os.path.basename(file.filename or "upload.bin")
    stem, ext = os.path.splitext(safe_filename)
    if ext not in VALID_PROM_UPLOAD_EXTENSIONS:
        return JSONResponse(
            status_code = 400,
            content = {
            "filename": file.filename,
            "reason": "Invalid File Format for Email",
            "status": "Rejected",
            })
    unique_suffix = uuid.uuid4().hex[:8]
    stored_filename = f"prom_{stem}__{unique_suffix}{ext}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)
    #maybe use aiofiles and turn this blocking operation into async
    total_file_bytes = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
            total_file_bytes += len(chunk)
    file_obj = FileObject(
        user_id=user_id,
        upload_id=stored_filename,
        kind="prom",
        filepath=filepath,
    )
    print(user_id)
    print(json.dumps(file_obj.model_dump()))
    try:
        queue_len = await redis_file_queue.rpush("pending_prom_files", json.dumps(file_obj.model_dump()))
        print(f"succesfully added to queue with length {queue_len} for {user_id}")
    except Exception as e:
        print(f"cannot push to redis file queue | Error {e}")
    return UploadFileResponse(
        filename=file.filename,
        path = path,
        content_type = file.content_type,
        size_bytes = total_file_bytes,
        status = "Queued"
    )

@app.post("/upload/emails", response_model=UploadFileResponse)
async def upload_email(request:Request, file: UploadFile = File(...), path: str = Form(...)) -> UploadFileResponse:
    user_id: str = request.cookies.get(USER_COOKIE)
    safe_filename = os.path.basename(file.filename or "upload.bin")
    stem, ext = os.path.splitext(safe_filename)
    if ext not in VALID_EMAIL_UPLOAD_EXTENSIONS:
        return JSONResponse(
            status_code = 400,
            content = {
            "filename" : file.filename,
           "reason" : "Invalid File Format for Email",
            "status" : "Rejected"
        })
    unique_suffix = uuid.uuid4().hex[:8]
    stored_filename = f"email_{stem}__{unique_suffix}{ext}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)
    total_file_bytes = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024*1024):
            f.write(chunk)
            total_file_bytes += len(chunk)
    file_obj = FileObject(
        user_id=user_id,
        upload_id=stored_filename,
        kind="email",
        filepath=filepath,
    )
    await redis_file_queue.rpush("pending_email_files", json.dumps(file_obj.model_dump()))
    print("email file pushed to redis queue")

    return UploadFileResponse(
        filename = file.filename,
        path=path,
        content_type="email_threads",
        size_bytes=total_file_bytes,
        status="Queued"
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


@app.get("/upload/get")
async def get_uploads(request: Request):
    user_id = request.cookies.get(USER_COOKIE)
    if not user_id:
        return []
    items = await redis_file_status_store.lrange(_upload_status_key(user_id), 0, -1)
    return [json.loads(item) for item in items]

@app.get("/context/show-list")
async def show_context_list(request: Request):
    # if not user_id:
        #hit them with a redirect
    all_active_sessions = {}

    async for key in redis_uids_sids.scan_iter():
        active_sessions = await redis_uids_sids.smembers(key)
        all_active_sessions[key] = active_sessions
    return all_active_sessions


@app.post("/upload/reset_counter", response_model=UploadCounterResetResponse)
async def reset_upload_counter() -> UploadCounterResetResponse:
    key = "promfile_upload_counter"
    queue_name = "pending_files"
    len_of_queue = await redis_file_queue.llen(queue_name)
    await redis_file_queue.delete(queue_name)
    print(f"{key} set to 0")
    print(f"{queue_name} cleared")
    return UploadCounterResetResponse(number_of_files_cleared=len_of_queue, status_of_queue="cleared") 


async def embed_query(text: str) -> list[float]:
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


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

    
async def stream_chat_completion_and_store(
    session_id: str,
    system_prompt: str,
    user_payload: str,
    request: Request,
    response: Response,
    context_entry: dict,
) -> AsyncGenerator[str, None]:
    full_response_text = ""
    try:
        print(f"[DEBUG] Starting streamed chat completion (model={CHAT_MODEL})...")
        stream = await client.chat.completions.create(
            model=CHAT_MODEL,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.2,
        )
        async for event in stream:
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
                session_id, 
                request,
                response,
                {
                    **context_entry,
                    "assistant_text": full_response_text,
                },
            )


@app.post("/search/all", response_model=SearchResponse)
async def search_emails(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar prom->email1, email2, email3 connections"""
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
                a.entry_id,
                p.request_title,
                1 - (a.prom_embedding <=> %s::vector) AS similarity
            FROM all_embeddings a
            JOIN prom_embeddings p
                ON p.prom_id = a.prom_id
            ORDER BY a.prom_embedding <=> %s::vector
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

@app.post("/session/{session_id}/embed/all/stream")
async def embed_all_stream(session_id: str, payload: EmbedRequest, request: Request, response: Response):

    query = payload.text.strip()
    print(f"[DEBUG][all][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(session_id, request, response)
    if len(context_history) == 0:
        try:
            print("[DEBUG][all][stream] Embedding query...")
            query_embedding = await embed_query(query)
            print(f"[DEBUG][all][stream] Embedding succeeded, dim={len(query_embedding)}")
        except Exception as error:
            print(f"[ERROR][all][stream] Embedding failed: {error}")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {error}") from error

        con = None
        try:
            print("[DEBUG][all][stream] Connecting to database...")
            con = get_db_connection()
            cursor = con.cursor()
            cursor.execute(
                """
                SELECT
                    p.request_title,
                    p.chemicals_and_processes,
                    p.request_reason,
                    p.process_flow,
                    p.amount_and_form,
                    e1.prom_approval AS email_1_prom_approval,
                    e1.prom_considerations AS email_1_prom_considerations,
                    e1.requestor AS email_1_requestor,
                    e1.chemicals AS email_1_chemicals,
                    e1.processes AS email_1_processes,
                    LEFT(e1.raw_thread, 2000) AS email_1_raw_thread,
                    e2.prom_approval AS email_2_prom_approval,
                    e2.prom_considerations AS email_2_prom_considerations,
                    e2.requestor AS email_2_requestor,
                    e2.chemicals AS email_2_chemicals,
                    e2.processes AS email_2_processes,
                    LEFT(e2.raw_thread, 2000) AS email_2_raw_thread,
                    e3.prom_approval AS email_3_prom_approval,
                    e3.prom_considerations AS email_3_prom_considerations,
                    e3.requestor AS email_3_requestor,
                    e3.chemicals AS email_3_chemicals,
                    e3.processes AS email_3_processes,
                    LEFT(e3.raw_thread, 2000) AS email_3_raw_thread,
                    1 - (a.prom_embedding <=> %s::vector) AS similarity
                FROM all_embeddings a
                JOIN prom_embeddings p
                    ON p.prom_id = a.prom_id
                LEFT JOIN email_embeddings e1
                    ON e1.email_id = a.email_id_1
                LEFT JOIN email_embeddings e2
                    ON e2.email_id = a.email_id_2
                LEFT JOIN email_embeddings e3
                    ON e3.email_id = a.email_id_3
                ORDER BY a.prom_embedding <=> %s::vector
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
            request_title,
            chemicals_and_processes,
            request_reason,
            process_flow,
            amount_and_form,
            email_1_prom_approval,
            email_1_prom_considerations,
            email_1_requestor,
            email_1_chemicals,
            email_1_processes,
            email_1_raw_thread,
            email_2_prom_approval,
            email_2_prom_considerations,
            email_2_requestor,
            email_2_chemicals,
            email_2_processes,
            email_2_raw_thread,
            email_3_prom_approval,
            email_3_prom_considerations,
            email_3_requestor,
            email_3_chemicals,
            email_3_processes,
            email_3_raw_thread,
            similarity,
        ) = row

        print(f"[DEBUG][all][stream] Best match: title={request_title}, similarity={similarity:.4f}")

        system_prompt = ALL_SYSTEM_PROMPT
        user_payload = (
            f"USER_QUESTION: {query}\n\n"
            f"REQUEST_TITLE: {request_title}\n"
            f"CHEMICALS_AND_PROCESSES: {chemicals_and_processes}\n"
            f"REQUEST_REASON: {request_reason}\n"
            f"PROCESS_FLOW: {process_flow}\n"
            f"AMOUNT_AND_FORM: {amount_and_form}\n\n"
            f"EMAIL_1_PROM_APPROVAL: {email_1_prom_approval}\n"
            f"EMAIL_1_PROM_CONSIDERATIONS: {email_1_prom_considerations}\n"
            f"EMAIL_1_REQUESTOR: {email_1_requestor}\n"
            f"EMAIL_1_CHEMICALS: {email_1_chemicals}\n"
            f"EMAIL_1_PROCESSES: {email_1_processes}\n"
            f"EMAIL_1_RAW_THREAD_EXCERPT: {email_1_raw_thread}\n\n"
            f"EMAIL_2_PROM_APPROVAL: {email_2_prom_approval}\n"
            f"EMAIL_2_PROM_CONSIDERATIONS: {email_2_prom_considerations}\n"
            f"EMAIL_2_REQUESTOR: {email_2_requestor}\n"
            f"EMAIL_2_CHEMICALS: {email_2_chemicals}\n"
            f"EMAIL_2_PROCESSES: {email_2_processes}\n"
            f"EMAIL_2_RAW_THREAD_EXCERPT: {email_2_raw_thread}\n\n"
            f"EMAIL_3_PROM_APPROVAL: {email_3_prom_approval}\n"
            f"EMAIL_3_PROM_CONSIDERATIONS: {email_3_prom_considerations}\n"
            f"EMAIL_3_REQUESTOR: {email_3_requestor}\n"
            f"EMAIL_3_CHEMICALS: {email_3_chemicals}\n"
            f"EMAIL_3_PROCESSES: {email_3_processes}\n"
            f"EMAIL_3_RAW_THREAD_EXCERPT: {email_3_raw_thread}\n"
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



async def append_context_entry(session_id: str, request: Request, response: Response, entry: dict) -> str:
    key = _session_key(session_id)
    raw_context = await redis_chat_context.get(key)
    context_history = json.loads(raw_context) if raw_context else []
    context_history.append(entry)
    await redis_chat_context.set(key, json.dumps(context_history), ex=SESSION_TTL_SECONDS)
    return session_id

async def get_context(session_id: str, request: Request, response: Response):
    key = _session_key(session_id)
    raw_context = await redis_chat_context.get(key)
    context_history = json.loads(raw_context) if raw_context else []
    return context_history 

# async def context_length(request: Request, response: Response) -> int:
#     session_id = await get_or_create_session_id(request, response)
#     key = _session_key(session_id)
#     raw_context = await redis_chat_context.get(key)
#     context_history = json.loads(raw_context) if raw_context else []
#     return len(context_history)redis_uids_cids: Dic = 


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
