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
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorageService(StorageService):
    """Deliberately simple storage substitute; replace with S3StorageService in AWS."""
    def __init__(self): self._files: dict[str, bytes] = {}
    def put(self, key: str, data: bytes) -> None: self._files[key] = data
    def get(self, key: str) -> bytes: return self._files[key]
    def delete(self, key: str) -> None: self._files.pop(key, None)
