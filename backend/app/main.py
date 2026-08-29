import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, get_db
from .models import Document, DocumentChunk, User
from .schemas import AskResponse, Credentials, DocumentOut, SearchRequest, SearchResponse, Source, Token
from .services.documents import DocumentProcessor, LocalStorageService
from .services.retrieval import EmbeddingService, LLMService, RetrievalService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="CloudMind API", version="0.1.0")
security = HTTPBearer()
password_hash = PasswordHash.recommended()
processor, storage = DocumentProcessor(), LocalStorageService()
embeddings = EmbeddingService(); retrieval = RetrievalService(embeddings); llm = LLMService()

@app.on_event("startup")
def startup(): Base.metadata.create_all(engine)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    try: payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if not user: raise HTTPException(401, "User no longer exists")
    return user

def token_for(user: User) -> Token:
    encoded = jwt.encode({"sub": user.id, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return Token(access_token=encoded)

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/auth/register", response_model=Token, status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Email is already registered")
    user = User(email=body.email, password_hash=password_hash.hash(body.password)); db.add(user); db.commit(); db.refresh(user)
    return token_for(user)

@app.post("/auth/login", response_model=Token)
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not password_hash.verify(body.password, user.password_hash): raise HTTPException(401, "Incorrect email or password")
    return token_for(user)

def process_document(document_id: str, user_id: str, filename: str, data: bytes):
    # In production this function is executed by a separate SQS worker.
    from .database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id); doc.status = "processing"; db.commit()
        chunks = processor.chunk(processor.extract_text(filename, data)); vectors = embeddings.embed_many(chunks)
        db.add_all([DocumentChunk(document_id=document_id, user_id=user_id, chunk_index=i, text=text, embedding_json=json.dumps(vector)) for i, (text, vector) in enumerate(zip(chunks, vectors))])
        doc.status = "ready"; db.commit()
    except Exception as exc:
        doc = db.get(Document, document_id)
        if doc: doc.status = "failed"; doc.error_message = str(exc)[:500]; db.commit()
        logger.exception("document_processing_failed", extra={"document_id": document_id})
    finally: db.close()

@app.post("/documents/upload", response_model=DocumentOut, status_code=202)
async def upload_document(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith((".txt", ".pdf")): raise HTTPException(415, "Only PDF and TXT files are supported")
    data = await file.read()
    if not data or len(data) > settings.max_upload_bytes: raise HTTPException(413, "File is empty or exceeds the upload limit")
    doc = Document(user_id=user.id, filename=file.filename, content_type=file.content_type or "application/octet-stream", size_bytes=len(data)); db.add(doc); db.commit(); db.refresh(doc)
    storage.put(f"documents/{user.id}/{doc.id}/original", data)
    process_document(doc.id, user.id, doc.filename, data)
    db.refresh(doc); return doc

@app.get("/documents", response_model=list[DocumentOut])
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).all()

@app.get("/documents/{document_id}", response_model=DocumentOut)
def document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not doc: raise HTTPException(404, "Document not found")
    return doc

@app.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not doc: raise HTTPException(404, "Document not found")
    storage.delete(f"documents/{user.id}/{doc.id}/original"); db.delete(doc); db.commit()

def as_source(result) -> Source:
    score, chunk, filename = result
    return Source(document_id=chunk.document_id, document_name=filename, chunk_id=chunk.id, text=chunk.text, score=round(score, 4))

@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return SearchResponse(sources=[as_source(row) for row in retrieval.search(db, user.id, body.query, body.top_k)])

@app.post("/ask", response_model=AskResponse)
def ask(body: SearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sources = [as_source(row) for row in retrieval.search(db, user.id, body.query, body.top_k)]
    return AskResponse(answer=llm.answer(body.query, [source.model_dump() for source in sources]), sources=sources)
