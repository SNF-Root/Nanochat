import os
import asyncio
from openai import AsyncOpenAI
from typing import List
import json
from models.insert import Email
from dataclasses import replace



client = AsyncOpenAI(
    api_key=os.environ.get("STANFORD_API_KEY"),
    base_url="https://aiapi-prod.stanford.edu/v1"
)


MAX_CONCURRENT_REQUESTS = 20


SYSTEM_PROMPT_TEMPLATE = """
You are an information extraction engine. Output MUST be valid JSON only. No markdown. No explanations. No extra keys.

SCHEMA (must match exactly)
{{
  "prom_request": string,
  "prom_considerations": string,
  "chemicals_mentioned": [string],
  "processes_mentioned": [string],
  "prom_approval": "approved" | "rejected" | "hard_to_tell",
  "approval_evidence": string,
  "llm_context": string
}}

RULES (CRITICAL)
- EARLY EXIT: If EMAIL_THREAD is NOT about a PROM request (e.g., scheduling, administrative, general discussion, announcements, lab tours, nanofabrication interest or any topic unrelated to chemicals, materials, or the request of doing a certain nanofabrication process), return ONLY: {{"prom_request": "", "prom_considerations":"", "chemicals_mentioned":[], "processes_mentioned":[], "prom_considerations":"", "prom_approval":"", "approval_evidence": "", "llm_context": ""}}
- Use ONLY the text in EMAIL_THREAD. Do NOT guess.
- Do NOT include email headers/metadata inside any extracted strings (e.g., lines containing "From:", "To:", "Cc:", "Subject:", dates/timestamps).
- Do NOT include quoted reply history (lines starting with ">").
- prom_request and prom_considerations are the ONLY fields you may paraphrase/clean for clarity.
- chemicals_mentioned, processes_mentioned, and approval_evidence MUST be VERBATIM spans from EMAIL_THREAD. Do NOT paraphrase. Do NOT normalize. Do NOT correct spelling.
- Keep strings minimal but complete. Preserve newlines in extracted verbatim spans exactly as they appear.

IMPORTANT ROLE RULE
- prom_considerations MUST come ONLY from the committee/reviewer/responder side (i.e., messages evaluating the request).
- Do NOT use the requestor's own message content as prom_considerations.
- If the thread contains only the request (no committee/reviewer response/evaluation), set prom_considerations to "Hard_to_see_considerations".

FIELD DEFINITIONS
- prom_request:
  The request or proposal content (what is being asked or proposed). Prefer the earliest request if multiple exist.
  You MAY paraphrase/clean this field, but it must remain faithful to the thread.
  FORMAT: Structure as "[ACTION] [CHEMICAL/MATERIAL] using [PROCESS/TOOL] for [PURPOSE]"
  Example: "Deposit Ti/Pt contacts using Lesker sputter for high-temperature conductivity measurement of solid electrolyte samples"
  Do NOT artificially shorten - aim for 200 - 300 tokens to capture full context. Include relevant details about materials, tools, and goals.

- prom_considerations:
  Any evaluative reasoning, considerations, constraints, opinions, risks, caveats, suggestions, or conditional statements about the request,
  BUT ONLY from the committee/reviewer/responder (not the requestor).
  Do NOT include explicit approval or rejection language here.
  If none exist AND there is a clear committee/reviewer response present, set to "No Considerations were found".
  If no committee/reviewer response/evaluation is present, set to "Hard_to_see_considerations".
  You MAY paraphrase/clean this field, but it must remain faithful to the thread.

- chemicals_mentioned:
  A JSON array of VERBATIM chemical mentions found in EMAIL_THREAD. Chemicals include chemical species, gases, acids/bases, solvents, resists, precursors, dopants, reagents, or chemical formulas.
  - Only include chemicals explicitly mentioned in EMAIL_THREAD (excluding headers and quoted history).
  - Each list item MUST be copied verbatim from the thread (exact casing/spaces/punctuation).
  - Deduplicate by exact string match (case-sensitive) and preserve first-seen order.
  - If none exist, return [].

- processes_mentioned:
  A JSON array of VERBATIM process mentions found in EMAIL_THREAD. Processes include fabrication/processing steps, etch/deposition/clean steps, lithography steps, metrology steps, or named process flows.
  Examples include but are not limited to: "ALD", "PECVD", "RIE", "ICP", "wet etch", "lift-off", "photolithography", "descum", "anneal", "oxidation", "develop", "strip", "ashing", "sputter".
  - Only include processes explicitly mentioned in EMAIL_THREAD (excluding headers and quoted history).
  - Each list item MUST be copied verbatim from the thread (exact casing/spaces/punctuation).
  - Deduplicate by exact string match (case-sensitive) and preserve first-seen order.
  - If none exist, return [].

- prom_approval:
  - "approved" ONLY if explicit approval/acceptance language exists in EMAIL_THREAD.
  - "rejected" ONLY if explicit denial language exists in EMAIL_THREAD.
  - Otherwise "hard_to_tell".

- approval_evidence:
  Verbatim quote(s) that justify prom_approval.
  - If prom_approval is "approved" or "rejected", copy the shortest verbatim span(s) that clearly justify the label.
  - If prom_approval="hard_to_tell", set approval_evidence="".

- llm_context:
  YOUR domain knowledge that enriches the extracted information. Consider the prom_request, prom_considerations, chemicals_mentioned, and processes_mentioned, then ADD relevant context from your training knowledge.
  Include: chemical properties, safety considerations, common use cases, process compatibility, typical equipment requirements, or known best practices.
  This should SUPPLEMENT (not repeat) the verbatim extractions.
  Aim for ~200 tokens. Be specific and technically relevant to semiconductor/nanofabrication contexts.

EMAIL_THREAD:
<<<THREAD
{thread}
THREAD>>>

OUTPUT
Return exactly one JSON object matching SCHEMA. JSON only.
"""




async def extract_prom_json(email_thread: str) -> str:
    """
    Async version - takes a raw email thread and returns the extracted PROM JSON.
    Does not block CPU while waiting for OpenAI response.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(thread=email_thread)

    response = await client.chat.completions.create(
        model="gpt-4.omini",
        messages=[
            {"role": "system", "content": system_prompt}
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content

async def embed_concat_json(concat_thread: str) -> List[float]:
    """
    Async version of embedding, comes post LLM JSON retrieval in the pipeline
    """

    response = await client.embeddings.create(
        model = "text-embedding-ada-002",
        input=concat_thread
    )

    return response.data[0].embedding


def validating_llm_response(result: str) -> dict | None:
    """Parse LLM response, return dict matching Email dataclass attributes."""
    json_object = json.loads(result)
    chemicals_mentioned = json_object["chemicals_mentioned"]
    processes_mentioned = json_object["processes_mentioned"]
    
    if not chemicals_mentioned and not processes_mentioned:
        print("off topic email")
        return None
    
    prom_request = json_object["prom_request"]
    prom_considerations = json_object["prom_considerations"]
    llm_context = json_object["llm_context"]
    prom_approval = json_object["prom_approval"]
    
    chemicals_string = " ".join(chemicals_mentioned)
    processes_string = " ".join(processes_mentioned)
    #REQUEST
    embed_string = f"Reason for Request: {prom_request}\n Process Flow: {llm_context}\n The chemical or material: {chemicals_string} {processes_string}"
    return {
        "embedded_string": embed_string,
        "prom_considerations": prom_considerations,
        "prom_approval": prom_approval,
        "chemicals": chemicals_string,
        "processes": processes_string,
        "llm_context": llm_context
    }



        
async def process_single(email_object: Email, llm_sem):
    """Each thread flows through LLM → validate → embed → return updated Email."""
    async with llm_sem:
        llm_result = await extract_prom_json(email_object.raw_thread)
    
    if llm_result is None:
        return None
    
    extracted = validating_llm_response(llm_result)
    if extracted is None:
        return None
    
    embedding = await embed_concat_json(extracted["embedded_string"])
    
    # Unpack dict + add embedding, all keys match Email attributes
    return replace(email_object, embedding=embedding, **extracted)




async def run_pipeline(email_objects: List[Email], con):
    llm_sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    inserted_counter = 0
    tasks = [process_single(email_object, llm_sem) for email_object in email_objects]
    for coro in asyncio.as_completed(tasks):
        finished_email_object = await coro
        if finished_email_object:
            print(finished_email_object.embedded_string)
            print("*" * 100)
            finished_email_object.insert_email(con)
            inserted_counter += 1
    print(f"inserted {inserted_counter} email objects")
    return inserted_counter