"""The RAG pipeline: chunk -> embed -> FAISS index -> retrieve -> Gemini generate.

FAISS only ever stores vectors and hands back vector ids (integers).
Mongo (see db.py) is what turns a vector id back into readable chunk text.
"""
import os
import threading

import faiss
import google.generativeai as genai
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

EMBED_MODEL = "models/text-embedding-004"
EMBED_DIM = 768
GEN_MODEL = "gemini-1.5-flash"

_lock = threading.Lock()
_index = None
_index_path = None


def configure_gemini():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def _index_files():
    base = os.environ.get("FAISS_INDEX_DIR", "./faiss_index")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "index.faiss")


def get_index():
    """Load the FAISS index from disk once, or create a fresh empty one."""
    global _index, _index_path
    if _index is None:
        _index_path = _index_files()
        if os.path.exists(_index_path):
            _index = faiss.read_index(_index_path)
        else:
            # IndexIDMap lets us assign our own integer ids to vectors,
            # so a vector id can be stored directly on the Mongo chunk document.
            _index = faiss.IndexIDMap(faiss.IndexFlatL2(EMBED_DIM))
    return _index


def _save_index():
    faiss.write_index(_index, _index_path)


def chunk_text(raw_text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [c.strip() for c in splitter.split_text(raw_text) if c.strip()]


def embed_texts(texts: list[str], task_type: str) -> np.ndarray:
    """task_type is 'retrieval_document' for chunks being stored,
    or 'retrieval_query' for a question being asked -- Gemini's embedding
    model optimizes the vector differently depending on which side it's for."""
    vectors = []
    for t in texts:
        result = genai.embed_content(model=EMBED_MODEL, content=t, task_type=task_type)
        vectors.append(result["embedding"])
    return np.array(vectors, dtype="float32")


def add_vectors(vectors: np.ndarray, ids: list[int]):
    with _lock:
        index = get_index()
        index.add_with_ids(vectors, np.array(ids, dtype="int64"))
        _save_index()


def next_vector_id(count: int) -> list[int]:
    """FAISS doesn't hand out ids for us with IndexIDMap, so we track the
    next free id ourselves based on how many vectors are already stored."""
    index = get_index()
    start = int(index.ntotal)
    return list(range(start, start + count))


def search(query_vector: np.ndarray, top_k: int = 5) -> list[int]:
    index = get_index()
    if index.ntotal == 0:
        return []
    distances, ids = index.search(query_vector.reshape(1, -1), min(top_k, index.ntotal))
    return [int(i) for i in ids[0] if i != -1]


def generate_answer(question: str, context_chunks: list[str]) -> str:
    if not context_chunks:
        return ("I couldn't find anything relevant to that question in the uploaded "
                "document, so I don't have a grounded answer to give.")

    context = "\n\n---\n\n".join(context_chunks)
    prompt = (
        "You are a clinical document assistant. Answer the question using ONLY the "
        "context passages below. If the answer is not contained in the context, say "
        "so plainly instead of guessing.\n\n"
        f"Context passages:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )
    model = genai.GenerativeModel(GEN_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()
