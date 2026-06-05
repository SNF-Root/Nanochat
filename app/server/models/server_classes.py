from pydantic import BaseModel
from typing import Optional, List, Dict, Tuple


class EmbedRequest(BaseModel):
    text: str
    entry_id: Optional[int] = None


class EmbedResponse(BaseModel):
    text: str


class AddContext(BaseModel):
    entry_ids: List[int]

class SearchResult(BaseModel):
    id: int
    title: str
    similarity: float
    prom_filename: Optional[str] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]

class SearchStartResponse(BaseModel):
    session_id: str
    prom_filename: str
    entry_id: int
    query: str
    request_title: str


class UploadFileResponse(BaseModel):
    filename: str
    path: str
    content_type : Optional[str] = None
    size_bytes : int
    status: str

class FileObject(BaseModel):
    user_id: str
    upload_id:str
    kind: str
    filepath: str


class UploadCounterResetResponse(BaseModel):
    number_of_files_cleared: int
    status_of_queue: str
