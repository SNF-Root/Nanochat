import ast
import json
from typing import AsyncGenerator


redis_chat_context = None
CHAT_TTL_SECONDS = None
client = None
EMBEDDING_MODEL = None
CHAT_MODEL = None


def _user_key(user_id: str) -> str:
    return f"user:{user_id}:session_ids"


def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"

def _agentaction_key(session_id: str) -> str:
    return f"chat:agent:actions:history:{session_id}"


def _retrieved_entries_key(session_id: str) -> str:
    return f"chat:session:retrieved_entries:{session_id}"


def append_log_line(file_path: str, payload: dict) -> None:
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


async def append_chat_entry(session_id: str, request, response, entry: dict) -> str:
    key = _session_key(session_id)
    raw_chat_history = await redis_chat_context.get(key)
    context_history = json.loads(raw_chat_history) if raw_chat_history else []
    context_history.append(entry)
    await redis_chat_context.set(key, json.dumps(context_history), ex=CHAT_TTL_SECONDS)
    return session_id

async def append_agent_action_history(session_id: str, entry: dict) -> str:
    key = _agentaction_key(session_id)
    raw_context = await redis_chat_context.get(key)
    agent_actions_history = json.loads(raw_context) if raw_context else []
    agent_actions_history.append(entry)
    await redis_chat_context.set(key, json.dumps(agent_actions_history), ex=CHAT_TTL_SECONDS)
    return session_id


async def clear_agent_action_history(session_id: str) -> None:
    key = _agentaction_key(session_id)
    await redis_chat_context.delete(key)


async def get_chat_context(session_id: str):
    """
    Final retrieval from aggregated agent_actions is injected into Context of the chat
    """
    key = _session_key(session_id)
    raw_chat_history = await redis_chat_context.get(key)
    if raw_chat_history is None:
        return None
    context_history = json.loads(raw_chat_history) if raw_chat_history else []
    return context_history



async def get_agent_action_history(session_id: str):
    """
    Retrieved context is also stored into this one alongside past agent actions
    this is so that future agent actions can improve on retrieval quality in
    next iterations.
    """
    key = _agentaction_key(session_id)
    raw_agent_action_history = await redis_chat_context.get(key)
    if raw_agent_action_history is None:
        return []
    agent_action_history = json.loads(raw_agent_action_history) if raw_agent_action_history else []
    return agent_action_history



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


def parse_retrieved_entries_value(entries_raw):
    if entries_raw is None:
        return []

    try:
        parsed_entries = json.loads(entries_raw)
    except (TypeError, json.JSONDecodeError):
        return []

    return parsed_entries if isinstance(parsed_entries, list) else []


def merge_retrieved_entries(existing_entries: list[dict], new_entries: list[dict]) -> list[dict]:
    merged_entries = []
    seen = set()

    for entry in [*existing_entries, *new_entries]:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        table = str(entry.get("table") or "")
        row_id = str(entry.get("row_id") or "")
        dedupe_key = (table, row_id, filename)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged_entries.append(entry)

    return merged_entries


async def get_retrieved_entries(session_id: str) -> list[dict]:
    raw_entries = await redis_chat_context.get(_retrieved_entries_key(session_id))
    return parse_retrieved_entries_value(raw_entries)


async def merge_retrieved_entries_for_session(session_id: str, new_entries: list[dict]) -> list[dict]:
    existing_entries = await get_retrieved_entries(session_id)
    merged_entries = merge_retrieved_entries(existing_entries, new_entries)
    await redis_chat_context.set(
        _retrieved_entries_key(session_id),
        json.dumps(merged_entries),
        ex=CHAT_TTL_SECONDS,
    )
    return merged_entries


async def embed_query(client_override, embedding_model: str, text: str) -> list[float]:
    response = await client_override.embeddings.create(model=embedding_model, input=text)
    return response.data[0].embedding


async def stream_chat_completion_and_store(
    session_id: str,
    system_prompt: str,
    user_payload: str,
    request,
    response,
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
            await append_chat_entry(
                session_id,
                request,
                response,
                {
                    **context_entry,
                    "assistant_text": full_response_text,
                },
            )
