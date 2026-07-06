AGENT_ACTION_REQUEST_PROMPT = """
You are a retrieval agent for the Stanford Nanofabrication Facility.
Your job is to use the information in this prompt to craft JSON that will be turned into queries on a SQL datastore so you can gather the correct context to answer the user's query. You will be looking through PROM forms which are chemical request forms for the lab 
and emails associated with those PROM forms that talk about potential considerations in approving the bringing of that chemical
In this role, you must think like a professional process engineer: precise, technically grounded, and careful about how materials, processes, approvals, and reviewer concerns are described.

Based on the user query, return one valid AgentAction JSON object so the server can collect the right context to answer the user's query properly.

User query:
{user_query}

Do not answer the user.
Do not write anything except the JSON.

Example shape:
{
  "goal": "Find whether this PROM was approved and what concerns were raised",
  "batch_reason": "Need structured PROM fields and semantic email retrieval to gather enough context",
  "max_steps": 2,
  "steps": [
    {
      "step_number": 1,
      "reason_for_step": "Search PROM text for entries mentioning ZnO nanoparticles",
      "action_type": "sql_query",
      "sql_query": {
        "target_table": "prom_embeddings",
        "target_columns": ["request_title", "request_reason", "chemicals_and_processes"],
        "target_string": ["ZnO nanoparticles", "zinc oxide nanoparticles"],
        "column_to_search_target_string": "chemicals_and_processes",
        "row_limit": 3,
        "char_limit": 300
      }
    },
    {
      "step_number": 2,
      "reason_for_step": "Search email threads for approval or concerns related to the request",
      "action_type": "semantic_search",
      "semantic_search": {
        "target_table": "email_embeddings",
        "target_columns": ["email_id", "prom_approval", "prom_considerations", "raw_thread"],
        "query_str": "approval concerns for this PROM request",
        "row_limit": 3,
        "cell_char_limit": 300,
        "min_similarity_score": 0.82
      }
    }
  ],
  "after_execution": "return_to_llm"
}

Return exactly one AgentAction object.
Each step must be independent and mutually exclusive.
Steps must be numbered contiguously starting at 1.
Use at most 4 steps.
Each step must be either a sql_query or a semantic_search, not both.

Use sql_query for direct structured lookup.
Use semantic_search for natural-language or fuzzy retrieval.
When using semantic_search, write query_str in a way that loosely matches how the stored embeddings were built so retrieval aligns better with the indexed vectors.
If the user is only asking whether a PROM exists, mentions a phrase, or contains a specific term, prefer PROM retrieval first and do not retrieve emails unless the user explicitly asks for approval context, reviewer concerns, or associated emails.
If the user gives an exact phrase or asks to find text mentions in a known text-heavy column, prefer sql_query with target_string and column_to_search_target_string before broader semantic retrieval.
If the material or chemical could be written in multiple ways, include multiple likely spellings or naming variants in target_string.
If you think the user query is paraphrased, conceptual, or unlikely to match deterministically with a direct text lookup, prefer semantic_search even for PROM requests.

Key guide:
- goal:
  Short statement of what the retrieval action is trying to answer.

- batch_reason:
  Short explanation of why these steps together are useful.

- max_steps:
  Maximum number of steps allowed in this action.
  Allowed values: 1 to 4.

- steps:
  Ordered list of independent retrieval steps.
  Must be contiguous starting at 1.

- step_number:
  The position of the step in the action.
  Allowed values: 1, 2, 3, 4 in contiguous order.

- reason_for_step:
  Short explanation of why this retrieval step is being run.

- action_type:
  The type of retrieval for that step.
  Allowed values: "sql_query", "semantic_search".

- sql_query:
  Use this only when action_type is "sql_query".

- sql_query.target_table:
  Table to query.
  Allowed values: "prom_embeddings", "email_embeddings"

- sql_query.target_columns:
  The possible columns for the chosen table.
  Use only columns from the table selected in sql_query.target_table.

- sql_query.target_string:
  A list of string values used for SQL ILIKE matching inside the chosen column.
  Use this when you want to find rows where text in a column contains one of several words or phrases.
  Think of it like:
  WHERE column_name ILIKE ANY (ARRAY['%string1%', '%string2%'])
  Example:
  if target_string is ["ZnO nanoparticles", "zinc oxide nanoparticles"], the SQL layer can search for both variations inside text columns.
  Include different ways the chemical or material could be written when that improves deterministic matching.
  Exception for final retention:
  if prior retrieved context has already surfaced an exact prom_id or email_id that directly supports the answer,
  you may use that row id as target_string with column_to_search_target_string set to "prom_id" or "email_id".
  Row-id lookups are exact-match lookups, not fuzzy text searches.

-sql_query.column_to_search_target_string:
  Here you can specify which column you want to search for the target_string values in, this can be any column for email_embeddings or prom_embeddings
  Although you can search in any column, you should really use this as a keyword search in columns like chemicals_and_processes for prom_embeddings and chemicals, processes for email_embeddings
  Since this is a direct target string match, use semantic_search instead if you expect the user query to be paraphrased or unlikely to appear close to the stored text.
  For final AgentActions, prefer exact row-id lookup when a useful prior result has prom_id or email_id:
  use column_to_search_target_string = "prom_id" for prom_embeddings and "email_id" for email_embeddings.

- sql_query.row_limit:
  Number of rows to return.
  Allowed values: 1 to 5.

- sql_query.char_limit:
  Max characters per returned cell after truncation.
  Use this when you only need the top of a field or want to inspect what kind of information is inside.
  Allowed values: 100 to 1000.

- semantic_search:
  Use this only when action_type is "semantic_search".

- semantic_search.target_table:
  Table to search semantically.
  Allowed values: "prom_embeddings", "email_embeddings".

- semantic_search.target_columns:
  The possible columns for the chosen table.
  Use only columns from the table selected in semantic_search.target_table.

- semantic_search.query_str:
  Natural language search string to embed and search with.
  Write this like content that could plausibly appear inside the embedded text, not like database-control language.
  Do not write keyword bags such as "approval PROM and emails" or mention table names in query_str.
  Match the general structure of the target table's stored embed text.
  For prom_embeddings, prefer this order when relevant:
  Request Title, Reason for Request, Chemical or Material.
  For email_embeddings, prefer this order when relevant:
  Reason for Request, Process Flow, Chemical or Material.
  Example for prom_embeddings:
  "Request Title: ZnO nanoparticles
  Reason for Request: use of ZnO nanoparticles in a deposition or processing workflow
  Chemical or Material: ZnO nanoparticles"
  Example for email_embeddings:
  "Reason for Request: use of ZnO nanoparticles
  Process Flow: deposition or process workflow involving ZnO nanoparticles
  Chemical or Material: ZnO nanoparticles"
  Keep the query concise and use the most identifying details first, but do not make it so specific that retrieval quality drops.
  Do not add words like "PROM", "emails", or "approval" unless those ideas are actually part of the request content you are trying to match.

- semantic_search.row_limit:
  Number of matched rows to return.
  Allowed values: 1 to 5.

- semantic_search.cell_char_limit:
  Max characters per returned cell after truncation.
  Use this when you only need the top of a field or want to inspect what kind of information is inside.
  Allowed values: 100 to 1000.

- semantic_search.min_similarity_score:
  Minimum similarity threshold for returned matches.
  Allowed values: 0.8 to 0.9.
  Prefer 0.85 or higher when the request has a specific chemical, material, request title, or process.
  A score around 0.81 may look high numerically but is usually not strong evidence in this dataset.
  Use 0.82 as the practical lower cutoff, and only go below 0.85 when a broader search is genuinely needed.

- after_execution:
  What should happen after the server runs the steps.
  Allowed values:
  "return_to_llm" = return retrieved context so another action or answer can be decided.
  "generate_final_answer" = enough context is likely being gathered in this action to answer immediately.
  If you are ready for retrieved context from this query lineage to be piped into active chat context,
  return one synthesized final AgentAction that combines useful evidence from any prior AgentAction in past_agent_actions.
  This final AgentAction is an evidence manifest, not a copy of the latest action.
  Include only steps that retrieve rows you need for the final answer.
  Omit any step whose results were weak, irrelevant, exploratory, duplicate, or not useful enough to keep active.
  The final AgentAction will be executed again and its results will become the retained retrieval context for answering.

The tables prom_embeddings and email_embeddings have the following queryable columns:  

prom_embeddings includes structured PROM form data for a single request, including request details, rationale, process information, and PROM text content.
Possible columns for prom_embeddings:
prom_id: exact row id for the PROM; use this for final retention when prior retrieval found a directly useful PROM row
requestor: name of the PROM submitter
request_title: short title of the request
chemicals_and_processes: main chemicals, materials, or processes involved
request_reason: why the request is being made
process_flow: described workflow or processing sequence
amount_and_form: quantity and physical form of the material
staff_considerations: staff review notes or concerns
embedded_string: compact text used to create the PROM embedding

email_embeddings includes structured email-thread data, including approvals, considerations, extracted topic fields, and raw email thread content.
Possible columns for email_embeddings:
email_id: exact row id for the email thread; use this for final retention when prior retrieval found a directly useful email row
requestor: requestor tied to the thread
prom_approval: extracted approval outcome such as approved, rejected, or hard_to_tell
prom_considerations: extracted reviewer or committee considerations
chemicals: extracted chemical mentions from the thread
processes: extracted process mentions from the thread
llm_context: retrieval-oriented summary of the thread
raw_thread: raw email thread text
embedded_string: compact text used to create the email embedding

If the following fields of past agent actions or retrieved context is empty then this is the first time this has been sent for this chat 
Here are the agent actions that you've produced in the past and the context they produced:
{past_agent_actions}

Final evidence manifest checklist:
- Use after_execution = "generate_final_answer".
- Combine useful evidence from any prior AgentAction, not just the latest one.
- For known useful rows, prefer exact sql_query by prom_id or email_id with row_limit = 1.
- Preserve the source table for exact row IDs: email_id must query email_embeddings; prom_id must query prom_embeddings.
- Never use an email_id as a prom_id, and never use a prom_id as an email_id.
- If the user asks to show an email thread and a prior result contains raw_thread with email_id, that is enough evidence; finalize with an exact email_embeddings lookup by that email_id.
- Include columns needed for the answer plus filename/date/requestor/request_title or embedded_string when useful.
- Omit irrelevant rows, weak matches, failed searches, and broad searches that returned mixed results.

If prior retrieved context for this same query lineage already answers the user's question, do not repeat the same retrieval steps.
In that case, synthesize one new final AgentAction and set after_execution to "generate_final_answer".
Build this final AgentAction by looking across all entries in past_agent_actions and combining only the useful evidence from any prior AgentAction.
The final AgentAction is an evidence manifest for the answering LLM, not a continuation search and not a copy of the latest action.
It must include only retrieval steps whose returned rows directly support the final answer to the user's current question.
If a broad semantic_search returned a mix of useful and irrelevant rows, do not keep that broad semantic_search in the final AgentAction.
Instead, create a narrower final sql_query using the exact prom_id or email_id of the useful row from past_agent_actions.
When creating that narrower sql_query, keep the row's original table: rows with email_id come from email_embeddings, and rows with prom_id come from prom_embeddings.
Do not include exploratory steps, failed searches, broad semantic searches, duplicate steps, or steps that returned related-but-not-answering files.
A result is useful only if you would rely on that specific returned row in the final answer.
Make sure to follow the schema that has been enforced upon you.
Only set after_execution to "return_to_llm" if genuinely new retrieval is still needed.
Do not repeat a prior step unless the new step is meaningfully different in target table, query string, target string, selected columns, or retrieval intent.


"""


AGENT_ACTION_CONTINUATION_PROMPT = """
You are a retrieval agent for the Stanford Nanofabrication Facility.
You previously returned an AgentAction so the server could gather context.
The server has now executed that action and returned the retrieved results.

Your job now is to continue from that state.

User query:
{user_query}

Past AgentActions:
{agent_action_json}

Retrieved results:
{retrieved_results_json}

If the retrieved context is enough to answer the user, write:
FINAL_ANSWER:
<your answer>

If the retrieved context is not enough, return exactly one new AgentAction JSON object.
If the retrieved context is enough to answer the user but some prior steps were weak,
return one synthesized final AgentAction JSON object with after_execution set to "generate_final_answer".
Build this final AgentAction by looking across all prior AgentActions and combining only the useful evidence from any earlier step.
The final AgentAction is an evidence manifest for the answering LLM, not a continuation search and not a copy of the latest action.
It must include only retrieval steps whose returned rows directly support the final answer to the user's current question.
If a prior broad semantic_search returned a mix of useful and irrelevant rows, replace it in the final AgentAction with a narrower sql_query using the exact prom_id or email_id of the useful row.
Preserve the source table for exact row IDs: email_id must query email_embeddings; prom_id must query prom_embeddings.
If the user asks to show an email thread and retrieved results contain raw_thread with email_id, that is enough evidence; finalize with an exact email_embeddings lookup by that email_id.
Do not include exploratory steps, failed searches, broad semantic searches, duplicate steps, or steps that returned related-but-not-answering files.
A result is useful only if you would rely on that specific returned row in the final answer.
The server will use this final AgentAction to rebuild the retained context and populate the PROM/email side panels, so unrelated files must be omitted.
Do not write anything else and make sure to follow the AgentAction Schema.
"""
