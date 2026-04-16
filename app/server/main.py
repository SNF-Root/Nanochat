import logging
import os
from typing import Dict, List, Set
import json
import uuid
import shutil
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from typing import AsyncGenerator, Optional, Tuple
from openai import OpenAI
from preprocessing.database.pg import get_db_connection
from .auth_config import is_email_allowed, load_allowed_emails
from .prompts import (
    CONTINUATION_SYS_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    prom_prompt,
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

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-ada-002"
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")


USER_COOKIE = "user_id"
SESSION_TTL_SECONDS = 60 * 60 * 24


def _auth_user_key(user_id: str) -> str:
    return f"auth:user:{user_id}"


def _user_cookie_params() -> dict:
    return {
        "max_age": SESSION_TTL_SECONDS,
        "httponly": True,
        "secure": os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        "samesite": "lax",
        "path": "/",
    }


async def require_saml_authentication(request: Request) -> None:
    if not saml_is_configured():
        return
    user_id = request.cookies.get(USER_COOKIE)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    raw = await redis_chat_context.get(_auth_user_key(user_id))
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



@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_saml_env_at_startup()
    try:
        yield
    finally:
        await clear_all_user_keys()
        clear_uploaded_files_dir() 


app = FastAPI(lifespan=lifespan)
redis_chat_context = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
redis_file_queue = redis.Redis(host="redis", port=6379, db=1)
redis_uids_sids: Dict[str, Set[str]] = redis.Redis(host="redis", port=6379, db=2)
redis_file_status_store = redis.Redis(host="redis", port=6379, db=3, decode_responses=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#TODO: please change this to an async client for the love of concurrent streaming
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

class FileObject(BaseModel):
    user_id: str
    upload_id:str
    kind: str
    filepath: str


class UploadCounterResetResponse(BaseModel):
    number_of_files_cleared: int
    status_of_queue: str


def _user_key(user_id: str) -> str:
    return f"user:{user_id}:session_ids"

def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"


def _upload_status_key(user_id: str) -> str:
    return f"user:upload_file_status:{user_id}"




#called only on server shutdown
async def clear_all_user_keys() -> int:
    deleted_count = 0
    async for key in redis_uids_sids.scan_iter():
        deleted_count += await redis_uids_sids.delete(key)
    print(f"[DEBUG] Cleared {deleted_count} context history keys on shutdown")
    return deleted_count


async def create_user_id(request: Request, response: Response) -> str:
    user_id = uuid.uuid4().hex
    response.set_cookie(key=USER_COOKIE, value=user_id, **_user_cookie_params())
    return user_id



async def create_add_session_id(request: Request, response: Response) -> str:
    user_id = request.cookies.get(USER_COOKIE)
    session_id = uuid.uuid4().hex
    added = await redis_uids_sids.sadd(_user_key(user_id), _session_key(session_id))
    return session_id, added 

async def get_session_ids(request: Request, response: Response):
    user_id = request.cookies.get(USER_COOKIE)
    return await redis_uids_sids.smembers(_user_key(user_id))





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
        if not await redis_chat_context.get(_auth_user_key(user_id)):
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


@app.get("/user/status")
async def user_status(request: Request):
    user_id = request.cookies.get(USER_COOKIE)
    return {
        "has_user": bool(user_id),
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
        await redis_chat_context.delete(_auth_user_key(user_id))
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
        raise HTTPException(status_code=403, detail="SAML validation failed")

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
        raise HTTPException(status_code=403, detail="Not authorized for this application")
    if not is_email_allowed(email, allowed):
        logger.warning(
            "[SAML] acs outcome=reject phase=allowlist "
            "reason=email_not_allowlisted email=%r allowlist_entries=%d",
            email,
            len(allowed),
        )
        raise HTTPException(status_code=403, detail="Not authorized for this application")

    user_id = request.cookies.get(USER_COOKIE) or uuid.uuid4().hex
    sunet = sunet_from_saml(attrs, nameid, email)
    payload = {
        "email": email,
        "sunetid": sunet,
        "nameid": nameid,
    }
    await redis_chat_context.set(
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
    



VALID_PROM_UPLOAD_EXTENSIONS = [".pdf", ".docx"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "uploaded_files"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

def clear_uploaded_files_dir() -> None:
    try:
        if os.path.isdir(UPLOAD_DIR):
            shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    except Exception as e:
        return f"Could not clear uploaded files {e}"




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


@app.post("/upload/reset_counter", response_model=UploadCounterResetResponse)
async def reset_upload_counter(
    _: None = Depends(require_saml_authentication),
) -> UploadCounterResetResponse:
    key = "promfile_upload_counter"
    queue_name = "pending_files"
    len_of_queue = await redis_file_queue.llen(queue_name)
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
                session_id, 
                request,
                response,
                {
                    **context_entry,
                    "assistant_text": full_response_text,
                },
            )




@app.post("/search/emails", response_model=SearchResponse)
def search_emails(
    payload: EmbedRequest,
    _: None = Depends(require_saml_authentication),
) -> SearchResponse:
    """Return the top 5 most similar email threads (llm_context + similarity)."""
    query = payload.text.strip()
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
def search_proms(
    payload: EmbedRequest,
    _: None = Depends(require_saml_authentication),
) -> SearchResponse:
    """Return the top 5 most similar PROM requests (title + similarity only)."""
    query = payload.text.strip()
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


@app.post("/session/{session_id}/embed/emails/stream")
async def embed_emails_stream(
    session_id: str, payload: EmbedRequest, request: Request, response: Response
):
    await require_owned_chat_session(session_id, request)
    query = payload.text.strip()
    print(f"[DEBUG][emails][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(session_id, request, response)
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
#     return len(context_history)


@app.post("/session/{session_id}/embed/proms/stream")
async def embed_proms_stream(
    session_id: str, payload: EmbedRequest, request: Request, response: Response
):
    await require_owned_chat_session(session_id, request)
    query = payload.text.strip()
    print(f"[DEBUG][proms][stream] Received query: '{query}'")
    if not query:
        raise HTTPException(status_code=400, detail="Text is required")

    context_history = await get_context(session_id, request, response)
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
