from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Tuple, Literal

#an action is referred to one set of mutually exclusive steps
class SQLQuery(BaseModel):
    target_table: str
    target_columns: List[str]
    target_string: List[str]
    column_to_search_target_string: str
    row_limit: int = Field(..., ge=1, le=5)
    char_limit: int = Field(..., ge=100)

class SemanticSearch(BaseModel):
    target_table: str
    target_columns: List[str]
    query_str: str
    row_limit: int = Field(..., ge = 1, le = 5)
    cell_char_limit: int = Field(100, ge = 100)
    min_similarity_score: float = Field(0.84, ge=0.8, le=0.9)

class Step(BaseModel): 
    step_number: int 
    reason_for_step: str
    action_type: Literal["semantic_search", "sql_query"]
    sql_query: Optional[SQLQuery] = None
    semantic_search: Optional[SemanticSearch] = None

    @model_validator(mode="after")
    def validate_query_payload(self):
        #make sure that one of the queries is filled
        if self.sql_query is None and self.semantic_search is None:
            raise ValueError(f"Every step requires either a semantic search query or sql query, this has None")
        if self.sql_query and self.semantic_search:
            raise ValueError(f"Cannot have both sql query and semantic search in a single step")
        if self.action_type == "semantic_search" and not self.semantic_search or self.action_type == "sql_query" and not self.sql_query:
            raise ValueError(f"action type must match what type of query you are trying to send")
        return self

class AgentAction(BaseModel):
    goal: str
    batch_reason: str
    max_steps: int = Field(..., ge=1, le=4)
    steps: list[Step]
    after_execution: Literal["return_to_llm", "generate_final_answer"]

    @model_validator(mode="after")
    def validate_step_number(self):
        if len(self.steps) > self.max_steps or len(self.steps) < 1:
            raise ValueError("number of steps does not falled in the allowed range")
        contiguous_list_comparison = list(range(1, len(self.steps) + 1))
        steps_list = [step.step_number for step in self.steps]
        if contiguous_list_comparison != steps_list:
            raise ValueError("step numbers are not in the correct order for list of steps returned by agent")
        return self 
    
class ExecutedStep(BaseModel):
    step_number: int
    reason_for_step: str
    action_type: Literal["semantic_search", "sql_query"]
    sql_params: Optional[SQLQuery] = None
    semantic_params: Optional[SemanticSearch] = None
    query_results: List[dict]


class ExecutedAgentSteps(BaseModel):
    list_of_executed_steps: List[ExecutedStep]

class AgentRetrievalResponse(BaseModel):
    text: Optional[str] = None
    list_of_executed_steps: List[ExecutedStep]
    done: bool
    retrieved_entries: List[dict] = []

class RetrievalPlanningDecision(BaseModel):
    needs_retrieval: bool
    rewritten_query: str
    answer_from_chat_context: Optional[str] = None
    reason: str

class AgentRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    text: str


class SearchResult(BaseModel):
    id: int
    title: str
    similarity: float
    prom_filename: Optional[str] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]

class SearchStartResponse(BaseModel):
    session_id: str
    query: str


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
