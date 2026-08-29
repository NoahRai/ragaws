import json
from app.services.jobs import SQSJobQueue


class FakeSQS:
    def __init__(self): self.sent = []; self.deleted = []
    def send_message(self, **kwargs): self.sent.append(kwargs)
    def receive_message(self, **kwargs): return {"Messages": [{"Body": '{"job_id":"job-1"}', "ReceiptHandle": "receipt"}]}
    def delete_message(self, **kwargs): self.deleted.append(kwargs)


def test_sqs_queue_serializes_and_acknowledges_job_messages():
    client = FakeSQS(); queue = SQSJobQueue("https://queue.example", "us-east-1", client=client)
    queue.enqueue("job-1")
    assert json.loads(client.sent[0]["MessageBody"]) == {"job_id": "job-1"}
    assert queue.receive(20)[0]["Body"] == '{"job_id":"job-1"}'
    queue.acknowledge("receipt")
    assert client.deleted[0]["ReceiptHandle"] == "receipt"
