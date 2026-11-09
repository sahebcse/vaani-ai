#!/usr/bin/env python3
"""Ingest fixtures/policies/*.md into OpenSearch (hybrid lexical + kNN).

Run after `docker compose up` with OPENSEARCH_URL set. Idempotent.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearchpy import OpenSearch  # noqa: E402

from vaani.retrieval import (  # noqa: E402
    EMBEDDING_DIM,
    HashEmbedder,
    OpenSearchStore,
    chunk_markdown,
)


def main() -> int:
    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    client = OpenSearch(hosts=[url])
    store = OpenSearchStore(client, "vaani-policies", dim=EMBEDDING_DIM)
    store.ensure_index()
    embedder = HashEmbedder()
    total = 0
    for path in sorted(glob.glob("fixtures/policies/*.md")):
        if os.path.basename(path) == "README.md":
            continue
        with open(path, encoding="utf-8") as fh:
            docs = chunk_markdown(fh.read(), os.path.basename(path))
        vectors = embedder.embed([d.text for d in docs])
        store.index(docs, vectors)
        total += len(docs)
        print(f"indexed {len(docs)} chunks from {path}")
    print(f"done: {total} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
