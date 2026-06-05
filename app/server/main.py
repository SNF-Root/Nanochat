import logging
import os
from typing import Dict, List, Set
import json
import uuid
import shutil
import re
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, FileResponse
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from typing import AsyncGenerator, Optional, Tuple
from openai import AsyncOpenAI
from .auth_config import is_email_allowed, load_allowed_emails
from datetime import datetime, timezone

from .prompts import (
    ALL_SYSTEM_PROMPT,
    CONTINUATION_SYS_PROMPT,
    CONTINUATION_ADDED_CONTEXT_SYS_PROMPT
    )
from .saml_config import (
    acs_public_url,
    build_request_data_for_url,
    build_saml_settings,
    primary_email_from_saml,
    saml_auth_for_request,
    saml_is_configured,
    saml_login_public_url,
    sunet_from_saml,
    validate_saml_env_at_startup,
)
from .models.server_classes import (
    EmbedRequest,
    EmbedResponse,
    SearchResponse,
    SearchResult,
    SearchStartResponse,
    UploadFileResponse,
    FileObject,
    AddContext
)
from .models.pool_db import init_pool, get_db_connection, release_db_conn, close_all_conns
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
    validate_saml_env_at_startup()
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
redis_auth_store = redis.Redis(host="redis", port=6379, db=5, decode_responses=True)
logger = logging.getLogger(__name__)

#called only on server shutdown
async def clear_all_user_keys() -> int:
    deleted_count = 0
    async for key in redis_uids_sids.scan_iter():
        deleted_count += await redis_uids_sids.delete(key)
    async for key in redis_auth_store.scan_iter():
        deleted_count += await redis_auth_store.delete(key)
    async for key in redis_file_queue.scan_iter():
        if key == "worker:last_seen_email_id":
            continue
        await redis_file_queue.delete(key)
    print(f"[DEBUG] Cleared {deleted_count} context history keys on shutdown")
    return deleted_count

def clear_uploaded_files_dir() -> None:
    try:
        if os.path.isdir(UPLOAD_DIR):
            shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    except Exception as e:
        return f"Could not clear uploaded files {e}"

def _auth_user_key(user_id: str) -> str:
    return f"auth:user:{user_id}"

def _user_key(user_id: str) -> str:
    return f"user:{user_id}:session_ids"

def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"

def _upload_status_key(user_id: str) -> str:
    return f"user:upload_file_status:{user_id}"

def append_log_line(file_path: str, payload: dict) -> None:
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def _user_cookie_params() -> dict:
    return {
        "max_age": SESSION_TTL_SECONDS,
        "httponly": True,
        "secure": os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        "samesite": "lax",
        "path": "/",
    }




async def create_user_id(request: Request, response: Response) -> str:
    user_id = uuid.uuid4().hex
    response.set_cookie(key=USER_COOKIE, value=user_id, **_user_cookie_params())
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


async def require_saml_authentication(request: Request) -> None:
    if not saml_is_configured():
        return
    user_id = request.cookies.get(USER_COOKIE)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    raw = await redis_auth_store.get(_auth_user_key(user_id))
    if not raw:
        raise HTTPException(status_code=401, detail="Authentication required")


async def require_owned_chat_session(session_id: str, request: Request) -> None:
    if not saml_is_configured():
        return
    await require_saml_authentication(request)
    user_id = request.cookies.get(USER_COOKIE)
    members = await redis_uids_sids.smembers(_user_key(user_id))
    if _session_key(session_id) not in members:
        raise HTTPException(status_code=403, detail="Unknown chat session")


#should happen during upon entering home

@app.post("/user/init")
async def set_user_cookie(request: Request, response: Response):
    if saml_is_configured():
        user_id = request.cookies.get(USER_COOKIE)
        if not user_id:
            print("[SAML] /user/init -> 401 saml_required (no user_id cookie)")
            raise HTTPException(
                status_code=401,
                detail={"error": "saml_required", "login_path": "/auth/saml/login"},
            )
        if not await redis_auth_store.get(_auth_user_key(user_id)):
            print("[SAML] /user/init -> 401 saml_required (no SAML session in Redis for cookie)")
            raise HTTPException(
                status_code=401,
                detail={"error": "saml_required", "login_path": "/auth/saml/login"},
            )
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
            "session_ids": sids,
        }
    user_id = await create_user_id(request, response)
    print("created session id")
    return {
        "created_session": True,
        "has_context": False,
        "session_ids": (),
    }


@app.post("/session/init")
async def set_session_id(
    request: Request,
    response: Response,
    _: None = Depends(require_saml_authentication),
):
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
        await redis_auth_store.delete(_auth_user_key(user_id))
    response.delete_cookie(key=USER_COOKIE, path="/")
    return {"ok": True, "logged_out": True}


@app.get("/saml/login")
async def saml_login_alias():
    """Shorthand URL; SAML AuthnRequest must use the canonical `/auth/saml/login` URL."""
    if not saml_is_configured():
        raise HTTPException(status_code=404, detail="SAML not configured")
    return RedirectResponse(url="/auth/saml/login", status_code=307)


@app.get("/auth/saml/login")
async def saml_login(request: Request):
    if not saml_is_configured():
        raise HTTPException(status_code=404, detail="SAML not configured")
    req_data = build_request_data_for_url(
        public_url=saml_login_public_url(),
        get_data={k: str(v) for k, v in request.query_params.items()},
        post_data={},
    )
    auth = saml_auth_for_request(req_data)
    frontend = os.getenv("SAML_FRONTEND_REDIRECT_URL", "").strip()
    if not frontend:
        p = urlparse(acs_public_url())
        frontend = f"{p.scheme}://{p.netloc}/"
    redirect_url = auth.login(return_to=frontend)
    return RedirectResponse(redirect_url)


async def _saml_acs_finish(
    request: Request,
    *,
    get_data: dict[str, str],
    post_data: dict[str, str],
) -> RedirectResponse:
    if not saml_is_configured():
        raise HTTPException(status_code=404, detail="SAML not configured")
    req_data = build_request_data_for_url(
        public_url=acs_public_url(),
        get_data=get_data,
        post_data=post_data,
    )
    auth = saml_auth_for_request(req_data)
    auth.process_response()
    if auth.get_errors():
        logger.warning(
            "[SAML] acs outcome=reject phase=saml_validation errors=%r reason=%r",
            auth.get_errors(),
            auth.get_last_error_reason(),
        )
        raise HTTPException(status_code=401, detail="SAML validation failed")

    attrs = auth.get_attributes()
    nameid = auth.get_nameid()
    email = primary_email_from_saml(attrs, nameid)
    allowed = load_allowed_emails()
    if not email:
        keys = sorted(attrs.keys()) if attrs else []
        logger.warning(
            "[SAML] acs outcome=reject phase=credential "
            "reason=no_email_in_assertion attribute_keys=%r nameid_present=%s",
            keys,
            bool(nameid),
        )
        raise HTTPException(status_code=401, detail="Not authorized for this application")
    if not is_email_allowed(email, allowed):
        logger.warning(
            "[SAML] acs outcome=reject phase=allowlist "
            "reason=email_not_allowlisted email=%r allowlist_entries=%d",
            email,
            len(allowed),
        )
        raise HTTPException(status_code=401, detail="Not authorized for this application")

    user_id = request.cookies.get(USER_COOKIE) or uuid.uuid4().hex
    sunet = sunet_from_saml(attrs, nameid, email)
    payload = {
        "email": email,
        "sunetid": sunet,
        "nameid": nameid,
    }
    await redis_auth_store.set(
        _auth_user_key(user_id),
        json.dumps(payload),
        ex=SESSION_TTL_SECONDS,
    )

    relay = (
        post_data.get("RelayState")
        or get_data.get("RelayState")
        or os.getenv("SAML_FRONTEND_REDIRECT_URL", "").strip()
    )
    if not relay:
        p = urlparse(acs_public_url())
        relay = f"{p.scheme}://{p.netloc}/"
    if relay.startswith("/"):
        p = urlparse(acs_public_url())
        relay = f"{p.scheme}://{p.netloc}{relay}"

    logger.info(
        "[SAML] acs outcome=ok phase=session email=%r sunet=%r",
        email,
        sunet,
    )

    out = RedirectResponse(url=relay, status_code=303)
    if not request.cookies.get(USER_COOKIE):
        out.set_cookie(USER_COOKIE, user_id, **_user_cookie_params())
    return out


@app.get("/auth/saml/callback")
async def saml_callback_get(request: Request):
    """
    Some IdPs or proxies deliver SAMLResponse on the query string (redirect-style).
    python3-saml's process_response() only inspects post_data, so we mirror those params
    into post_data when present. Bare GET (bookmark, bad redirect) → send user to login.
    """
    get_data = {k: str(v) for k, v in request.query_params.multi_items()}
    if "SAMLResponse" not in get_data:
        logger.warning(
            "[SAML] acs outcome=reject phase=transport "
            "reason=get_callback_without_samlresponse "
            "(IdP must POST SAMLResponse; a proxy that turns POST into GET drops the body)"
        )
        return RedirectResponse(url="/auth/saml/login", status_code=303)
    post_data = {
        k: get_data[k]
        for k in ("SAMLResponse", "RelayState")
        if k in get_data
    }
    return await _saml_acs_finish(request, get_data=get_data, post_data=post_data)


@app.post("/auth/saml/callback")
async def saml_callback_post(request: Request):
    """HTTP-POST binding: SAMLResponse and RelayState are form fields."""
    form = await request.form()
    post_data = {k: str(v) for k, v in form.multi_items()}
    get_data = {k: str(v) for k, v in request.query_params.multi_items()}
    return await _saml_acs_finish(request, get_data=get_data, post_data=post_data)


@app.get("/saml/metadata")
async def saml_metadata():
    if not saml_is_configured():
        raise HTTPException(status_code=503, detail="SAML not configured")
    settings = OneLogin_Saml2_Settings(build_saml_settings())
    metadata = settings.get_sp_metadata()
    errs = settings.validate_metadata(metadata)
    if errs:
        raise HTTPException(status_code=500, detail="Invalid SAML metadata configuration")
    return Response(content=metadata, media_type="application/xml")
    



@app.post("/upload/prom", response_model=UploadFileResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
    _: None = Depends(require_saml_authentication),
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
async def upload_email(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
    _: None = Depends(require_saml_authentication),
) -> UploadFileResponse:
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
async def show_list(_: None = Depends(require_saml_authentication)):
    prom_data_items = await redis_file_queue.lrange("pending_prom_files", 0, -1)
    emails_data_items = await redis_file_queue.lrange("pending_email_files", 0, -1)
    return_obj = {
        "prom_data_files": prom_data_items,
        "queued_email_files": emails_data_items
    }
    return return_obj


@app.get("/upload/get")
async def get_uploads(
    request: Request,
    _: None = Depends(require_saml_authentication),
):
    user_id = request.cookies.get(USER_COOKIE)
    if not user_id:
        return []
    items = await redis_file_status_store.lrange(_upload_status_key(user_id), 0, -1)
    return [json.loads(item) for item in items]

@app.get("/context/show-list")
async def show_context_list(
    request: Request,
    _: None = Depends(require_saml_authentication),
):
    # if not user_id:
        #hit them with a redirect
    all_active_sessions = {}

    async for key in redis_uids_sids.scan_iter():
        active_sessions = await redis_uids_sids.smembers(key)
        all_active_sessions[key] = active_sessions
    return all_active_sessions




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
async def retrieve_file(file_name: str, _: None = Depends(require_saml_authentication)):
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
async def retrieve_email(
    session_id: str,
    request: Request,
    _: None = Depends(require_owned_chat_session),
):
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
async def search_all_start(
    payload: EmbedRequest,
    request: Request,
    response: Response,
    _: None = Depends(require_saml_authentication),
):
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
    session_id, added = await create_add_session_id(request, response)
    session_id = session_id if added else None
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
async def search_all(request: EmbedRequest, _: None = Depends(require_saml_authentication)) -> SearchResponse:
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
async def add_context(
    session_id: str,
    payload: AddContext,
    request: Request,
    response: Response,
    _: None = Depends(require_owned_chat_session),
):
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
async def rehydrate_chat(session_id: str, request: Request, response: Response, _: None = Depends(require_owned_chat_session)):
    context_history = await get_context(session_id, request=request, response=response)
    if context_history is None:
        print("in rehydration chat, and key has expired")
        return RedirectResponse(url="/chat/expired", status_code=307)
    return context_history

@app.get("/session/{session_id}")
async def redirect_rehydrated_chat(session_id: str, request: Request, response: Response, _: None = Depends(require_owned_chat_session)):
    return RedirectResponse(url=f"http://localhost:3000/session/{session_id}")


@app.post("/session/{session_id}/embed/all/stream")
async def embed_all_stream(session_id: str, payload: EmbedRequest, request: Request, response: Response, _: None = Depends(require_owned_chat_session)):
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
