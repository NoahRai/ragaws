import os

# Unit and API tests must not fetch a Hugging Face model.
os.environ.setdefault("CLOUDMIND_EMBEDDING_PROVIDER", "hashing")
