from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .core import SUPPORTED, RAGService, VectorStore, ingest_files

load_dotenv()

app = FastAPI(title="RAG Generator", version="2.1.0")

DATA = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
DATA.mkdir(parents=True, exist_ok=True)

store = VectorStore(
    os.getenv("FAISS_DIR", "./data/faiss"),
    os.getenv("COLLECTION_NAME", "rag_generator"),
)

rag = RAGService(store)

# Internal retrieval setting.
# The user does not need to control this from the UI.
DEFAULT_TOP_K = 5


class Query(BaseModel):
    question: str = Field(min_length=1)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_configured": rag.client is not None,
        "llm_provider": "OpenRouter",
        "documents_indexed": store.document_count,
        "chunks_indexed": store.chunk_count,
    }


@app.delete("/documents")
def clear_documents():
    """Clear the current knowledge base."""
    store.clear()

    for child in DATA.iterdir():
        if child.is_file():
            child.unlink()

    return {
        "status": "cleared",
        "documents_indexed": 0,
        "chunks_indexed": 0,
    }


@app.post("/documents")
async def upload_documents(
    files: list[UploadFile] = File(...),
    replace_existing: bool = False,
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one document is required",
        )

    if replace_existing:
        store.clear()

        for child in DATA.iterdir():
            if child.is_file():
                child.unlink()

    paths = []

    for file in files:
        filename = Path(file.filename or "").name

        if not filename:
            raise HTTPException(
                status_code=400,
                detail="A file name is required",
            )

        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported type: {ext or 'unknown'}",
            )

        target = DATA / filename

        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        paths.append(str(target))

    try:
        count = ingest_files(paths, store)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Document indexing failed: {exc}",
        ) from exc

    return {
        "documents": len(paths),
        "chunks_indexed": count,
        "total_chunks": store.chunk_count,
        "files": [Path(path).name for path in paths],
        "replace_existing": replace_existing,
    }


@app.post("/query")
def query(q: Query):
    question = q.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty",
        )

    if store.chunk_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents have been indexed yet. Upload and index documents first.",
        )

    try:
        return rag.answer(
            question,
            DEFAULT_TOP_K,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Question answering failed: {exc}",
        ) from exc