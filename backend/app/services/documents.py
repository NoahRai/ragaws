import re
from abc import ABC, abstractmethod


class DocumentProcessor:
    """Extracts and chunks supported local-MVP document formats."""
    def extract_text(self, filename: str, content: bytes) -> str:
        if filename.lower().endswith(".txt"):
            return content.decode("utf-8", errors="replace")
        if filename.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                from io import BytesIO
                return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
            except ImportError as exc:
                raise ValueError("PDF support requires pypdf. Install the optional dependency.") from exc
        raise ValueError("Only PDF and TXT files are supported")

    def chunk(self, text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if not clean:
            raise ValueError("The document did not contain extractable text")
        return [clean[start:start + chunk_size] for start in range(0, len(clean), chunk_size - overlap)]


class StorageService(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def download_url(self, key: str, expires_in: int) -> str: ...


class LocalStorageService(StorageService):
    """Deliberately simple storage substitute; replace with S3StorageService in AWS."""
    def __init__(self): self._files: dict[str, bytes] = {}
    def put(self, key: str, data: bytes, content_type: str) -> None: self._files[key] = data
    def get(self, key: str) -> bytes: return self._files[key]
    def delete(self, key: str) -> None: self._files.pop(key, None)
    def download_url(self, key: str, expires_in: int) -> str:
        raise NotImplementedError("Local storage does not create download URLs")


class S3StorageService(StorageService):
    """Private S3 implementation; credentials are supplied by the AWS runtime."""
    def __init__(self, bucket: str, region: str, client=None):
        if not bucket:
            raise ValueError("CLOUDMIND_S3_BUCKET is required when storage_backend is s3")
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=region)
        self.bucket, self.client = bucket, client

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def download_url(self, key: str, expires_in: int) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in)


def document_object_key(user_id: str, document_id: str, filename: str) -> str:
    """A stable, private object layout. IDs prevent filename path traversal/collision."""
    suffix = filename.rsplit(".", 1)[-1].lower()
    return f"documents/{user_id}/{document_id}/original.{suffix}"
