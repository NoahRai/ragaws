# CloudMind demo script

Use this short script for a portfolio video or interview walkthrough.

1. Create an account and introduce CloudMind as a private RAG workspace.
2. Upload a lecture note or paper in PDF/TXT format; point out its `queued` → `processing` → `ready` lifecycle.
3. Ask a question whose answer is in the file, then call out the grounded answer, chunk source, document name, and relevance score.
4. Open `/docs` to show the typed FastAPI contract and `/metrics` to show operational counters.
5. Explain the deployment seam: API uploads to private S3, emits an SQS job, and an independent worker writes vectors to PostgreSQL/pgvector.

## Interview talking points

- **Ownership isolation:** each data access path scopes records to the JWT subject; S3 object keys include the user and document IDs.
- **Asynchronous reliability:** processing is idempotent, status is persisted, SQS visibility timeout supports retries, and failed messages route to a DLQ.
- **Production operations:** API responses carry `X-Request-ID`; JSON logs and metrics flow to CloudWatch in ECS.
- **Trade-off:** the local MVP uses a deterministic PyTorch hashing embedder to stay lightweight. The interface is designed to swap in a sentence-transformer plus pgvector without changing API behavior.
