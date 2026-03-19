import json
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatObject(BaseModel):
    chat_id: Optional[int] = None
    session_id: str
    chat_name: str
    chat_content: list[dict[str, Any]] = Field(default_factory=list)


def init_chat_table(con, drop_table: bool = False):
    cursor = con.cursor()
    if drop_table:
        cursor.execute("DROP TABLE IF EXISTS chat_objects")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_objects (
            chat_id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            chat_name TEXT NOT NULL,
            chat_content JSONB NOT NULL DEFAULT '[]'::jsonb
        )
        """
    )
    con.commit()
    return con


def migrate_chat_table_to_jsonb(con):
    cursor = con.cursor()
    cursor.execute(
        """
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'chat_objects'
          AND column_name = 'chat_content'
        """
    )
    row = cursor.fetchone()
    if row is None:
        return con

    _, udt_name = row
    if udt_name == "jsonb":
        return con

    if udt_name == "_text":
        cursor.execute(
            """
            ALTER TABLE chat_objects
            ALTER COLUMN chat_content DROP DEFAULT,
            ALTER COLUMN chat_content TYPE JSONB
                USING COALESCE(to_jsonb(chat_content), '[]'::jsonb),
            ALTER COLUMN chat_content SET DEFAULT '[]'::jsonb,
            ALTER COLUMN chat_content SET NOT NULL
            """
        )
        con.commit()
        return con

    raise ValueError(f"Unsupported chat_content type for migration: {udt_name}")


def insert_chat_object(con, chat_object: ChatObject) -> ChatObject:
    cursor = con.cursor()
    cursor.execute(
        """
        INSERT INTO chat_objects (session_id, chat_name, chat_content)
        VALUES (%s, %s, %s::jsonb)
        RETURNING chat_id
        """,
        (
            chat_object.session_id,
            chat_object.chat_name,
            json.dumps(chat_object.chat_content),
        ),
    )
    chat_id = cursor.fetchone()[0]
    con.commit()
    return ChatObject(
        chat_id=chat_id,
        session_id=chat_object.session_id,
        chat_name=chat_object.chat_name,
        chat_content=chat_object.chat_content,
    )

