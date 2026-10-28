from typing import List, Any, Optional
from pydantic import BaseModel, Field

class ColumnInfo(BaseModel):
    name: str
    dtype: str

class QueryResult(BaseModel):
    sql: str = Field(description="The SQLite query that was executed")
    rows: List[dict] = Field(default_factory=list, description="Result rows as JSON objects")
    row_count: int

class FinalAnswer(BaseModel):
    summary: str = Field(description="Concise natural-language answer")
    structured: Optional[dict] = Field(
        None,
        description="Structured payload, e.g. {'top5':[...]} when the user asks for a list"
    )
    sql: str
    table_markdown: str