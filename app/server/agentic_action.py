import asyncio
import json
import os
from functools import wraps
from time import perf_counter

from openai import AsyncOpenAI
import psycopg2

try:
    from .agent_execution import (
        _joined_columns,
        execute_agent_actions,
    )
    from .models.server_classes import AgentAction
    from .prompts import (
        AGENT_ACTION_CONTINUATION_PROMPT,
        AGENT_ACTION_REQUEST_PROMPT,
    )
except ImportError:
    from agent_execution import _joined_columns, execute_agent_actions
    from models.server_classes import AgentAction
    from prompts import AGENT_ACTION_CONTINUATION_PROMPT, AGENT_ACTION_REQUEST_PROMPT





CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.4-nano")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
STANFORD_BASE_URL = os.getenv("STANFORD_BASE_URL", "https://aiapi-prod.stanford.edu/v1")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:user_pw@localhost:5433/appdb")
SEMANTIC_EMBEDDING_COLUMNS = {
    "prom_embeddings": "request_embedding",
    "email_embeddings": "embedding",
}


def timed_async(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        start = perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            elapsed = perf_counter() - start
            print(f"[TIMING] {fn.__name__} took {elapsed:.2f}s")

    return wrapper


def create_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("STANFORD_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    return AsyncOpenAI(
        api_key=api_key,
        base_url=STANFORD_BASE_URL,
    )


def create_db_connection():
    return psycopg2.connect(DATABASE_URL)


def render_sql_query(step) -> str:
    sql_query = step.sql_query
    columns = _joined_columns(sql_query.target_columns)
    target_patterns = []
    for target in sql_query.target_string:
        escaped_target = target.replace("'", "''")
        target_patterns.append(f"'%{escaped_target}%'")
    array_literal = ", ".join(target_patterns)
    return (
        f"-- Step {step.step_number}: {step.reason_for_step}\n"
        f"SELECT {columns}\n"
        f"FROM {sql_query.target_table}\n"
        f"WHERE {sql_query.column_to_search_target_string} ILIKE ANY (ARRAY[{array_literal}])\n"
        f"LIMIT {sql_query.row_limit};\n"
        f"-- Post-processing: truncate each returned cell to {sql_query.char_limit} chars"
    )


def render_semantic_search_query(step) -> str:
    semantic_search = step.semantic_search
    columns = _joined_columns(semantic_search.target_columns)
    embedding_column = SEMANTIC_EMBEDDING_COLUMNS.get(semantic_search.target_table)
    if embedding_column is None:
        raise ValueError(
            f"No semantic embedding column configured for table "
            f"{semantic_search.target_table}"
        )
    query_str = semantic_search.query_str.replace("'", "''")
    return (
        f"-- Step {step.step_number}: {step.reason_for_step}\n"
        f"-- First create an embedding for this query string:\n"
        f"-- {query_str}\n"
        f"SELECT {columns},\n"
        f"       1 - ({embedding_column} <=> :query_embedding::vector) AS similarity\n"
        f"FROM {semantic_search.target_table}\n"
        f"WHERE 1 - ({embedding_column} <=> :query_embedding::vector) >= "
        f"{semantic_search.min_similarity_score}\n"
        f"ORDER BY {embedding_column} <=> :query_embedding::vector\n"
        f"LIMIT {semantic_search.row_limit};\n"
        f"-- Post-processing: truncate each returned cell to "
        f"{semantic_search.cell_char_limit} chars"
    )


def render_step_queries(agent_action: AgentAction) -> str:
    rendered_queries = []
    for step in agent_action.steps:
        if step.action_type == "sql_query":
            rendered_queries.append(render_sql_query(step))
        elif step.action_type == "semantic_search":
            rendered_queries.append(render_semantic_search_query(step))
    return "\n\n".join(rendered_queries)


@timed_async
async def run_agentic_action(user_query: str) -> str:
    query = user_query.strip()
    if not query:
        raise ValueError("user_query must not be empty")

    client = create_openai_client()
    planner_prompt = AGENT_ACTION_REQUEST_PROMPT.replace("{user_query}", query)
    completion = await client.beta.chat.completions.parse(
        model=CHAT_MODEL,
        messages=[
            {"role": "user", "content": planner_prompt},
        ],
        temperature=0.2,
        response_format=AgentAction,
    )
    message = completion.choices[0].message
    if message.parsed is not None:
        planner_text = message.parsed.model_dump_json(indent=2)
        print(planner_text)
        print("\n[RENDERED SQL]")
        print(render_step_queries(message.parsed))
        print("\n[EXECUTED RESULTS]")
        con = create_db_connection()
        try:
            executed_steps = await execute_agent_actions(
                client,
                con,
                message.parsed,
                EMBEDDING_MODEL,
                SEMANTIC_EMBEDDING_COLUMNS,
            )
        finally:
            con.close()
        if message.parsed.after_execution == "return_to_llm":
            continuation_prompt = AGENT_ACTION_CONTINUATION_PROMPT.format(
                user_query=query,
                agent_action_json=planner_text,
                retrieved_results_json=json.dumps(
                    [executed_step.model_dump() for executed_step in executed_steps],
                    indent=2,
                ),
            )
            continuation = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "user", "content": continuation_prompt},
                ],
                temperature=0.2,
            )
            continuation_text = (
                continuation.choices[0].message.content
                if continuation.choices
                else ""
            )
            print("\n[LLM CONTINUATION]")
            print(continuation_text)
    elif message.refusal:
        planner_text = message.refusal
        print(planner_text)
    else:
        planner_text = message.content or ""
        print(planner_text)
    return planner_text


def run_agentic_action_sync(user_query: str) -> str:
    return asyncio.run(run_agentic_action(user_query))


if __name__ == "__main__":
    query = input("User query: ")
    run_agentic_action_sync(query)
