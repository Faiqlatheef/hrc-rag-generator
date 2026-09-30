# RAG Generator — Agentic Coding Assessment

A runtime-configurable Retrieval-Augmented Generation application for the HRC Labs Senior AI Engineer assessment.

## What it demonstrates

- Runtime upload of PDF, DOCX, TXT and Markdown documents.
- No code changes required when the document set changes.
- Text extraction and overlapping chunks.
- Sentence-Transformer embeddings with persistent FAISS vector search.
- Grounded LLM responses using retrieved context only.
- Source metadata and similarity scores for traceability.
- Explicit fallback when no LLM key is configured instead of fabricating an answer.
- FastAPI REST API plus Streamlit demonstration UI.
- A reset/replace flow for demonstrating completely different document sets.
- Docker support and automated tests.

## Architecture

```text
User
  |
  v
Streamlit UI / REST API
  |
  +--> Runtime document upload
  |       |
  |       +--> PDF/DOCX/TXT/MD parser
  |       +--> normalization + chunking
  |       +--> SentenceTransformer embeddings
  |       +--> FAISS IndexFlatIP
  |       +--> JSON metadata sidecar
  |
  +--> Question
          |
          +--> query embedding
          +--> top-k similarity retrieval
          +--> grounded prompt
          +--> LLM
          +--> answer + source metadata
```

FAISS uses inner-product search over normalized embeddings, which is equivalent to cosine similarity for unit-normalized vectors.

## Why this design

The assessment requires the application to work with different document sets without code changes. The ingestion path is therefore data-driven: uploaded files are parsed, chunked and indexed at runtime. The UI can replace the current knowledge base with a new document set without changing application code.

The LLM is deliberately not given unrestricted access to external knowledge. The generation prompt instructs it to answer only from retrieved context and to explicitly report when the evidence is insufficient.

FAISS is used as a lightweight local vector index, avoiding a separate vector database service for this time-boxed assessment. The index and metadata are persisted under `data/faiss`.

## Local setup — Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env` from `.env.example` and add your OpenAI API key if you want LLM-generated answers.

Then start the API:

```powershell
uvicorn app.api:app --reload
```

In a second terminal, activate the same environment and start the UI:

```powershell
streamlit run app/ui.py
```

Open the Streamlit URL shown in the terminal.

## Verify the installation

```powershell
python -c "import faiss; print('FAISS:', faiss.__version__)"
pytest -q
```

FAISS publishes Windows wheels for CPython 3.13 and current releases, so the project can run on the user's Windows/Python 3.13 environment without compiling `chroma-hnswlib`.

## Environment variables

```env
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=all-MiniLM-L6-v2
UPLOAD_DIR=./data/uploads
FAISS_DIR=./data/faiss
COLLECTION_NAME=rag_generator
```

## Assessment demonstration

Use this exact demo flow:

1. Upload document set A.
2. Select **Replace the current knowledge base**.
3. Index the documents.
4. Ask a question whose answer exists in set A.
5. Show the answer and source metadata.
6. Upload document set B with the same code and replace the knowledge base.
7. Ask a question that only set B can answer.
8. Ask a question absent from set B and show the grounded fallback.
9. Show `/docs` in FastAPI and `/health` for operational visibility.

This demonstrates runtime adaptability, retrieval, grounding, citations, and basic operational behavior.

## API

### Health

`GET /health`

### Upload

`POST /documents`

Multipart form-data with one or more `files` fields.

Query parameter:

```text
replace_existing=true
```

Use this to replace the current knowledge base.

### Clear

`DELETE /documents`

### Query

```json
POST /query
{
  "question": "What are the main objectives?",
  "top_k": 5
}
```

Example response:

```json
{
  "answer": "... [Source 1] ...",
  "citations": [
    {
      "source": "policy.pdf",
      "chunk_index": 3,
      "document_id": "policy",
      "page": 4,
      "similarity": 0.8123
    }
  ]
}
```

## Testing

```powershell
pytest -q
```

Recommended manual tests:

- PDF ingestion and page citations.
- DOCX/TXT/Markdown ingestion.
- Replacement of document set A with document set B.
- Unsupported file extension returns HTTP 400.
- Empty question returns HTTP 400.
- Question outside the corpus returns the grounded fallback.
- Application works without an OpenAI key using the safe retrieval-only fallback.

## Production next steps

- Add OCR for scanned PDFs.
- Add hybrid BM25 + vector retrieval and reranking for larger corpora.
- Add authentication, rate limiting and upload malware scanning.
- Add tenant-aware document isolation.
- Add a golden evaluation dataset with retrieval and answer metrics.
- Add tracing, latency, token and cost monitoring.
- Move uploaded files to object storage and the vector index to a managed service for multi-instance deployment.

## Assessment submission note

The candidate brief requires the complete AI-agent development transcript. `transcripts/AGENT_TRANSCRIPT_TEMPLATE.md` is only a template. Replace it with the actual exported transcript from the coding agent used during development/refinement; do not submit a fabricated transcript.
