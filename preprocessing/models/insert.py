from dataclasses import asdict, dataclass, replace
from typing import Optional, List
import psycopg2
from preprocessing.database.pg import get_db_connection

@dataclass(frozen=True)
class Email:
    date: str
    filepath: str
    requestor: str
    prom_approval: Optional [str] = None
    prom_considerations: Optional [str] = None
    chemicals: Optional[str] = None
    processes: Optional[str] = None
    raw_thread: Optional[str] = None
    llm_context: Optional[str] = None
    embedded_string: Optional[str] = None
    embedding: Optional[list[float]] = None


    def insert_email(self, con):
        cursor = con.cursor()
        cursor.execute("""
        INSERT INTO email_embeddings (date, filename, requestor, prom_approval, prom_considerations, chemicals, processes, llm_context, raw_thread, embedded_string, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, filename, requestor, chemicals, processes) DO NOTHING
        RETURNING email_id
        """, (self.date, self.filepath, self.requestor, self.prom_approval, self.prom_considerations, self.chemicals, self.processes, self.llm_context, self.raw_thread, self.embedded_string, self.embedding))
        inserted_row = cursor.fetchone()
        con.commit()
        if inserted_row:
            return inserted_row[0]
        return None

@dataclass(frozen=True)
class PromForm:
    date: str
    filename: str
    requestor: str
    request_title: Optional[str] = None
    chemicals_and_processes: Optional[str] = None
    request_reason: Optional[str] = None
    process_flow: Optional[str] = None
    amount_and_form: Optional[str] = None
    staff_considerations: Optional[str] = None
    raw_prom: Optional[str] = None
    embedded_string: Optional[str] = None
    request_embedding: Optional[list[float]] = None
    process_embedding: Optional[list[float]] = None


    def insert_prom(self, con):
        cursor = con.cursor()
        cursor.execute("""
        INSERT INTO prom_embeddings (date, filename, requestor, request_title, chemicals_and_processes, request_reason, process_flow, amount_and_form, staff_considerations, raw_prom, embedded_string, request_embedding, process_embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, requestor, request_title) DO NOTHING
        RETURNING prom_id
        """, (self.date, self.filename, self.requestor, self.request_title, self.chemicals_and_processes, self.request_reason, self.process_flow, self.amount_and_form, self.staff_considerations, self.raw_prom, self.embedded_string, self.request_embedding, self.process_embedding))
        inserted_row = cursor.fetchone()
        con.commit()
        if inserted_row:
            print(inserted_row[0])
            return inserted_row[0]
        return None

    def is_empty(self) -> List[str]:
        return [field for field, value in asdict(self).items() if not value]


@dataclass(frozen=True)
class AllEntry:
    prom_id: int
    email_id_1: Optional[int] = None
    email_id_2: Optional[int] = None
    email_id_3: Optional[int] = None
    prom_embedding: Optional[list[float]] = None

    def insert_all(self, con):
        cursor = con.cursor()
        cursor.execute("""
        INSERT INTO all_embeddings (prom_id, email_id_1, email_id_2, email_id_3, prom_embedding)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (prom_id) DO NOTHING
        RETURNING entry_id
        """, (self.prom_id, self.email_id_1, self.email_id_2, self.email_id_3, self.prom_embedding))
        inserted_row = cursor.fetchone()
        con.commit()
        if inserted_row:
            return inserted_row[0]
        return None


#for searching up the prom_ids embedding vector

def get_prom_embedding_vector(row_id: int):
    """
    get the embedding vector of the prom form using row_id
    then return the embedding vector of the row_id.
    this is using the unique entry id for prom
    """
    con = get_db_connection()
    try:
        cursor = con.cursor()
        cursor.execute("""
        SELECT request_embedding
        FROM prom_embeddings
        WHERE prom_id = %s
        """, (row_id,))
        result = cursor.fetchone()
        if result is None:
            return None
        return result[0]
    finally:
        con.close()


def find_email_matches(prom_vector):
    con = get_db_connection()
    try:
        cursor = con.cursor()
        cursor.execute("""
        SELECT email_id
        FROM email_embeddings
        WHERE 1 - (embedding <=> %s::vector) > 0.85
        ORDER BY embedding <=> %s::vector
        LIMIT 3
        """, (prom_vector, prom_vector))
        results = cursor.fetchall()
        return [row[0] for row in results]
    finally:
        con.close()


def claim_unmatched_all_entries(con, current_latest_email_id: int, limit: int):
    cursor = con.cursor()
    cursor.execute(
        """
        WITH candidates AS (
            SELECT entry_id, prom_id, prom_embedding
            FROM all_embeddings
            WHERE email_id_1 IS NULL
              AND email_id_2 IS NULL
              AND email_id_3 IS NULL
              AND last_matched_against_email_id < %s
            ORDER BY entry_id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        )
        UPDATE all_embeddings a
        SET last_matched_against_email_id = %s
        FROM candidates
        WHERE a.entry_id = candidates.entry_id
        RETURNING candidates.entry_id, candidates.prom_id, candidates.prom_embedding
        """,
        (current_latest_email_id, limit, current_latest_email_id),
    )
    rows = cursor.fetchall()
    con.commit()
    return rows


def update_all_entry_matches(
    con,
    entry_id: int,
    current_latest_email_id: int,
    matching_emails: List[int],
):
    cursor = con.cursor()
    cursor.execute(
        """
        UPDATE all_embeddings
        SET email_id_1 = %s,
            email_id_2 = %s,
            email_id_3 = %s,
            last_matched_against_email_id = %s
        WHERE entry_id = %s
        """,
        (
            matching_emails[0] if len(matching_emails) > 0 else None,
            matching_emails[1] if len(matching_emails) > 1 else None,
            matching_emails[2] if len(matching_emails) > 2 else None,
            current_latest_email_id,
            entry_id,
        ),
    )
    con.commit()
