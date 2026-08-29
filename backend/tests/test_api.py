import os
os.environ["CLOUDMIND_DATABASE_URL"] = "sqlite:///./test_cloudmind.db"
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
client = TestClient(app)
def auth(email="user@example.com"):
    response = client.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def test_upload_search_and_isolation():
    first = auth(); second = auth("other@example.com")
    uploaded = client.post("/documents/upload", headers=first, files={"file": ("notes.txt", b"L1 regularization adds absolute values. L2 uses squared weights.", "text/plain")})
    assert uploaded.status_code == 202
    assert client.get("/documents", headers=second).json() == []
    result = client.post("/search", headers=first, json={"query": "What is L1?"})
    assert result.status_code == 200 and result.json()["sources"][0]["document_name"] == "notes.txt"
