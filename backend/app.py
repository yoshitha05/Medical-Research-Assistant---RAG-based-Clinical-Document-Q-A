import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from services import db, rag

rag.configure_gemini()

app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

ALLOWED_DOC_TYPES = {"discharge_summary", "clinical_note", "research_paper"}


@app.post("/api/upload")
def upload_document():
    """Accepts a real .txt or .pdf file (multipart), chunks it, embeds each
    chunk, stores the vectors in FAISS and the text + metadata in MongoDB."""
    doc_type = request.form.get("doc_type", "clinical_note")
    if doc_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": f"doc_type must be one of {sorted(ALLOWED_DOC_TYPES)}"}), 400

    if "file" not in request.files:
        return jsonify({"error": "a file is required"}), 400
    file = request.files["file"]
    filename = request.form.get("filename") or file.filename
    raw_bytes = file.read()

    lower_name = (file.filename or "").lower()
    if lower_name.endswith(".pdf"):
        raw_text = rag.extract_text_from_pdf(raw_bytes)
    elif lower_name.endswith(".txt"):
        raw_text = raw_bytes.decode("utf-8", errors="ignore")
    else:
        return jsonify({"error": "only .txt and .pdf files are supported"}), 400

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

@app.delete("/api/documents/<document_id>")
def delete_document(document_id):
    """Deletes a document's MongoDB records and its FAISS vectors."""
    vector_ids = db.delete_document(document_id)
    if vector_ids:
        rag.remove_vectors(vector_ids)
    return jsonify({"deleted": document_id}), 200


@app.post("/api/ask")
def ask_question():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question")
    document_id = payload.get("document_id")
    top_k = int(payload.get("top_k", 5))

    if not question:
        return jsonify({"error": "question is required"}), 400

    query_vector = rag.embed_texts([question], task_type="retrieval_query")[0]

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


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def serve_react(path):
    static_dir = app.static_folder
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)