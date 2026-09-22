"""MongoDB access layer.

Three collections, matching the schema design:
  - documents: metadata + raw text for each uploaded file
  - chunks:    each chunk of text, tied back to a document, tagged with its FAISS vector id
  - queries:   a log of every question asked, the answer given, and which chunks were used
"""
import os
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import MongoClient

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        uri = os.environ["MONGODB_URI"]
        _client = MongoClient(uri)
        _db = _client.get_default_database()
    return _db


def create_document(filename: str, doc_type: str, raw_text: str) -> str:
    db = get_db()
    result = db.documents.insert_one({
        "filename": filename,
        "doc_type": doc_type,
        "raw_text": raw_text,
        "upload_date": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)

def delete_document(document_id: str):
    db = get_db()
    oid = ObjectId(document_id)
    chunk_docs = list(db.chunks.find({"document_id": oid}, {"faiss_vector_id": 1}))
    vector_ids = [c["faiss_vector_id"] for c in chunk_docs]
    db.chunks.delete_many({"document_id": oid})
    db.documents.delete_one({"_id": oid})
    return vector_ids

def list_documents():
    db = get_db()
    docs = db.documents.find({}, {"raw_text": 0}).sort("upload_date", -1)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


def get_document(document_id: str):
    db = get_db()
    doc = db.documents.find_one({"_id": ObjectId(document_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def create_chunk(document_id: str, chunk_index: int, chunk_text: str, faiss_vector_id: int) -> str:
    db = get_db()
    result = db.chunks.insert_one({
        "document_id": ObjectId(document_id),
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "faiss_vector_id": faiss_vector_id,
    })
    return str(result.inserted_id)


def get_chunks_by_faiss_ids(faiss_ids: list[int]):
    """Fetch chunk text (and parent document id) for a list of FAISS vector ids,
    preserving the order FAISS returned them in (closest match first)."""
    db = get_db()
    docs = list(db.chunks.find({"faiss_vector_id": {"$in": faiss_ids}}))
    by_id = {d["faiss_vector_id"]: d for d in docs}
    ordered = [by_id[i] for i in faiss_ids if i in by_id]
    for d in ordered:
        d["_id"] = str(d["_id"])
        d["document_id"] = str(d["document_id"])
    return ordered


def log_query(document_id: str | None, question: str, answer: str, used_chunk_ids: list[str]):
    db = get_db()
    db.queries.insert_one({
        "document_id": ObjectId(document_id) if document_id else None,
        "question": question,
        "answer": answer,
        "used_chunk_ids": used_chunk_ids,
        "created_at": datetime.now(timezone.utc),
    })


def list_queries(document_id: str | None = None, limit: int = 50):
    db = get_db()
    filt = {"document_id": ObjectId(document_id)} if document_id else {}
    items = list(db.queries.find(filt).sort("created_at", -1).limit(limit))
    for i in items:
        i["_id"] = str(i["_id"])
        i["document_id"] = str(i["document_id"]) if i.get("document_id") else None
    return items
