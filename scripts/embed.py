"""
Embed the row chunks with OpenAI text-embedding-3-small (1536 dims).

Input : chunks/character/chunks_character.json
Output: embeddings/character/embeddings_character.json       (what lang.py loads)
        embeddings/character/embeddings_character.meta.json  (same, minus vectors)

Batches 100 chunks per request, retries 429/5xx with backoff, and resumes:
chunks already present in the output file (by chunk_id) are not re-embedded.
Delete the output file to force a full re-embed after re-chunking.

Requires OPENAI_API_KEY in the environment or in .env at the repo root.
Run: python3 scripts/embed.py      (116 chunks ~ a fraction of a cent)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

INPUT_FILE  = ROOT / "chunks" / "character" / "chunks_character.json"
OUTPUT_DIR  = ROOT / "embeddings" / "character"
OUTPUT_FILE = OUTPUT_DIR / "embeddings_character.json"
META_FILE   = OUTPUT_DIR / "embeddings_character.meta.json"

MODEL          = "text-embedding-3-small"
BATCH_SIZE     = 100
RETRY_LIMIT    = 3
RETRY_DELAY_S  = 2.0
URL            = "https://api.openai.com/v1/embeddings"


def embed_batch(texts, api_key, attempt=1):
    res = requests.post(URL, headers={"Content-Type": "application/json",
                                      "Authorization": f"Bearer {api_key}"},
                        json={"model": MODEL, "input": texts, "encoding_format": "float"},
                        timeout=60)
    if res.status_code != 200:
        if (res.status_code == 429 or res.status_code >= 500) and attempt <= RETRY_LIMIT:
            delay = RETRY_DELAY_S * attempt
            print(f"  HTTP {res.status_code} - retrying in {delay:.0f}s (attempt {attempt}/{RETRY_LIMIT})")
            time.sleep(delay)
            return embed_batch(texts, api_key, attempt + 1)
        raise RuntimeError(f"OpenAI API error {res.status_code}: {res.text}")
    data = sorted(res.json()["data"], key=lambda d: d["index"])   # keep input order
    return [d["embedding"] for d in data]


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set (copy .env.example to .env and fill it in)")
    if not INPUT_FILE.exists():
        sys.exit(f"Input not found: {INPUT_FILE.relative_to(ROOT)} - run scripts/chunk.py first")

    chunks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(chunks)} chunks")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    existing = {}
    if OUTPUT_FILE.exists():
        for e in json.loads(OUTPUT_FILE.read_text(encoding="utf-8")):
            existing[e["chunk_id"]] = e
        print(f"Resuming - {len(existing)} chunks already embedded")

    current_ids = {c["chunk_id"] for c in chunks}
    stale = [cid for cid in existing if cid not in current_ids]
    for cid in stale:                       # chunks that no longer exist
        del existing[cid]

    todo = [c for c in chunks if c["chunk_id"] not in existing]
    print(f"Chunks to embed: {len(todo)}")

    for b in range(0, len(todo), BATCH_SIZE):
        batch = todo[b:b + BATCH_SIZE]
        print(f"Batch {b // BATCH_SIZE + 1} ({len(batch)} chunks)... ", end="", flush=True)
        vectors = embed_batch([c["text"] for c in batch], api_key)
        for c, v in zip(batch, vectors):
            existing[c["chunk_id"]] = {
                "chunk_id":        c["chunk_id"],
                "chunk_index":     c["chunk_index"],
                "source_file":     c["source_file"],
                "statement_month": c["statement_month"],
                "page_number":     c["page_number"],
                "section_type":    c["section_type"],
                "text":            c["text"],
                "model":           MODEL,
                "embedding":       v,
            }
        print("done")
        if b + BATCH_SIZE < len(todo):
            time.sleep(0.2)

    results = sorted(existing.values(), key=lambda e: e["chunk_index"])
    OUTPUT_FILE.write_text(json.dumps(results), encoding="utf-8")
    meta = [{**{k: v for k, v in e.items() if k != "embedding"},
             "embedding_dims": len(e["embedding"])} for e in results]
    META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    dims = len(results[0]["embedding"]) if results else 0
    print(f"\nEmbeddings saved : {OUTPUT_FILE.relative_to(ROOT)}")
    print(f"Meta saved       : {META_FILE.relative_to(ROOT)}")
    print(f"Model {MODEL}, {dims} dims, {len(results)} chunks")


if __name__ == "__main__":
    main()
