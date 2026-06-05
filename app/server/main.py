from typing import Dict, List, Set
import json
import uuid
import shutil
import re
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from typing import AsyncGenerator, Optional, Tuple
from openai import AsyncOpenAI
from .prompts import (
    ALL_SYSTEM_PROMPT,
    CONTINUATION_SYS_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    prom_prompt,
)
from .models.server_classes import (
    EmbedRequest,
    EmbedResponse,
    SearchResponse,
    SearchResult,
    SearchStartResponse,
    UploadCounterResetResponse,
    UploadFileResponse,
    FileObject,
    AddContext
)
from .models.pool_db import init_pool, get_db_connection, release_db_conn, close_all_conns
import os
from datetime import datetime, timezone
import ast


EMBEDDING_MODEL = "text-embedding-ada-002"
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")
STANFORD_BASE_URL = os.getenv("STANFORD_BASE_URL", "https://aiapi-prod.stanford.edu/v1")
DSN = os.getenv("DATABASE_URL", "postgresql://user:user_pw@localhost:5433/appdb")

USER_COOKIE = "user_id"
SESSION_TTL_SECONDS = 60 * 60 * 24 
CHAT_TTL_SECONDS = 60 * 60 * 2

VALID_PROM_UPLOAD_EXTENSIONS = [".pdf", ".docx"]
VALID_EMAIL_UPLOAD_EXTENSIONS = [".txt"]


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "uploaded_files"))
LOG_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "logs"))
SEARCH_LOG_PATH = os.path.join(LOG_DIR, "search_all_queries.log")
CHAT_LOG_PATH = os.path.join(LOG_DIR, "chat_all_queries.log")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        initiated = init_pool(dsn=DSN)
        if initiated is None:
            print("pool of connections did not instantiate")
            return
        yield
    finally:
        await clear_all_user_keys()
        #clear_uploaded_files_dir()
        close_all_conns() 


app = FastAPI(lifespan=lifespan)
redis_chat_context = redis.Redis(host="redis", port=6379, db=0, decode_responses=True)
redis_file_queue = redis.Redis(host="redis", port=6379, db=1)
redis_uids_sids = redis.Redis(host="redis", port=6379, db=2)
redis_file_status_store = redis.Redis(host="redis", port=6379, db=3, decode_responses=True)
redis_prom_retry_ids = redis.Redis(host="redis", port=6379, db=4, decode_responses=True)


#called only on server shutdown
async def clear_all_user_keys() -> int:
    deleted_count = 0
    async for key in redis_uids_sids.scan_iter():
        deleted_count += await redis_uids_sids.delete(key)
    async for key in redis_file_queue.scan_iter():
        await redis_file_queue.delete(key)
    async for key in redis_prom_retry_ids.scan_iter():
        if key is "worker:last_seen_email_id":
            continue
        await redis_prom_retry_ids.delete(key)
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
    session_key = _session_key(session_id)
    added = await redis_uids_sids.sadd(_user_key(user_id), session_key)
    # Initialize chat context key at session creation so first stream call
    # does not look like an expired session.
    await redis_chat_context.set(session_key, json.dumps([]), ex=CHAT_TTL_SECONDS)
    return session_id, added 

async def get_session_ids(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    return await redis_uids_sids.smembers(_user_key(user_id))



def create_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("STANFORD_API_KEY")
    if not api_key:
        raise RuntimeError("Missing STANFORD_API_KEY")

    return AsyncOpenAI(
        api_key=api_key,
        base_url=STANFORD_BASE_URL,
    )



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


def append_log_line(file_path: str, payload: dict) -> None:
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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

#Use an RPUSH here. not just for the atomic lock, but because this is inefficient for no reason
async def append_context_entry(session_id: str, request: Request, response: Response, entry: dict) -> str:
    key = _session_key(session_id)
    raw_context = await redis_chat_context.get(key)
    if raw_context is None:
        return None
    context_history = json.loads(raw_context) if raw_context else []
    context_history.append(entry)
    await redis_chat_context.set(key, json.dumps(context_history), ex=CHAT_TTL_SECONDS)
    return session_id

async def get_context(session_id: str, request: Request, response: Response):
    key = _session_key(session_id)
    raw_context = await redis_chat_context.get(key)
    #check to see if chat_key expired
    if raw_context is None:
        return None
    context_history = json.loads(raw_context) if raw_context else []
    return context_history 


def parse_entry_ids_value(entry_ids_raw):
    if entry_ids_raw is None:
        return []

    try:
        parsed_entry_ids = json.loads(entry_ids_raw)
    except (TypeError, json.JSONDecodeError):
        try:
            parsed_entry_ids = ast.literal_eval(entry_ids_raw)
        except (ValueError, SyntaxError):
            parsed_entry_ids = []

    if isinstance(parsed_entry_ids, int):
        return [parsed_entry_ids]
    if not isinstance(parsed_entry_ids, list):
        return []
    return parsed_entry_ids

async def embed_query(text: str) -> list[float]:
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


    
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


#big security risk here, user may be able to access files we dont want him to access. 
#what if client asked to see .env file, first do auth, then make sure the parent dir is just /upload/
@app.get("/files/retrieve_files", response_class=FileResponse)
def retrieve_file(file_name: str):
    match = re.search(r"[^/\\?#]+(?=$|[?#])", file_name or "")
    base_name = match.group(0) if match else (file_name or "")
    file_path = Path(UPLOAD_DIR) / base_name
    if file_path.suffix != ".docx" and file_path.suffix != ".pdf":
        print("innapropriate file path requested")
        raise HTTPException(status_code=403, detail=f"Forbidden")
    if not file_path.is_file():
        print(f"UPLOAD_DIR is {UPLOAD_DIR}")
        print(file_path)
        print("could not find file path")
        raise HTTPException(status_code=404, detail=f"File {base_name} does not exist on server")
    print(f"Path is {file_path}")
    file_path_suffix = file_path.suffix[1:]
    return FileResponse(
        path = file_path,
        media_type=f"application/{file_path_suffix}",
        filename = base_name,
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, max-age=3600"
        }
    )

@app.get("/emails/retrieve_emails/{session_id}")
async def retrieve_email(session_id: str):
    entry_key = f"chat:session:selected_entry:{session_id}"
    entry_ids_raw = await redis_chat_context.get(entry_key)
    parsed_entry_ids = parse_entry_ids_value(entry_ids_raw)
    if not parsed_entry_ids:
        return {}

    con = None
    return_entries_obj = {}

    try:
        con = get_db_connection()
        cursor = con.cursor()
        for entry_id_raw in parsed_entry_ids:
            entry_id = int(entry_id_raw)
            cursor = con.cursor()
            cursor.execute(
                """
                SELECT
                    p.request_title,
                    e1.raw_thread,
                    e2.raw_thread,
                    e3.raw_thread
                FROM all_embeddings a
                JOIN prom_embeddings p
                    ON p.prom_id = a.prom_id
                LEFT JOIN email_embeddings e1
                    ON e1.email_id = a.email_id_1
                LEFT JOIN email_embeddings e2
                    ON e2.email_id = a.email_id_2
                LEFT JOIN email_embeddings e3
                    ON e3.email_id = a.email_id_3
                WHERE a.entry_id = %s
                LIMIT 1
                """,
                (entry_id,),
            )
            row = cursor.fetchone()
            if row is None:
                continue

            request_title, email_1, email_2, email_3 = row

            return_entries_obj[str(entry_id)] = {
                "entry_id": entry_id,
                "request_title": request_title,
                "email_1": email_1,
                "email_2": email_2,
                "email_3": email_3,
            }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
    finally:
        if con is not None:
            release_db_conn(con=con)

    return return_entries_obj

@app.post("/search/start", response_model=SearchStartResponse)
async def search_all_start(payload: EmbedRequest, request: Request, response: Response):
    """Return the top match plus a fresh session id so the client can immediately start streaming chat."""
    query = payload.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")
    try:
        append_log_line(
            SEARCH_LOG_PATH,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "route": "/search/start",
                "query": query,
            },
        )
    except Exception as error:
        print(f"[WARN] Failed to write start search query log: {error}")

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
                p.filename,
                1 - (a.prom_embedding <=> %s::vector) AS similarity
            FROM all_embeddings a
            JOIN prom_embeddings p
                ON p.prom_id = a.prom_id
            ORDER BY a.prom_embedding <=> %s::vector
            LIMIT 1
            """,
            (query_embedding, query_embedding),
        )
        rows = cursor.fetchall()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
    finally:
        if con is not None:
            release_db_conn(con=con)
    if not rows:
        raise HTTPException(status_code=404, detail="No results found")
    print(rows)
    entry_id = rows[0][0]
    request_title = rows[0][1]
    prom_filename = rows[0][2]
    session_init = await set_session_id(request=request, response=response)
    session_id = session_init.get("session_id") if isinstance(session_init, dict) else None
    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to create chat session")
    entry_id_key = f"chat:session:selected_entry:{session_id}"
    lst_entry_id = [entry_id]
    try: 
        await redis_chat_context.set(entry_id_key, json.dumps(lst_entry_id), ex=CHAT_TTL_SECONDS)
    except Exception as e:
        print("unable to save entry_id_key into redis_chat_context")
        print(e) 
    return {
        "session_id": session_id,
        "entry_id": lst_entry_id[0],
        "prom_filename": prom_filename,
        "query": query,
        "request_title": request_title,
    }

@app.post("/search/all", response_model=SearchResponse)
async def search_all(request: EmbedRequest) -> SearchResponse:
    """Return the top 5 most similar prom->email1, email2, email3 connections"""
    query = request.text.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")
    try:
        append_log_line(
            SEARCH_LOG_PATH,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "route": "/search/all",
                "query": query,
            },
        )
    except Exception as error:
        print(f"[WARN] Failed to write search query log: {error}")

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
                p.filename,
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
            release_db_conn(con=con)

    results = [
        SearchResult(
            id=row[0],
            title=row[1] or "No context available",
            prom_filename=row[2],
            similarity=float(row[3]),
        )
        for row in rows
    ]
    return SearchResponse(results=results)


@app.post("/add/context/{session_id}")
async def add_context(session_id: str, payload: AddContext, request: Request, response: Response):
    entry_ids = [int(entry_id) for entry_id in payload.entry_ids]
    if not entry_ids:
        raise HTTPException(status_code=400, detail="entry_ids is required")

    entry_key = f"chat:session:selected_entry:{session_id}"
    existing_entry_ids = parse_entry_ids_value(await redis_chat_context.get(entry_key))
    merged_entry_ids = list(dict.fromkeys([*existing_entry_ids, *entry_ids]))

    con = None
    attached_context = []
    try:
        con = get_db_connection()
        cursor = con.cursor()
        for entry_id in entry_ids:
            cursor.execute(
                """
                SELECT
                    p.request_title,
                    p.chemicals_and_processes,
                    p.request_reason,
                    p.process_flow,
                    p.amount_and_form,
                    e1.prom_approval AS email_1_prom_approval,
                    LEFT(e1.raw_thread, 2000) AS email_1_raw_thread,
                    e2.prom_approval AS email_2_prom_approval,
                    LEFT(e2.raw_thread, 2000) AS email_2_raw_thread
                FROM all_embeddings a
                JOIN prom_embeddings p
                    ON p.prom_id = a.prom_id
                LEFT JOIN email_embeddings e1
                    ON e1.email_id = a.email_id_1
                LEFT JOIN email_embeddings e2
                    ON e2.email_id = a.email_id_2
                WHERE a.entry_id = %s
                LIMIT 1
                """,
                (entry_id,),
            )
            row = cursor.fetchone()
            if row is None:
                continue

            (
                request_title,
                chemicals_and_processes,
                request_reason,
                process_flow,
                amount_and_form,
                email_1_prom_approval,
                email_1_raw_thread,
                email_2_prom_approval,
                email_2_raw_thread,
            ) = row
            attached_context.append(
                {
                    "entry_id": entry_id,
                    "request_title": request_title,
                    "chemicals_and_processes": chemicals_and_processes,
                    "request_reason": request_reason,
                    "process_flow": process_flow,
                    "amount_and_form": amount_and_form,
                    "email_1_prom_approval": email_1_prom_approval,
                    "email_1_raw_thread_excerpt": email_1_raw_thread,
                    "email_2_prom_approval": email_2_prom_approval,
                    "email_2_raw_thread_excerpt": email_2_raw_thread,
                }
            )
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
    finally:
        if con is not None:
            release_db_conn(con=con)

    await redis_chat_context.set(entry_key, json.dumps(merged_entry_ids), ex=CHAT_TTL_SECONDS)

    if attached_context:
        await append_context_entry(
            session_id,
            request,
            response,
            {
                "route": "add_context",
                "user_text": "Add context",
                "attached_entry_ids": entry_ids,
                "attached_context": attached_context,
            },
        )

    return {
        "ok": True,
        "attached_entry_ids": merged_entry_ids,
        "attached_context_count": len(attached_context),
    }
@app.get("/api/session/{session_id}")
async def rehydrate_chat(session_id: str, request: Request, response: Response):
    context_history = await get_context(session_id, request=request, response=response)
    if context_history is None:
        print("in rehydration chat, and key has expired")
        return RedirectResponse(url="/chat/expired", status_code=307)
    return context_history

@app.get("/session/{session_id}")
async def redirect_rehydrated_chat(session_id: str, request: Request, response: Response):
    return RedirectResponse(url=f"http://localhost:3000/session/{session_id}")


@app.post("/session/{session_id}/embed/all/stream")
async def embed_all_stream(session_id: str, payload: EmbedRequest, request: Request, response: Response):
    query = payload.text.strip()
    entry_id = payload.entry_id
    print(f"[DEBUG][all][stream] Received query: '{query}'")
    try:
        append_log_line(
            CHAT_LOG_PATH,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "route": "/session/{session_id}/embed/all/stream",
                "session_id": session_id,
                "query": query,
            },
        )
    except Exception as error:
        print(f"[WARN] Failed to write chat query log: {error}")
    context_history = await get_context(session_id, request, response)
    if context_history is None:
        print("in stream/embed/all, and key has expired")
        return RedirectResponse(url="/chat/expired", status_code=307)
    if len(context_history) == 0:
        if entry_id is None:
            raise HTTPException(status_code=400, detail="entry_id is required for first chat turn")

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
                    LEFT(e1.raw_thread, 2000) AS email_1_raw_thread,
                    e2.prom_approval AS email_2_prom_approval,
                    LEFT(e2.raw_thread, 2000) AS email_2_raw_thread
                FROM all_embeddings a
                JOIN prom_embeddings p
                    ON p.prom_id = a.prom_id
                LEFT JOIN email_embeddings e1
                    ON e1.email_id = a.email_id_1
                LEFT JOIN email_embeddings e2
                    ON e2.email_id = a.email_id_2
                WHERE a.entry_id = %s
                LIMIT 1
                """,
                (entry_id,),
            )
            row = cursor.fetchone()
            print(f"[DEBUG][emails][stream] DB query done. Row found: {row is not None}")
        except Exception as error:
            print(f"[ERROR][emails][stream] DB query failed: {error}")
            raise HTTPException(status_code=500, detail=f"DB query failed: {error}") from error
        finally:
            if con is not None:
                release_db_conn(con=con)

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
            email_1_raw_thread,
            email_2_prom_approval,
            email_2_raw_thread,
        ) = row
        print(f"[DEBUG][all][stream] Deterministic entry lookup: entry_id={entry_id}, title={request_title}")

        system_prompt = ALL_SYSTEM_PROMPT
        user_payload = (
            f"USER_QUESTION: {query}\n\n"
            f"REQUEST_TITLE: {request_title}\n"
            f"CHEMICALS_AND_PROCESSES: {chemicals_and_processes}\n"
            f"REQUEST_REASON: {request_reason}\n"
            f"PROCESS_FLOW: {process_flow}\n"
            f"AMOUNT_AND_FORM: {amount_and_form}\n\n"
            f"EMAIL_1_PROM_APPROVAL: {email_1_prom_approval}\n"
            f"EMAIL_1_RAW_THREAD_EXCERPT: {email_1_raw_thread}\n\n"
            f"EMAIL_2_PROM_APPROVAL: {email_2_prom_approval}\n"
            f"EMAIL_2_RAW_THREAD_EXCERPT: {email_2_raw_thread}\n"
        )
        print(user_payload)
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
            "route": "embed_all_stream",
            "user_text": query,
        },
    )
    return StreamingResponse(stream, media_type="text/plain")
