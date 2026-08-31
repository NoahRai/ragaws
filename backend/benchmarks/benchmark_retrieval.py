"""Small, repeatable local benchmark for the embedding + cosine-scoring path.

Run: PYTHONPATH=backend python backend/benchmarks/benchmark_retrieval.py
"""
import statistics
import time
import torch
from app.services.retrieval import EmbeddingService

CHUNK_COUNT = 500
QUERY_COUNT = 25


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[int((len(values) - 1) * fraction)]


def main() -> None:
    service = EmbeddingService()
    chunks = [f"CloudMind document {index} covers retrieval augmented generation, embeddings, and vector search." for index in range(CHUNK_COUNT)]
    started = time.perf_counter()
    chunk_vectors = torch.tensor(service.embed_many(chunks))
    indexing_ms = (time.perf_counter() - started) * 1000
    latencies = []
    for index in range(QUERY_COUNT):
        started = time.perf_counter()
        query_vector = torch.tensor(service.embed(f"How does vector search work in document {index}?"))
        torch.topk(chunk_vectors @ query_vector, k=5)
        latencies.append((time.perf_counter() - started) * 1000)
    print(f"device={service.device.type} chunks={CHUNK_COUNT} dimensions={service.dimensions}")
    print(f"indexing_ms={indexing_ms:.2f} query_p50_ms={statistics.median(latencies):.2f} query_p95_ms={percentile(latencies, .95):.2f}")


if __name__ == "__main__":
    main()
