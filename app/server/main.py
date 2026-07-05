from typing import Dict, List, Set
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
import redis.asyncio as redis
from typing import Optional, Tuple
from openai import AsyncOpenAI
from .prompts import (
    ALL_SYSTEM_PROMPT,
    CONTINUATION_SYS_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    prom_prompt,
    AGENT_ACTION_CONTINUATION_PROMPT,
    AGENT_ACTION_REQUEST_PROMPT
)
from .models.server_classes import (
    AgentRequest,
    SearchStartResponse,
    UploadCounterResetResponse,
    UploadFileResponse,
    FileObject,
    AgentAction,
    AgentRetrievalResponse,
)
from .agent_execution import execute_agent_actions
from .models.pool_db import init_pool, get_db_connection, release_db_conn, close_all_conns
from . import retrieval_helpers, upload_helpers
from .retrieval_helpers import (
    _session_key,
    _user_key,
    append_agent_action_history,
    append_chat_entry,
    append_log_line,
    clear_agent_action_history,
    get_agent_action_history,
    get_chat_context,
    parse_entry_ids_value,
)
from .upload_helpers import (
    _upload_status_key,
    clear_uploaded_files_dir,
)
import os
from datetime import datetime, timezone


EMBEDDING_MODEL = "text-embedding-ada-002"
AGENT_PLANNER_MODEL = os.getenv("CHAT_MODEL", "gpt-5.4")
RESPONSE_CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.4")
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
SEMANTIC_EMBEDDING_COLUMNS = {
        "prom_embeddings": "request_embedding",
        "email_embeddings": "embedding",
    }
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
retrieval_helpers.redis_chat_context = redis_chat_context
retrieval_helpers.CHAT_TTL_SECONDS = CHAT_TTL_SECONDS
retrieval_helpers.EMBEDDING_MODEL = EMBEDDING_MODEL
retrieval_helpers.CHAT_MODEL = AGENT_PLANNER_MODEL
upload_helpers.UPLOAD_DIR = UPLOAD_DIR


#called only on server shutdown
async def clear_all_user_keys() -> int:
    deleted_count = 0
    async for key in redis_uids_sids.scan_iter():
        deleted_count += await redis_uids_sids.delete(key)
    async for key in redis_file_queue.scan_iter():
        await redis_file_queue.delete(key)
    async for key in redis_prom_retry_ids.scan_iter():
        if key == "worker:last_seen_email_id":
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

client = create_openai_client()
retrieval_helpers.client = client

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

#big security risk here, user may be able to access files we dont want him to access. 
#what if client asked to see .env file, first do auth, then make sure the parent dir is just /upload/
@app.get("/files/retrieve_proms/{session_id}", response_class=FileResponse)
async def retrieve_prom(session_id: str):
    redis_entry_key = f"chat:session:selected_entry:{session_id}"
    raw_entries_for_session = await redis_chat_context.get(redis_entry_key)
    entries_for_session = json.loads(raw_entries_for_session) if raw_entries_for_session else [] 
    try:
        con = get_db_connection()
        cursor = con.cursor()
        cursor.execute(
        """
        SELECT
            #finish this query here so that we select all filesnames where row_id = entry_id in table {prom|embedding} depending on the shape            

        """
        )
    except Exception as err:
        print()
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
async def attach_session_id_to_user(payload: AgentRequest, request: Request, response: Response):
    """create a session_id for the session and attach it to the user"""
    user_query = payload.text.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Text is required")
    try:
        append_log_line(
            SEARCH_LOG_PATH,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "route": "/search/start",
                "query": user_query,
            },
        )
    except Exception as error:
        print(f"[WARN] Failed to write start search query log: {error}")
    session_init = await set_session_id(request=request, response=response)
    session_id = session_init.get("session_id") if isinstance(session_init, dict) else None
    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to create chat session") 
    return SearchStartResponse(session_id=session_id, query=user_query)


@app.get("/api/session/{session_id}")
async def rehydrate_chat(session_id: str, request: Request, response: Response):
    context_history = await get_chat_context(session_id)
    if context_history is None:
        print("in rehydration chat, and key has expired")
        return RedirectResponse(url="/chat/expired", status_code=307)
    return context_history

@app.get("/session/{session_id}")
async def redirect_rehydrated_chat(session_id: str, request: Request, response: Response):
    return RedirectResponse(url=f"http://localhost:3000/session/{session_id}")


@app.post("/session/{session_id}/agent/retrieval", response_model=AgentRetrievalResponse)
async def run_agent_action(session_id: str, payload: AgentRequest, request: Request, response: Response):
    user_query = payload.text.strip()
    print(user_query)
    if not user_query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_chat_context(session_id)
    if context_history is None:
        return RedirectResponse(url="/chat/expired", status_code=307)

    try:
        agent_prompt = AGENT_ACTION_REQUEST_PROMPT.replace("{user_query}", user_query)
        agent_action_history = await get_agent_action_history(session_id)
        agent_prompt = agent_prompt.replace(
            "{past_agent_actions}",
            json.dumps(agent_action_history, indent=2),
        )
        print("sending for agentic planning")
        planner_completion = await client.beta.chat.completions.parse(
            model=AGENT_PLANNER_MODEL,
            messages=[
                {"role": "user", "content": agent_prompt},
            ],
            temperature=0.2,
            response_format=AgentAction,
        )

        returned_agent_action_json = planner_completion.choices[0].message
        agent_action_obj = returned_agent_action_json.parsed
        if agent_action_obj is None:
            print("[AGENT_ACTION_VALIDATION] Planner did not produce a parsed AgentAction.")
            print(f"[AGENT_ACTION_VALIDATION] refusal={returned_agent_action_json.refusal}")
            print(f"[AGENT_ACTION_VALIDATION] content={returned_agent_action_json.content}")
            raise HTTPException(status_code=500, detail="Agent did not return a valid AgentAction")

        con = get_db_connection()
        try:
            executed_steps = await execute_agent_actions(
                client,
                con,
                agent_action_obj,
                EMBEDDING_MODEL,
                SEMANTIC_EMBEDDING_COLUMNS,
            )
        finally:
            release_db_conn(con=con)
        
        if agent_action_obj.after_execution == "return_to_llm":
            for executed_step in executed_steps:
                await append_agent_action_history(
                    session_id,
                    {
                        "agent_action": agent_action_obj.model_dump_json(),
                        "retrieved_context_for_action": executed_step.query_results
                    },
                )
            return AgentRetrievalResponse(
                text=None,
                list_of_executed_steps=executed_steps,
                done=False,
            )
        elif agent_action_obj.after_execution == "generate_final_answer":
            retrieved_context = json.dumps(
                [
                    {
                        "agent_action": agent_action_obj.model_dump(),
                        "retrieved_context_for_action": executed_step.query_results,
                    }
                    for executed_step in executed_steps
                ],
                indent=2,
            )
            past_chat_context = json.dumps(context_history, indent=2)
            answer_prompt = CONTINUATION_SYS_PROMPT.format(
                past_retrieved_context=retrieved_context,
                past_chat_context=past_chat_context,
                current_user_question=user_query,
            )
            answer_completion = await client.chat.completions.create(
                model=RESPONSE_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": answer_prompt},
                ],
                temperature=0.2,
            )
            assistant_text = answer_completion.choices[0].message.content or ""
            await append_chat_entry(
                session_id,
                request,
                response,
                {
                    "route": "run_agent_action",
                    "user_text": user_query,
                    "assistant_text": assistant_text,
                },
            )
            await clear_agent_action_history(session_id)
            return AgentRetrievalResponse(
                text=assistant_text,
                list_of_executed_steps=executed_steps,
                done=True,
            )
            

    except ValidationError as error:
        print("[AGENT_ACTION_VALIDATION] Pydantic validation failed for AgentAction.")
        print(error)
        raise HTTPException(status_code=500, detail="AgentAction schema validation failed") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Agentic retrieval failed: {error}") from error
