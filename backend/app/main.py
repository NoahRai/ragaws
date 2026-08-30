import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, get_db
from .models import Document, DocumentChunk, ProcessingJob, User
from .schemas import AskResponse, Credentials, DocumentOut, JobOut, SearchRequest, SearchResponse, Source, Token
from .services.documents import DocumentProcessor, build_storage, document_object_key
from .services.jobs import LocalJobQueue, SQSJobQueue
from .processing import process_job
from .services.retrieval import EmbeddingService, LLMService, RetrievalService
from .observability import configure_logging, metrics

logger = configure_logging()
@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title="CloudMind API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()
password_hash = PasswordHash.recommended()
processor = DocumentProcessor()
storage = build_storage(settings.storage_backend, settings.s3_bucket, settings.aws_region)
embeddings = EmbeddingService(); retrieval = RetrievalService(embeddings); llm = LLMService()
def run_local_job(job_id: str) -> None: process_job(job_id, storage, processor, embeddings)
queue = SQSJobQueue(settings.sqs_queue_url or "", settings.aws_region) if settings.queue_backend == "sqs" else LocalJobQueue(run_local_job)

@app.middleware("http")
async def observe_request(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        metrics.increment("api_requests_failed"); metrics.observe_ms("api_request_duration", duration_ms)
        logger.exception("api_request_failed", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "duration_ms": round(duration_ms, 2)})
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    metrics.increment("api_requests"); metrics.increment(f"api_status_{response.status_code}"); metrics.observe_ms("api_request_duration", duration_ms)
    response.headers["X-Request-ID"] = request_id
    logger.info("api_request", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": round(duration_ms, 2)})
    return response

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

@app.get("/metrics", include_in_schema=False)
def metric_snapshot():
    return Response(metrics.prometheus(), media_type="text/plain; version=0.0.4")

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

@app.post("/documents/upload", response_model=DocumentOut, status_code=202)
async def upload_document(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith((".txt", ".pdf")): raise HTTPException(415, "Only PDF and TXT files are supported")
    data = await file.read()
    if not data or len(data) > settings.max_upload_bytes: raise HTTPException(413, "File is empty or exceeds the upload limit")
    doc = Document(user_id=user.id, filename=file.filename, content_type=file.content_type or "application/octet-stream", size_bytes=len(data)); db.add(doc); db.commit(); db.refresh(doc)
    storage.put(document_object_key(user.id, doc.id, doc.filename), data, doc.content_type)
    job = ProcessingJob(document_id=doc.id, user_id=user.id); db.add(job); db.commit(); db.refresh(job)
    queue.enqueue(job.id)
    metrics.increment("documents_uploaded")
    db.refresh(doc); return doc

@app.get("/documents", response_model=list[DocumentOut])
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).all()

@app.get("/documents/{document_id}", response_model=DocumentOut)
def document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not doc: raise HTTPException(404, "Document not found")
    return doc

@app.get("/jobs/{job_id}", response_model=JobOut)
def job_status(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.user_id == user.id))
    if not job: raise HTTPException(404, "Job not found")
    return job

@app.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not doc: raise HTTPException(404, "Document not found")
    storage.delete(document_object_key(user.id, doc.id, doc.filename)); db.delete(doc); db.commit()

@app.get("/documents/{document_id}/download-url")
def document_download_url(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not doc: raise HTTPException(404, "Document not found")
    if settings.storage_backend != "s3": raise HTTPException(501, "Download URLs are available with S3 storage")
    return {"url": storage.download_url(document_object_key(user.id, doc.id, doc.filename), settings.presigned_url_expiry_seconds)}

def as_source(result) -> Source:
    score, chunk, filename = result
    return Source(document_id=chunk.document_id, document_name=filename, chunk_id=chunk.id, text=chunk.text, score=round(score, 4))

@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return SearchResponse(sources=[as_source(row) for row in retrieval.search(db, user.id, body.query, body.top_k)])

@app.post("/ask", response_model=AskResponse)
def ask(body: SearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sources = [as_source(row) for row in retrieval.search(db, user.id, body.query, body.top_k)]
    metrics.increment("questions_asked")
    return AskResponse(answer=llm.answer(body.query, [source.model_dump() for source in sources]), sources=sources)
