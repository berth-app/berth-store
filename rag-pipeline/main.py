"""RAG Pipeline — Document ingestion and Q&A with vector search

Loads text documents, generates embeddings, stores in a local vector index,
and answers questions using retrieval-augmented generation.

Set OPENAI_API_KEY env var. Optionally set DOCS_DIR (default: ./docs).
"""

import os
import json
import glob
import numpy as np
from pathlib import Path
from openai import OpenAI

API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    print("Error: OPENAI_API_KEY environment variable not set")
    exit(1)

DOCS_DIR = os.environ.get("DOCS_DIR", "./docs")
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

client = OpenAI(api_key=API_KEY)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), size - overlap):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def load_documents(docs_dir: str) -> list[dict]:
    docs = []
    patterns = ["*.txt", "*.md", "*.py", "*.js", "*.json"]
    for pattern in patterns:
        for filepath in glob.glob(os.path.join(docs_dir, "**", pattern), recursive=True):
            try:
                text = Path(filepath).read_text(encoding="utf-8", errors="replace")
                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    docs.append({"source": filepath, "chunk_index": i, "text": chunk})
            except Exception as e:
                print(f"  Skipping {filepath}: {e}")
    return docs


def get_embeddings(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_np, b_np = np.array(a), np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


def search(query: str, index: list[dict], top_k: int = TOP_K) -> list[dict]:
    query_embedding = get_embeddings([query])[0]
    scored = []
    for item in index:
        score = cosine_similarity(query_embedding, item["embedding"])
        scored.append({**item, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def ask(question: str, index: list[dict]) -> str:
    results = search(question, index)
    context = "\n\n---\n\n".join(
        f"[Source: {r['source']}]\n{r['text']}" for r in results
    )

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Answer questions based on the provided context. "
                    "If the context doesn't contain enough information, say so."
                ),
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    return response.choices[0].message.content


def main():
    docs_dir = os.path.abspath(DOCS_DIR)
    print(f"RAG Pipeline — Loading documents from {docs_dir}")

    if not os.path.isdir(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        sample = Path(docs_dir) / "sample.txt"
        sample.write_text(
            "Berth is a Mac-native deployment control plane for AI-generated code. "
            "It lets developers deploy code to local machines, remote servers, and cloud targets. "
            "Berth includes a lightweight Rust agent for remote execution and an MCP server "
            "for AI agent control. Projects can be deployed via paste, import, or template store."
        )
        print(f"  Created sample document at {sample}")

    # Load and chunk documents
    documents = load_documents(docs_dir)
    if not documents:
        print("No documents found. Add .txt, .md, .py, .js, or .json files to the docs directory.")
        return

    print(f"  Loaded {len(documents)} chunk(s) from documents")

    # Generate embeddings
    print("  Generating embeddings...")
    texts = [doc["text"] for doc in documents]
    embeddings = get_embeddings(texts)
    index = [{**doc, "embedding": emb} for doc, emb in zip(documents, embeddings)]
    print(f"  Indexed {len(index)} chunk(s)")

    # Interactive Q&A
    print("\nRAG Pipeline ready. Enter questions (Ctrl+C to exit):\n")
    try:
        while True:
            question = input("Q: ").strip()
            if not question:
                continue
            answer = ask(question, index)
            print(f"\nA: {answer}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nDone.")


if __name__ == "__main__":
    main()
