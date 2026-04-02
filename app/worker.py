import asyncio
import redis.asyncio as redis
from typing import List
import os
import sys
import random
from pydantic import BaseModel
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREPROCESSING_DIR = os.path.join(ROOT_DIR, "preprocessing")
if PREPROCESSING_DIR not in sys.path:
    sys.path.append(PREPROCESSING_DIR)

from preprocessing.database.pg import get_db_connection
from preprocessing.test import fork_then_extract
from preprocessing.prom_pipeline import filter_duplicates, run_prom_pipeline
from preprocessing.order_emails import create_dict_of_threads, get_email_by_msgid
from preprocessing.filter_emails import extract_main_message
from preprocessing.embed_emails import run_pipeline
from preprocessing.models.insert import Email


redis_file_queue = redis.Redis(host="redis", port=6379, db=1, decode_responses=True)
redis_file_status_store = redis.Redis(host="redis", port=6379, db=3)

PROM_QUEUE_NAME = "pending_prom_files"
EMAIL_QUEUE_NAME = "pending_email_files"
MAX_PROM_FILES = 15
MAX_EMAIL_FILES = 6
BATCH_FILL_WINDOW_SECONDS = 0.2
BATCH_FILL_POLL_INTERVAL_SECONDS = 0.02



class FileStatusUpdate(BaseModel):
    user_id: str
    upload_id:str
    status: str
    kind: str
    filepath: str


class FileObject(BaseModel):
    user_id: str
    upload_id: str
    kind: str
    filepath: str



def __user_key(user_id: str):
    return f"user:upload_file_status:{user_id}"


async def push_status(file_obj: FileObject, status: str):
    item_status_obj = FileStatusUpdate(
        user_id=file_obj.user_id,
        upload_id=file_obj.upload_id,
        status=status,
        kind=file_obj.kind,
        filepath=file_obj.filepath,
    )
    await redis_file_status_store.rpush(
        __user_key(file_obj.user_id),
        json.dumps(item_status_obj.model_dump()),
    )



#PROM PIPELINE

def prom_extraction(batch: List[str]):
    problematic_files = []
    results = []
    for file_obj_str in batch:
        file_obj = FileObject(**json.loads(file_obj_str))
        prom_form = fork_then_extract(file_obj.filepath)
        if isinstance(prom_form, str) or prom_form is None:
            problematic_files.append(prom_form)
        else:
            results.append(prom_form)
    results = filter_duplicates(results)
    return results, problematic_files

async def prom_process_batch(file_batch: List[str]):
    file_objects = [FileObject(**json.loads(file_obj_str)) for file_obj_str in file_batch]
    results, problematic_files = prom_extraction(file_batch)
    if results:
        await run_prom_pipeline(results, con)
        for file_obj in file_objects:
            await push_status(file_obj, "Inserted Into Database")
            await push_status(file_obj, "Complete")
    return problematic_files


async def email_pipeline(email_batch: List[Email]):
    num_of_succ_inserts = await run_pipeline(email_batch, con)
    return num_of_succ_inserts


async def create_threads_of_emails(batch: List[str]):
    results = 0
    for file_obj_str in batch:
        file_obj = FileObject(**json.loads(file_obj_str))
        dict_of_threads, msg_start, msg_end = create_dict_of_threads(file_obj.filepath)
        if not dict_of_threads:
            print(f"no threads found in {file_obj.filepath}")
            continue
        email_objects = []
        for keys, vals in dict_of_threads.items():
            date, requestor = keys
            for val in vals:
                thread = ""
                for item in val:
                    email = get_email_by_msgid(file_obj.filepath, msg_start, msg_end, item)
                    if email is None:
                        print(f"cannot find email in {file_obj.filepath}, byte position")
                        continue
                    processed_email = extract_main_message(email)
                    thread = thread + "\n" + processed_email
                email_object = Email(date=date, filepath=file_obj.filepath, requestor=requestor, raw_thread=thread)
                email_objects.append(email_object)
        print(f"created {len(email_objects)} email_objects")
        print(f"SENDING {len(email_objects)} to EMAIL pipeline")
        await push_status(file_obj, "Sending for Embedding")
        results += await email_pipeline(email_objects)
        await push_status(file_obj, "Inserted Into Database")
        await push_status(file_obj, "Complete")
    return results


#EMAIL PIPELINE

async def collect_batch():
    #queue prioritization does not scale to more than 2 queues right now, fix later
    queue_order = (
        [PROM_QUEUE_NAME, EMAIL_QUEUE_NAME]
        if random.random() < 0.5
        else [EMAIL_QUEUE_NAME, PROM_QUEUE_NAME]
    )
    queue_name, first_item = await redis_file_queue.blpop(queue_order, timeout=0)
    if queue_name == PROM_QUEUE_NAME:
        max_files = MAX_PROM_FILES
    elif queue_name == EMAIL_QUEUE_NAME:
        max_files = MAX_EMAIL_FILES
    else:
        max_files = 1

    batch = [first_item]
    print(f"{first_item} is the first item")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + BATCH_FILL_WINDOW_SECONDS
    while len(batch) < max_files:
        item = await redis_file_queue.lpop(queue_name)
        if item is not None:
            batch.append(item)
            continue

        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(BATCH_FILL_POLL_INTERVAL_SECONDS, remaining))
    #consider the creation of a route on the server that does the sync portion of this and pushes to redis as an alternative option
    for item in batch:
        item_obj = FileObject(**json.loads(item))
        await push_status(item_obj, "File Extraction Started")
    return (queue_name, batch)



async def worker():
    while True:
        queue_name, batch = await collect_batch()
        if not batch:
            continue
        if queue_name == PROM_QUEUE_NAME:
            await prom_process_batch(batch)
        elif queue_name == EMAIL_QUEUE_NAME:
            await create_threads_of_emails(batch)

if __name__ == "__main__":
    try: 
        con = get_db_connection()
    except Exception as e:
        print("Could not establish connection to database")
        print(e)
        raise SystemExit(1)
    asyncio.run(worker())
