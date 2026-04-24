
from preprocessing.models.insert import PromForm
import os
from multiprocessing import Pool
import time
from typing import List
from dataclasses import replace
from preprocessing.database.pg import get_db_connection, init_prom_table
import asyncio
from preprocessing.test import fork_then_extract, build_embed_string
from openai import AsyncOpenAI



MAX_CONCURRENT_PROM_REQUESTS = 20


client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)


async def embed_concat_json(concat_thread: str) -> List[float]:
    """
    Async version of embedding, comes post LLM JSON retrieval in the pipeline
    """
    response = await client.embeddings.create(
        model = "text-embedding-ada-002",
        input=concat_thread
    )
    

    return response.data[0].embedding

# def process_file(file_path) -> PromForm:
#     is_docx = file_path.lower().endswith('.docx')
#     if is_docx:
#         prom = extract_prom_from_docx(file_path, debug=False)
#     else:
#         print("PDF are hanging, skipping for now")
#         # prom = extract_prom_from_docling(file_path, debug=False)
#         prom = None

#     # prom = extract_prom_unified(file_path, debug=False)
#     if prom is None:
#         return None, file_path
#     return prom, None



def filter_duplicates(prom_forms: List[PromForm]) -> List[PromForm]:
    """
    Filter out duplicate PromForms based on (date, requestor, request_title).
    Returns list of unique PromForms.
    """
    seen = set()
    unique = []
    duplicates = 0
    
    for prom in prom_forms:
        if prom.date is None or prom.requestor is None or prom.request_title is None:
            continue
        
        key = (prom.date.lower(), prom.requestor.lower(), prom.request_title.lower())
        
        if key in seen:
            print(f"Duplicate found: {prom.request_title} by {prom.requestor} on {prom.date}")
            duplicates += 1
        else:
            seen.add(key)
            unique.append(prom)
    
    if duplicates > 0:
        print(f"Filtered out {duplicates} duplicate(s), {len(unique)} unique remaining")
    
    return unique

async def embed_pipeline(prom_form: PromForm, embed_sem: asyncio.Semaphore) -> PromForm:
    required_fields = {
        'date',
        'filename',
        'requestor',
        'request_title',
        'chemicals_and_processes',
        'request_reason',
        'process_flow',
        'amount_and_form',
    }
    has_empty = [f for f in prom_form.is_empty() if f in required_fields]
    if has_empty:
        return f"{', '.join(has_empty)} is returning None | {prom_form.filename}"
    
    # Build the embed string from form fields
    embed_string = build_embed_string(prom_form)
    if not embed_string:
        return f"Could not build embed string in {prom_form.filename}:{has_empty}"
    
    async with embed_sem:
        prom_embed = await embed_concat_json(embed_string)
    async with embed_sem:
        process_embed = await embed_concat_json(prom_form.process_flow)
    
    return replace(prom_form, embedded_string=embed_string, request_embedding=prom_embed, process_embedding=process_embed)

async def run_prom_pipeline(prom_objects: List[PromForm], con) -> int:
    embed_sem = asyncio.Semaphore(MAX_CONCURRENT_PROM_REQUESTS)
    tasks = [embed_pipeline(prom_object, embed_sem=embed_sem) for prom_object in prom_objects]
    prom_ids = []
    for coro in asyncio.as_completed(tasks):
        finished_prom_object = await coro
        # Skip if embed_pipeline returned an error string
        if isinstance(finished_prom_object, str):
            print(finished_prom_object)
            print(f"Skipping: {finished_prom_object}")
            continue
        prom_id = finished_prom_object.insert_prom(con)
        if prom_id is not None:
            prom_ids.append(prom_id)
            print(f"Finished Inserting {finished_prom_object.request_title}")
        else:
            print("Skipping insertion, duplicate entry exists in prom_embeddings")
    return prom_ids 


if __name__ == "__main__":
    print("--- Extracting PROM Forms ---")
    pdf_path = "../files/promForms/"

    cpu_count = os.cpu_count()
    print(f"Running {cpu_count - 4} processes simultaneously")

    con = get_db_connection()
    try: 
        con = init_prom_table(con=con, drop_table=True) 
    except Exception as e:
        print("Could not initiate Table")
        print(e)

    prom_dirs = ["../files/promForms/2022"]
    for prom_dir in prom_dirs:
        pdf_files = [os.path.join(prom_dir, f) for f in os.listdir(prom_dir) 
                    if f.endswith(('.pdf', '.docx', '.PDF', '.DOCX'))]
        print(f"Found {len(pdf_files)} files to process")
        if not pdf_files:
            print(f"No files found in {prom_dir}")
            raise SystemExit(0)
        start = time.perf_counter()
        processed_files = 0
        pool = Pool(processes = (cpu_count - 4))
        results = []
        problematic_files = []
        try:
            for result in pool.imap_unordered(fork_then_extract, pdf_files):
                if isinstance(result, str):
                    problematic_files.append(result)
                elif result is None:
                    problematic_files
                else:
                    processed_files += 1
                    print(f"Finished processing {result.filename}")
                    print(f"Finished {processed_files/len(pdf_files)*100:.1f}%")
                    results.append(result)
                # if bad:
                #     problematic_files.append(bad)
                # elif result:
                #     processed_files += 1
                #     print(f"Finished processing {result.filename}")
                #     print(f"Finished {processed_files/len(pdf_files)*100:.1f}%")
                # results.append(result)
        finally:
            pool.terminate()
            pool.join()
        
        print(f"Problematic files: {problematic_files}")
        #OPTIMIZE THIS, can do this in the pipeline on insertion instead of another o(N) operation
        print(f"successfully process {processed_files}/{len(pdf_files)}")
        print(f"Finished {processed_files/len(pdf_files)*100:.1f}%")
        results = [r for r in results if r is not None]
        results = filter_duplicates(results)

        if results:
            asyncio.run(run_prom_pipeline(results, con))
            print(f"Pipeline complete. Processed {len(results)} unique forms.")
        else:
            print("No valid results to process")

        end = time.perf_counter()
    
