import os

from dotenv import load_dotenv

load_dotenv()  # loads .env for local dev; on Render, env vars come from the dashboard instead

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from services import db, rag

rag.configure_gemini()

app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

ALLOWED_DOC_TYPES = {"discharge_summary", "clinical_note", "research_paper"}


@app.post("/api/upload")
def upload_document():
    """Accepts a plain-text clinical document, chunks it, embeds each chunk,
    stores the vectors in FAISS and the text + metadata in MongoDB."""
    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename")
    doc_type = payload.get("doc_type", "clinical_note")
    raw_text = payload.get("text")

    if not filename or not raw_text:
        return jsonify({"error": "filename and text are required"}), 400
    if doc_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": f"doc_type must be one of {sorted(ALLOWED_DOC_TYPES)}"}), 400

    document_id = db.create_document(filename, doc_type, raw_text)

    chunks = rag.chunk_text(raw_text)
    if not chunks:
        return jsonify({"error": "no extractable text found in document"}), 400

    vectors = rag.embed_texts(chunks, task_type="retrieval_document")
    vector_ids = rag.next_vector_id(len(chunks))
    rag.add_vectors(vectors, vector_ids)

    for idx, (chunk, vec_id) in enumerate(zip(chunks, vector_ids)):
        db.create_chunk(document_id, idx, chunk, vec_id)

    return jsonify({
        "document_id": document_id,
        "filename": filename,
        "doc_type": doc_type,
        "chunks_stored": len(chunks),
    }), 201


@app.get("/api/documents")
def list_documents():
    return jsonify(db.list_documents())


@app.get("/api/documents/<document_id>")
def get_document(document_id):
    doc = db.get_document(document_id)
    if not doc:
        return jsonify({"error": "not found"}), 404
    doc["_id"] = str(doc["_id"])
    return jsonify(doc)


@app.post("/api/ask")
def ask_question():
    """Embeds the question, finds the nearest chunks via FAISS, looks their
    text up in MongoDB, and asks Gemini to answer grounded in that text."""
    payload = request.get_json(silent=True) or {}
    question = payload.get("question")
    document_id = payload.get("document_id")  # optional: restrict to one document
    top_k = int(payload.get("top_k", 5))

    if not question:
        return jsonify({"error": "question is required"}), 400

    query_vector = rag.embed_texts([question], task_type="retrieval_query")[0]

    # Over-fetch, then filter down to the requested document if one was given.
    fetch_k = top_k * 4 if document_id else top_k
    candidate_ids = rag.search(query_vector, top_k=fetch_k)
    candidates = db.get_chunks_by_faiss_ids(candidate_ids)

    if document_id:
        candidates = [c for c in candidates if c["document_id"] == document_id]
    candidates = candidates[:top_k]

    context_chunks = [c["chunk_text"] for c in candidates]
    answer = rag.generate_answer(question, context_chunks)

    db.log_query(document_id, question, answer, [c["_id"] for c in candidates])

    return jsonify({
        "question": question,
        "answer": answer,
        "sources": [
            {"chunk_id": c["_id"], "document_id": c["document_id"], "text": c["chunk_text"]}
            for c in candidates
        ],
    })


@app.get("/api/documents/<document_id>/history")
def document_history(document_id):
    return jsonify(db.list_queries(document_id=document_id))


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


# --- Serve the built React app for everything else ---
@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def serve_react(path):
    static_dir = app.static_folder
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
