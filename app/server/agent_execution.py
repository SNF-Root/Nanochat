from openai import AsyncOpenAI

try:
    from .retrieval_helpers import embed_query
    from .models.server_classes import ExecutedStep
except ImportError:
    from retrieval_helpers import embed_query
    from models.server_classes import ExecutedStep

def _joined_columns(columns: list[str]) -> str:
    return ", ".join(columns)


def truncate(value, limit: int):
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def execute_sql_query(con, sql_query_obj):
    columns = _joined_columns(sql_query_obj.target_columns)
    query = (
        f"SELECT {columns} "
        f"FROM {sql_query_obj.target_table} "
        f"WHERE {sql_query_obj.column_to_search_target_string} ILIKE ANY (%s) "
        f"LIMIT %s"
    )
    like_patterns = [f"%{target}%" for target in sql_query_obj.target_string]
    params = (like_patterns, sql_query_obj.row_limit)
    cursor = con.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]
    return [
        {
            column_name: truncate(value, sql_query_obj.char_limit)
            for column_name, value in zip(column_names, row)
        }
        for row in rows
    ]


async def execute_semantic_search(
    client: AsyncOpenAI,
    con,
    semantic_search_obj,
    embedding_model: str,
    semantic_embedding_columns: dict[str, str],
):
    columns = _joined_columns(semantic_search_obj.target_columns)
    embedding_column = semantic_embedding_columns[semantic_search_obj.target_table]
    query_embedding = await embed_query(client, embedding_model, semantic_search_obj.query_str)
    query = (
        f"SELECT {columns}, "
        f"1 - ({embedding_column} <=> %s::vector) AS similarity "
        f"FROM {semantic_search_obj.target_table} "
        f"WHERE 1 - ({embedding_column} <=> %s::vector) >= %s "
        f"ORDER BY {embedding_column} <=> %s::vector "
        f"LIMIT %s"
    )
    params = (
        query_embedding,
        query_embedding,
        semantic_search_obj.min_similarity_score,
        query_embedding,
        semantic_search_obj.row_limit,
    )
    cursor = con.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]
    return [
        {
            column_name: (
                float(value)
                if column_name == "similarity"
                else truncate(value, semantic_search_obj.cell_char_limit)
            )
            for column_name, value in zip(column_names, row)
        }
        for row in rows
    ]


async def execute_agent_actions(
    client: AsyncOpenAI,
    con,
    agent_action,
    embedding_model: str,
    semantic_embedding_columns: dict[str, str],
):
    executed_steps = []
    for step in agent_action.steps:
        print(f"\n[STEP {step.step_number} RESULTS]")
        if step.action_type == "sql_query":
            results = execute_sql_query(con, step.sql_query)
        else:
            results = await execute_semantic_search(
                client,
                con,
                step.semantic_search,
                embedding_model,
                semantic_embedding_columns,
            )
        executed_steps.append(
            ExecutedStep(
                step_number = step.step_number,
                reason_for_step = step.reason_for_step,
                action_type= step.action_type,
                sql_params= step.sql_query,
                semantic_params = step.semantic_search,
                query_results = results
            )
        )
        if not results:
            print("No rows returned.")
            continue
        for row in results:
            print(row)
    return executed_steps
