from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class DocumentOut(BaseModel):
    id: str; filename: str; content_type: str; size_bytes: int; status: str
    error_message: str | None; created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)

class Source(BaseModel):
    document_id: str; document_name: str; chunk_id: str; text: str; score: float

class SearchResponse(BaseModel):
    sources: list[Source]

class AskResponse(SearchResponse):
    answer: str

class JobOut(BaseModel):
    id: str; document_id: str; status: str; attempts: int; error_message: str | None
    created_at: datetime; completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
