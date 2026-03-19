import asyncio
import redis.asyncio as redis
from typing import List
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREPROCESSING_DIR = os.path.join(ROOT_DIR, "preprocessing")
if PREPROCESSING_DIR not in sys.path:
    sys.path.append(PREPROCESSING_DIR)

from preprocessing.database.pg import get_db_connection
from preprocessing.test import fork_then_extract
from preprocessing.prom_pipeline import filter_duplicates, run_prom_pipeline


redis_file_queue = redis.Redis(host="redis", port=6379, db=1, decode_responses=True)

QUEUE_NAME = "pending_files"
MAX_FILES = 20



def prom_extraction(batch: List[str]):
    problematic_files = []
    results = []
    for filepath in batch:
        prom_form = fork_then_extract(filepath)
        if isinstance(prom_form, str) or prom_form is None:
            problematic_files.append(prom_form)
        else:
            results.append(prom_form)
    results = filter_duplicates(results)
    return results, problematic_files


async def process_batch(file_batch: List[str]):
    results, problematic_files = prom_extraction(file_batch)
    if results:
        await run_prom_pipeline(results, con)
    return problematic_files


async def collect_batch():
    _, first_item = await redis_file_queue.blpop(QUEUE_NAME, timeout=0)
    batch = [first_item]
    while len(batch) < MAX_FILES:
        item = await redis_file_queue.lpop(QUEUE_NAME)
        if item is None:
            break
        batch.append(item)
    return batch

async def worker():
    while True:
        batch = await collect_batch()
        if not batch:
            continue
        await process_batch(batch)


if __name__ == "__main__":
    try: 
        con = get_db_connection()
    except Exception as e:
        print("Could not establish connection to database")
        print(e)
        raise SystemExit(1)
    asyncio.run(worker())
