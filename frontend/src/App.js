import React, { useEffect, useState } from "react";
import "./App.css";

const API_BASE = process.env.REACT_APP_API_BASE || "";

export default function App() {
  const [activeTab, setActiveTab] = useState("ask"); // "ask" | "documents"

  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");

  const [uploadPanelOpen, setUploadPanelOpen] = useState(false);
  const [docType, setDocType] = useState("discharge_summary");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState(null);

  const loadDocuments = async () => {
    const res = await fetch(`${API_BASE}/api/documents`);
    setDocuments(await res.json());
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setUploadMsg("Choose a file first.");
      return;
    }
    setUploading(true);
    setUploadMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("doc_type", docType);

      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      setUploadMsg(`Stored "${data.filename}" as ${data.chunks_stored} chunks.`);
      setFile(null);
      setUploadPanelOpen(false);
      await loadDocuments();
    } catch (err) {
      setUploadMsg(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleAsk = async (e) => {
    e.preventDefault();
    setAsking(true);
    setAnswer(null);
    try {
      const res = await fetch(`${API_BASE}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          document_id: selectedDocId || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Question failed");
      setAnswer(data);
    } catch (err) {
      setAnswer({ answer: `Error: ${err.message}`, sources: [] });
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="page">
      <h1>Clinical Q&amp;A Assistant</h1>
      <p className="subtitle">Upload a clinical document, then ask it a question in plain language.</p>

      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "ask" ? "active" : ""}`}
          onClick={() => setActiveTab("ask")}
        >
          Upload &amp; Ask
        </button>
        <button
          className={`tab-btn ${activeTab === "documents" ? "active" : ""}`}
          onClick={() => setActiveTab("documents")}
        >
          Documents ({documents.length})
        </button>
      </div>

      {activeTab === "ask" && (
        <>
          <section className="card">
            <div className="upload-header">
              <h2>1. Upload a document</h2>
              <button className="plus-btn" onClick={() => setUploadPanelOpen((v) => !v)}>
                +
              </button>
            </div>

            {uploadPanelOpen && (
              <form onSubmit={handleUpload} className="upload-panel">
                <label>
                  Document type
                  <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                    <option value="discharge_summary">Discharge summary</option>
                    <option value="clinical_note">Clinical / progress note</option>
                    <option value="research_paper">Research paper</option>
                  </select>
                </label>
                <label>
                  File (.txt or .pdf)
                  <input
                    type="file"
                    accept=".txt,.pdf"
                    onChange={(e) => setFile(e.target.files[0])}
                  />
                </label>
                <button type="submit" disabled={uploading}>
                  {uploading ? "Uploading..." : "Upload & Index"}
                </button>
              </form>
            )}
            {uploadMsg && <p className="msg">{uploadMsg}</p>}
          </section>

          <section className="card">
            <h2>2. Ask a question</h2>
            <form onSubmit={handleAsk}>
              <label>
                Restrict to document (optional)
                <select value={selectedDocId} onChange={(e) => setSelectedDocId(e.target.value)}>
                  <option value="">All documents</option>
                  {documents.map((d) => (
                    <option key={d._id} value={d._id}>
                      {d.filename} ({d.doc_type})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Question
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. What antibiotic was the patient started on?"
                  required
                />
              </label>
              <button type="submit" disabled={asking}>
                {asking ? "Thinking..." : "Ask"}
              </button>
            </form>

            {answer && (
              <div className="answer-box">
                <p className="answer-text">{answer.answer}</p>
                {answer.sources?.length > 0 && (
                  <div className="sources">
                    <p className="sources-label">Retrieved from:</p>
                    <ul>
                      {answer.sources.map((s) => (
                        <li key={s.chunk_id}>{s.text}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      )}

      {activeTab === "documents" && (
        <section className="card">
          <h2>Documents uploaded ({documents.length})</h2>
          <ul className="doc-list">
            {documents.map((d) => (
              <li key={d._id} className="doc-row">
                <span><strong>{d.filename}</strong> — {d.doc_type}</span>
                <button
                  className="delete-btn"
                  onClick={async () => {
                    if (!window.confirm(`Delete "${d.filename}"?`)) return;
                    await fetch(`${API_BASE}/api/documents/${d._id}`, { method: "DELETE" });
                    if (selectedDocId === d._id) setSelectedDocId("");
                    await loadDocuments();
                  }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}