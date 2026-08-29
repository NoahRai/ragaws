"""SQS worker entrypoint. Run separately from the FastAPI API container."""
import json
import logging
from app.config import settings
from app.processing import process_job
from app.services.documents import DocumentProcessor, build_storage
from app.services.jobs import SQSJobQueue
from app.services.retrieval import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(message)s")
queue = SQSJobQueue(settings.sqs_queue_url or "", settings.aws_region)
storage = build_storage(settings.storage_backend, settings.s3_bucket, settings.aws_region)
processor, embeddings = DocumentProcessor(), EmbeddingService()

def main():
    while True:
        for message in queue.receive(settings.worker_wait_seconds):
            job_id = json.loads(message["Body"])["job_id"]
            if process_job(job_id, storage, processor, embeddings): queue.acknowledge(message["ReceiptHandle"])

if __name__ == "__main__": main()
