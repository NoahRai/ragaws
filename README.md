# CloudMind

CloudMind is a private AI document intelligence platform: users upload TXT/PDF files, CloudMind processes them, retrieves relevant passages with vector similarity, and returns grounded answers with sources.

> **Status:** Phases 1–5 complete: CloudMind has a parameterized AWS deployment topology for independently scalable API and worker services. It is ready to be reviewed and applied in an AWS account; infrastructure has not been applied from this repository.

## Architecture

```mermaid
flowchart LR
  U[User] --> R[React / Vite]
  R --> A[FastAPI API]
  A --> D[(PostgreSQL + pgvector)]
  A --> S[S3 private documents]
  A --> Q[SQS processing queue]
  Q --> W[Worker: parse, chunk, PyTorch embeddings]
  W --> D
  A --> L[LLM]
  A --> C[CloudWatch]
```

The local implementation uses SQLite and local in-memory storage. Set `CLOUDMIND_STORAGE_BACKEND=s3` and `CLOUDMIND_S3_BUCKET` to use `S3StorageService`; it stores private, encrypted objects as `documents/{user_id}/{document_id}/original.{extension}` and creates short-lived presigned download URLs only after ownership validation. Set `CLOUDMIND_QUEUE_BACKEND=sqs` and `CLOUDMIND_SQS_QUEUE_URL` to dispatch an idempotent `processing_jobs` record to `backend/worker.py`. `DocumentProcessor`, `StorageService`, `EmbeddingService`, `RetrievalService`, and `LLMService` isolate provider-specific work.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# Separate terminal
cd frontend && npm install && npm run dev
```

Open the UI at `http://localhost:5173`; API documentation is at `http://localhost:8000/docs`.

Or run `docker compose up --build`.

## Verification

```bash
PYTHONPATH=backend pytest backend/tests
```

## Data flow and security

1. Authenticated user uploads a validated PDF/TXT document.
2. A document record is created; it is parsed, chunked, embedded under `torch.inference_mode()`, and marked `ready` (synchronously for the local MVP).
3. Every list, retrieval, search, and delete query filters by the JWT subject, preventing cross-user access.
4. Search embeds the question, scores only that user's ready chunks, and returns document/chunk citations.

Passwords are Argon2-hashed, SQLAlchemy binds query values, secrets live in environment variables, and file size/type are validated. Copy `.env.example` to `.env` and replace the JWT secret before deployment.

## Production roadmap

- **Database:** migrate SQLite to PostgreSQL with Alembic; store embeddings in `vector`, add HNSW indexes, and use an ownership-scoped join for retrieval.
- **Production engineering:** add migrations, CI image publishing/deployment, structured correlation IDs, latency metrics, and alarms.
- **RAG quality:** use a sentence-transformer, pgvector cosine search, a provider-backed LLM with a strict context-only prompt, and optional reranking/hybrid BM25.

## Project layout

```
frontend/       React + TypeScript Vite interface
backend/app/    FastAPI, models, services, authentication
backend/tests/  API workflow test
infrastructure/ Terraform cloud starter
.github/        CI pipeline
```

## AWS deployment (Phase 5)

Terraform provisions private S3/SQS resources, ECR repositories, an RDS PostgreSQL instance, CloudWatch log groups, an ALB, and separate Fargate API/worker services. It deliberately accepts an existing VPC and public/private subnets so networking stays under account control.

1. Create two Secrets Manager secrets: the full `postgresql+psycopg://...` URL and a 32-byte+ JWT secret.
2. Build and push the API and worker images to the Terraform-created ECR repositories.
3. Copy `infrastructure/terraform.tfvars.example` to `terraform.tfvars`, fill in your account resources, and supply `TF_VAR_db_password` from a secure shell/CI secret.
4. Run `terraform init`, `terraform plan`, and then review `terraform apply` in `infrastructure/`.

The RDS database is private and deletion-protected; the task roles are scoped separately so the API can send queue messages while the worker can receive them. No AWS keys are present in this repository.
