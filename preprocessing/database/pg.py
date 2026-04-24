import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def init_email_table(con = None, drop_table: bool = False):
    """Initialize database tables. Pass existing connection to reuse it."""
    should_close = False
    if con is None:
        con = get_db_connection()
        should_close = True
    cursor = con.cursor()

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if drop_table:
        cursor.execute("DROP TABLE IF EXISTS email_embeddings")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_embeddings (
        email_id SERIAL PRIMARY KEY,
        date VARCHAR(20) NOT NULL,
        requestor VARCHAR(100) NOT NULL,
        filename VARCHAR(100) NOT NULL,
        prom_approval VARCHAR(50),
        prom_considerations TEXT NOT NULL,
        chemicals TEXT NOT NULL,
        processes TEXT NOT NULL,
        llm_context TEXT NOT NULL,
        raw_thread TEXT NOT NULL,
        embedded_string TEXT NOT NULL,
        embedding vector(1536) NOT NULL,
        UNIQUE (date, filename, requestor, chemicals, processes)
    )
    """)
    #using HNSW when we create third DB table
    print("successfully initiated database")
    con.commit()

    if should_close:
        con.close()
        return None
    
    return con 

def init_prom_table(con = None, drop_table: bool = False):
    should_close = False
    if con is None:
        con = get_db_connection()
        should_close = True
    cursor = con.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if drop_table:
        cursor.execute("DROP TABLE IF EXISTS prom_embeddings")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prom_embeddings (
    prom_id SERIAL PRIMARY KEY,
    date VARCHAR(20) NOT NULL,
    filename TEXT NOT NULL,
    requestor VARCHAR(100) NOT NULL,
    request_title TEXT,
    chemicals_and_processes TEXT,
    request_reason TEXT,
    process_flow TEXT,
    amount_and_form TEXT,
    staff_considerations TEXT,
    raw_prom TEXT,
    embedded_string TEXT,
    request_embedding vector(1536),
    process_embedding vector(1536),
    UNIQUE (date, requestor, request_title)
    )
    """)
    print("FINISHED INITIATING TABLE")
    con.commit()

    if should_close:
        con.close()
        return None

    return con


def init_all_table(con = None, drop_table: bool = False):
    should_close = False
    if con is None:
        con = get_db_connection()
        should_close = True
    cursor = con.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if drop_table:
        cursor.execute("DROP TABLE IF EXISTS all_embeddings")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS all_embeddings (
    entry_id SERIAL PRIMARY KEY,
    prom_id INT NOT NULL UNIQUE REFERENCES prom_embeddings(prom_id),
    email_id_1 INT REFERENCES email_embeddings(email_id),
    email_id_2 INT REFERENCES email_embeddings(email_id),
    email_id_3 INT REFERENCES email_embeddings(email_id),
    prom_embedding vector(1536) NOT NULL
    )
    """)
    print("FINISHED INITIATING MATCH TABLE")
    con.commit()

    if should_close:
        con.close()
        return None

    return con



def create_hnsw_idx(con=None):
    """Build HNSW index on prom_embeddings. Call AFTER bulk insert."""
    should_close = False
    if con is None:
        con = get_db_connection()
        should_close = True
    
    cursor = con.cursor()
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS prom_emb_idx 
    ON prom_embeddings USING hnsw(embedding vector_cosine_ops)
    """)
    con.commit()
    
    if should_close:
        con.close()
        return None
    return con
