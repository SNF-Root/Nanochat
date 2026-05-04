import asyncio
from dataclasses import dataclass
from pathlib import Path

from preprocessing.database.pg import get_db_connection, init_email_table
from preprocessing.filter_emails import extract_main_message
from preprocessing.models.insert import Email
from preprocessing.order_emails import create_dict_of_threads, get_email_by_msgid
import preprocessing.embed_emails as embed_module

BASE_DIR = Path("/Users/abdulhannanmohammed/Projects/PROM/files/emails/2019_emails")
INSERTED_OUT = Path("/Users/abdulhannanmohammed/Projects/PROM/inserted_threads_2019.txt")
DROPPED_OUT = Path("/Users/abdulhannanmohammed/Projects/PROM/dropped_threads_2019.txt")


@dataclass
class ThreadItem:
    idx: int
    source_file: str
    date: str
    requestor: str
    msg_count: int
    raw_thread: str
    email_obj: Email


@dataclass
class ThreadResult:
    item: ThreadItem
    status: str  # inserted | dropped
    reason: str
    inserted_email_id: int | None = None
    llm_output: str | None = None


def find_existing_email_id(con, email_obj: Email) -> int | None:
    cursor = con.cursor()
    cursor.execute(
        """
        SELECT email_id
        FROM email_embeddings
        WHERE date = %s
          AND filename = %s
          AND requestor = %s
          AND chemicals = %s
          AND processes = %s
        LIMIT 1
        """,
        (
            email_obj.date,
            email_obj.filepath,
            email_obj.requestor,
            email_obj.chemicals,
            email_obj.processes,
        ),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def build_email_objects() -> list[ThreadItem]:
    files = sorted([p for p in BASE_DIR.iterdir() if p.is_file()])
    items: list[ThreadItem] = []
    thread_idx = 0

    print(f"[build] scanning files from {BASE_DIR}")
    for file_path in files:
        print(f"[build] file={file_path}")
        dict_of_threads, msg_start, msg_end = create_dict_of_threads(str(file_path))
        if not dict_of_threads:
            print(f"[build] no_threads file={file_path}")
            continue

        for keys, vals in dict_of_threads.items():
            date, requestor = keys
            for val in vals:
                thread_idx += 1
                parts = []
                for msgid in val:
                    raw_email = get_email_by_msgid(str(file_path), msg_start, msg_end, msgid)
                    if raw_email is None:
                        print(
                            f"[build] thread={thread_idx} missing_msgid file={file_path.name} msgid=<{msgid}>"
                        )
                        continue
                    cleaned = extract_main_message(raw_email)
                    if cleaned:
                        parts.append(cleaned)

                raw_thread = "\n".join(parts).strip()
                print(
                    f"[build] thread={thread_idx} file={file_path.name} date={date} requestor={requestor} "
                    f"msg_count={len(val)} cleaned_chars={len(raw_thread)}"
                )
                email_obj = Email(date=date, filepath=str(file_path), requestor=requestor, raw_thread=raw_thread)
                items.append(
                    ThreadItem(
                        idx=thread_idx,
                        source_file=file_path.name,
                        date=date,
                        requestor=requestor,
                        msg_count=len(val),
                        raw_thread=raw_thread,
                        email_obj=email_obj,
                    )
                )

    print(f"[build] complete total_threads={len(items)}")
    return items


def _write_results(
    path: Path, title: str, results: list[ThreadResult], total_threads: int, count_label: str
) -> None:
    with path.open("w", encoding="utf-8", errors="replace") as f:
        f.write(f"{title}\n")
        f.write(f"{count_label}={len(results)}\n")
        f.write(f"total_threads={total_threads}\n\n")
        for r in results:
            item = r.item
            f.write("=" * 120 + "\n")
            f.write(f"THREAD_INDEX: {item.idx}\n")
            f.write(f"SOURCE_FILE: {item.source_file}\n")
            f.write(f"DATE: {item.date}\n")
            f.write(f"REQUESTOR: {item.requestor}\n")
            f.write(f"MESSAGE_COUNT: {item.msg_count}\n")
            f.write(f"STATUS: {r.status}\n")
            f.write(f"REASON: {r.reason}\n")
            if r.inserted_email_id is not None:
                f.write(f"EMAIL_ID: {r.inserted_email_id}\n")
            f.write("-" * 120 + "\n")
            f.write("CLEANED_THREAD_START\n")
            f.write(item.raw_thread)
            if item.raw_thread and not item.raw_thread.endswith("\n"):
                f.write("\n")
            f.write("CLEANED_THREAD_END\n")
            if r.llm_output is not None:
                f.write("-" * 120 + "\n")
                f.write("LLM_OUTPUT_START\n")
                f.write(r.llm_output)
                if r.llm_output and not r.llm_output.endswith("\n"):
                    f.write("\n")
                f.write("LLM_OUTPUT_END\n")
            f.write("=" * 120 + "\n\n")


async def process_item(item: ThreadItem, con, llm_sem: asyncio.Semaphore) -> ThreadResult:
    label = (
        f"thread={item.idx} file={item.source_file} date={item.date} "
        f"requestor={item.requestor} msg_count={item.msg_count} chars={len(item.raw_thread)}"
    )
    print(f"[thread] start {label}")

    if not item.raw_thread.strip():
        print(f"[thread] dropped stage=precheck reason=empty_cleaned_thread {label}")
        return ThreadResult(item=item, status="dropped", reason="empty_cleaned_thread")

    llm_output: str | None = None
    try:
        async with llm_sem:
            llm_output = await embed_module.extract_prom_json(item.raw_thread)
    except Exception as e:
        print(f"[thread] dropped stage=llm_or_embed error={e} {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason=f"llm_or_embed_error: {e}",
            llm_output=llm_output,
        )

    try:
        extracted = embed_module.validating_llm_response(llm_output)
    except Exception as e:
        print(f"[thread] dropped stage=llm_validation error={e} {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason=f"llm_validation_error: {e}",
            llm_output=llm_output,
        )

    if extracted is None:
        print(f"[thread] dropped stage=validation reason=filtered_or_empty {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason="filtered_or_empty",
            llm_output=llm_output,
        )

    try:
        embedding = await embed_module.embed_concat_json(extracted["embedded_string"])
    except Exception as e:
        print(f"[thread] dropped stage=embed error={e} {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason=f"embed_error: {e}",
            llm_output=llm_output,
        )

    processed = Email(
        date=item.email_obj.date,
        filepath=item.email_obj.filepath,
        requestor=item.email_obj.requestor,
        prom_approval=extracted["prom_approval"],
        prom_considerations=extracted["prom_considerations"],
        chemicals=extracted["chemicals"],
        processes=extracted["processes"],
        raw_thread=item.email_obj.raw_thread,
        llm_context=extracted["llm_context"],
        embedded_string=extracted["embedded_string"],
        embedding=embedding,
    )

    try:
        inserted_id = processed.insert_email(con)
    except Exception as e:
        print(f"[thread] dropped stage=db_insert error={e} {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason=f"db_insert_error: {e}",
            llm_output=llm_output,
        )

    if inserted_id is None:
        existing_id = find_existing_email_id(con, processed)
        if existing_id is not None:
            print(f"[thread] already_exists email_id={existing_id} {label}")
            return ThreadResult(
                item=item,
                status="inserted",
                reason="already_exists_conflict",
                inserted_email_id=existing_id,
            )
        print(f"[thread] dropped stage=db_insert reason=insert_returned_none_no_existing_row {label}")
        return ThreadResult(
            item=item,
            status="dropped",
            reason="insert_returned_none_no_existing_row",
            llm_output=llm_output,
        )

    print(f"[thread] inserted email_id={inserted_id} {label}")
    return ThreadResult(
        item=item,
        status="inserted",
        reason="insert_success",
        inserted_email_id=inserted_id,
        llm_output=llm_output,
    )


async def run_with_debug(items: list[ThreadItem], con):
    llm_sem = asyncio.Semaphore(embed_module.MAX_CONCURRENT_REQUESTS)
    print(f"[pipeline] start total_threads={len(items)}")

    tasks = [asyncio.create_task(process_item(item, con, llm_sem)) for item in items]
    results = await asyncio.gather(*tasks)

    results_sorted = sorted(results, key=lambda r: r.item.idx)
    inserted = [r for r in results_sorted if r.status == "inserted"]
    dropped = [r for r in results_sorted if r.status == "dropped"]

    _write_results(
        INSERTED_OUT, "INSERTED THREADS 2019", inserted, len(results_sorted), "inserted_threads"
    )
    _write_results(
        DROPPED_OUT, "DROPPED THREADS 2019", dropped, len(results_sorted), "dropped_threads"
    )

    print(
        f"[pipeline] complete inserted={len(inserted)} dropped={len(dropped)} total={len(results_sorted)}"
    )
    print(f"[pipeline] wrote inserted_file={INSERTED_OUT}")
    print(f"[pipeline] wrote dropped_file={DROPPED_OUT}")


if __name__ == "__main__":
    con = get_db_connection()
    init_email_table(con, drop_table=True)
    try:
        items = build_email_objects()
        asyncio.run(run_with_debug(items, con))
    finally:
        con.close()
