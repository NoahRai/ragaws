import json
from abc import ABC, abstractmethod
from collections.abc import Callable


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, job_id: str) -> None: ...


class LocalJobQueue(JobQueue):
    """Local development adapter: runs jobs immediately without AWS dependencies."""
    def __init__(self, handler: Callable[[str], None]): self.handler = handler
    def enqueue(self, job_id: str) -> None: self.handler(job_id)


class SQSJobQueue(JobQueue):
    def __init__(self, queue_url: str, region: str, client=None):
        if not queue_url: raise ValueError("CLOUDMIND_SQS_QUEUE_URL is required when queue_backend is sqs")
        if client is None:
            import boto3
            client = boto3.client("sqs", region_name=region)
        self.queue_url, self.client = queue_url, client

    def enqueue(self, job_id: str) -> None:
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps({"job_id": job_id}))

    def receive(self, wait_seconds: int) -> list[dict]:
        return self.client.receive_message(QueueUrl=self.queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=wait_seconds, VisibilityTimeout=300).get("Messages", [])

    def acknowledge(self, receipt_handle: str) -> None:
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
