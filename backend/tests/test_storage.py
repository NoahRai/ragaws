from app.services.documents import S3StorageService, document_object_key


class FakeS3:
    def __init__(self): self.calls = []
    def put_object(self, **kwargs): self.calls.append(("put", kwargs))
    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"Body": type("Body", (), {"read": lambda self: b"hello"})()}
    def delete_object(self, **kwargs): self.calls.append(("delete", kwargs))
    def generate_presigned_url(self, *args, **kwargs): return "https://signed.example/file"


def test_s3_service_keeps_documents_private_and_supports_presigning():
    client = FakeS3(); storage = S3StorageService("private-bucket", "us-east-1", client=client)
    key = document_object_key("user-1", "doc-1", "notes.TXT")
    storage.put(key, b"hello", "text/plain")
    assert key == "documents/user-1/doc-1/original.txt"
    assert client.calls[0][1]["ServerSideEncryption"] == "AES256"
    assert storage.get(key) == b"hello"
    assert storage.download_url(key, 300) == "https://signed.example/file"
    storage.delete(key)
