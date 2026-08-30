import json
import logging
import time
from datetime import datetime, timezone
from .database import SessionLocal
from .models import Document, DocumentChunk, ProcessingJob
from .services.documents import DocumentProcessor, StorageService, document_object_key
from .services.retrieval import EmbeddingService
from .observability import metrics

logger = logging.getLogger(__name__)


def process_job(job_id: str, storage: StorageService, processor: DocumentProcessor, embeddings: EmbeddingService) -> bool:
    """Idempotent worker operation. False leaves an SQS message for retry/DLQ."""
    db = SessionLocal()
    started = time.perf_counter()
    try:
        job = db.get(ProcessingJob, job_id)
        if not job or job.status == "ready": return True
        document = db.get(Document, job.document_id)
        if not document: return True
        job.status = document.status = "processing"; job.attempts += 1; db.commit()
        data = storage.get(document_object_key(document.user_id, document.id, document.filename))
        chunks = processor.chunk(processor.extract_text(document.filename, data)); vectors = embeddings.embed_many(chunks)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.add_all([DocumentChunk(document_id=document.id, user_id=document.user_id, chunk_index=i, text=text, embedding_json=json.dumps(vector)) for i, (text, vector) in enumerate(zip(chunks, vectors))])
        job.status = document.status = "ready"; job.completed_at = datetime.now(timezone.utc); db.commit()
        metrics.increment("documents_processed"); metrics.observe_ms("document_processing_duration", (time.perf_counter() - started) * 1000)
        logger.info("document_processing_completed", extra={"job_id": job_id, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        return True
    except Exception as exc:
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        if job:
            job.status = "failed"; job.error_message = str(exc)[:500]
            document = db.get(Document, job.document_id)
            if document: document.status = "failed"; document.error_message = job.error_message
            db.commit()
        metrics.increment("document_processing_failures"); metrics.observe_ms("document_processing_duration", (time.perf_counter() - started) * 1000)
        logger.exception("document_processing_failed", extra={"job_id": job_id, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        return False
    finally: db.close()
