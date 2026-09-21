# Clinical Q&A Assistant

RAG-based clinical document Q&A. Flask + ReactJS interface, FAISS for vector
search, MongoDB for document/chunk/query storage, Gemini for embeddings and
generation.

## 1. Get a Gemini API key (5 min)

1. Go to https://aistudio.google.com/app/apikey
2. Sign in with your Google account.
3. Click **Create API key** -> choose or create a Google Cloud project when prompted.
4. Copy the key. You'll paste it into Render as `GEMINI_API_KEY`.

## 2. Create a MongoDB Atlas cluster (10 min)

1. Go to https://www.mongodb.com/cloud/atlas/register and sign up (free).
2. Click **Build a Database** -> choose the **M0 Free** tier -> pick any cloud/region -> **Create**.
3. Under **Security -> Database Access**, add a database user with a username/password.
4. Under **Security -> Network Access**, click **Add IP Address** -> **Allow Access From Anywhere**
   (`0.0.0.0/0`) — needed since Render's servers don't have a fixed IP on the free tier.
5. Go to **Database -> Connect -> Drivers**, copy the connection string. It looks like:
   `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
6. Add a database name before the `?`, e.g. `.../clinical_qa?retryWrites=true...` —
   this becomes `MONGODB_URI`.

## 3. Push this project to GitHub

```bash
cd clinical-qa-app
git init
git add .
git commit -m "Initial commit"
gh repo create clinical-qa-assistant --public --source=. --push
# (or create a repo on github.com and `git remote add origin <url> && git push -u origin main`)
```

## 4. Deploy on Render (15-20 min)

1. Go to https://dashboard.render.com -> **New** -> **Blueprint**.
2. Connect your GitHub account and pick this repo. Render will read `render.yaml`
   automatically and propose the `clinical-qa-assistant` web service.
3. Before the first deploy, set the two secret environment variables it asks for:
   - `MONGODB_URI` -> the connection string from step 2
   - `GEMINI_API_KEY` -> the key from step 1
4. Click **Apply** / **Create Web Service**. The build installs Python deps,
   builds the React app, and copies it into `backend/static` so Flask serves
   everything from one URL.
5. Once it's live, Render gives you a URL like
   `https://clinical-qa-assistant.onrender.com` — that's your deployed app.

**Note:** Render's free tier spins the service down after ~15 minutes of
inactivity. The first request after that takes 30-50 seconds to wake back up —
normal, not a bug. If you're demoing it live, open the link a minute before
you need it.

## Local development (optional, before deploying)

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # then fill in MONGODB_URI and GEMINI_API_KEY
python app.py          # runs on http://localhost:5000
```

Frontend (in a second terminal):
```bash
cd frontend
npm install
REACT_APP_API_BASE=http://localhost:5000 npm start   # runs on http://localhost:3000
```

## API reference

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/upload` | `{filename, doc_type, text}` -> chunks, embeds, indexes the document |
| GET | `/api/documents` | list uploaded documents |
| GET | `/api/documents/<id>` | one document's metadata + raw text |
| POST | `/api/ask` | `{question, document_id?}` -> grounded answer + source chunks |
| GET | `/api/documents/<id>/history` | past questions asked against that document |

`doc_type` must be one of: `discharge_summary`, `clinical_note`, `research_paper`.

## Architecture

```
Browser (React) -> Flask API -> FAISS (nearest chunk vectors)
                              -> MongoDB (chunk text, by vector id)
                              -> Gemini (question + chunks -> grounded answer)
```

FAISS never stores text — only vectors and integer ids. MongoDB stores the
actual chunk text and metadata, keyed by that same id, so a FAISS match can be
turned back into readable content before it's handed to Gemini.
