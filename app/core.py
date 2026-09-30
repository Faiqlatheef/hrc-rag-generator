from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from docx import Document
from pypdf import PdfReader

try:
    import faiss
except ImportError:
    faiss = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


# ============================================================
# CONFIGURATION
# ============================================================

SUPPORTED = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
}

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 150

DEFAULT_TOP_K = 5

DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Chunk:
    text: str
    source: str
    page: int | None = None
    chunk_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "chunk_index": self.chunk_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        return cls(
            text=data["text"],
            source=data["source"],
            page=data.get("page"),
            chunk_index=data.get("chunk_index", 0),
        )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(text: str) -> str:
    """
    Normalize extracted document text while preserving
    meaningful content.
    """

    if not text:
        return ""

    text = text.replace("\x00", " ")

    # Normalize Windows/macOS line endings.
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove excessive spaces.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# DOCUMENT EXTRACTION
# ============================================================

def extract_pdf(path: str | Path) -> List[Tuple[str, int | None]]:
    """
    Extract PDF text while preserving page numbers.
    """

    path = Path(path)

    reader = PdfReader(str(path))

    pages: List[Tuple[str, int | None]] = []

    for page_number, page in enumerate(reader.pages, start=1):

        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        text = clean_text(text)

        if text:
            pages.append((text, page_number))

    return pages


def extract_docx(path: str | Path) -> List[Tuple[str, int | None]]:
    """
    Extract DOCX paragraphs.

    DOCX does not provide reliable page boundaries through
    python-docx, so page is left as None.
    """

    document = Document(str(path))

    paragraphs: List[str] = []

    for paragraph in document.paragraphs:

        text = clean_text(paragraph.text)

        if text:
            paragraphs.append(text)

    text = "\n".join(paragraphs)

    if not text:
        return []

    return [(text, None)]


def extract_text_file(path: str | Path) -> List[Tuple[str, int | None]]:
    """
    Extract TXT/Markdown files.
    """

    path = Path(path)

    # UTF-8 first.
    try:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        text = path.read_text(
            encoding="latin-1",
            errors="ignore",
        )

    text = clean_text(text)

    if not text:
        return []

    return [(text, None)]


def extract_document(path: str | Path) -> List[Tuple[str, int | None]]:
    """
    Extract document content based on file type.
    """

    path = Path(path)

    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path)

    if extension == ".docx":
        return extract_docx(path)

    if extension in {".txt", ".md"}:
        return extract_text_file(path)

    raise ValueError(
        f"Unsupported document type: {extension}"
    )


# ============================================================
# CHUNKING
# ============================================================

def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into overlapping chunks.

    The splitter first attempts to preserve paragraphs and
    sentences before falling back to character-based splitting.
    """

    text = clean_text(text)

    if not text:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    if len(text) <= chunk_size:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]

    chunks: List[str] = []

    current = ""

    for paragraph in paragraphs:

        # Paragraph fits in current chunk.
        candidate = (
            f"{current}\n\n{paragraph}"
            if current
            else paragraph
        )

        if len(candidate) <= chunk_size:
            current = candidate
            continue

        # Save current chunk.
        if current:
            chunks.append(current.strip())

        # Very large paragraph.
        if len(paragraph) > chunk_size:

            start = 0

            while start < len(paragraph):

                end = min(
                    start + chunk_size,
                    len(paragraph),
                )

                piece = paragraph[start:end].strip()

                if piece:
                    chunks.append(piece)

                if end >= len(paragraph):
                    break

                start = max(
                    end - chunk_overlap,
                    start + 1,
                )

            current = ""

        else:
            current = paragraph

    if current:
        chunks.append(current.strip())

    # Add overlap between chunks where possible.
    final_chunks: List[str] = []

    for index, chunk in enumerate(chunks):

        if index == 0:
            final_chunks.append(chunk)
            continue

        previous = final_chunks[-1]

        overlap_text = previous[-chunk_overlap:].strip()

        if overlap_text:
            combined = (
                overlap_text
                + "\n\n"
                + chunk
            )

            if len(combined) <= chunk_size + chunk_overlap:
                final_chunks.append(combined)
            else:
                final_chunks.append(chunk)
        else:
            final_chunks.append(chunk)

    return final_chunks


class Chunker:
    """
    Public chunker class retained for compatibility with tests.
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> List[str]:
        return split_text(
            text,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def chunk(self, text: str) -> List[str]:
        return self.split(text)


# ============================================================
# EMBEDDINGS
# ============================================================

class EmbeddingModel:
    """
    Local SentenceTransformer embedding model.

    No embedding API calls are made.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ):
        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers is not installed."
            )

        self.model_name = model_name

        self.model = SentenceTransformer(
            model_name
        )

    def encode(
        self,
        texts: List[str],
    ) -> np.ndarray:

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return np.asarray(
            embeddings,
            dtype="float32",
        )


# ============================================================
# FAISS VECTOR STORE
# ============================================================

class VectorStore:

    def __init__(
        self,
        directory: str | Path,
        collection_name: str = "rag_generator",
    ):
        if faiss is None:
            raise RuntimeError(
                "FAISS is not installed. "
                "Install it with: pip install faiss-cpu"
            )

        self.directory = Path(directory)

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.collection_name = collection_name

        self.index_path = (
            self.directory / "index.faiss"
        )

        self.metadata_path = (
            self.directory / "metadata.json"
        )

        self.index = None

        self.chunks: List[Chunk] = []

        self._load()

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    def _load(self) -> None:

        if (
            self.index_path.exists()
            and self.metadata_path.exists()
        ):

            try:
                self.index = faiss.read_index(
                    str(self.index_path)
                )

                data = json.loads(
                    self.metadata_path.read_text(
                        encoding="utf-8"
                    )
                )

                self.chunks = [
                    Chunk.from_dict(item)
                    for item in data
                ]

            except Exception:

                self.index = None
                self.chunks = []

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    def _save(self) -> None:

        if self.index is not None:
            faiss.write_index(
                self.index,
                str(self.index_path),
            )

        self.metadata_path.write_text(
            json.dumps(
                [
                    chunk.to_dict()
                    for chunk in self.chunks
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # --------------------------------------------------------
    # CLEAR
    # --------------------------------------------------------

    def clear(self) -> None:

        self.index = None
        self.chunks = []

        if self.index_path.exists():
            self.index_path.unlink()

        if self.metadata_path.exists():
            self.metadata_path.unlink()

    # --------------------------------------------------------
    # ADD
    # --------------------------------------------------------

    def add(
        self,
        chunks: List[Chunk],
        embeddings: np.ndarray,
    ) -> None:

        if not chunks:
            return

        if len(chunks) != len(embeddings):
            raise ValueError(
                "Number of chunks and embeddings must match."
            )

        embeddings = np.asarray(
            embeddings,
            dtype="float32",
        )

        # Embeddings are normalized, so inner product equals
        # cosine similarity.
        faiss.normalize_L2(embeddings)

        dimension = embeddings.shape[1]

        if self.index is None:

            self.index = faiss.IndexFlatIP(
                dimension
            )

        elif self.index.d != dimension:

            raise ValueError(
                "Embedding dimension does not match "
                "the existing FAISS index."
            )

        self.index.add(embeddings)

        self.chunks.extend(chunks)

        self._save()

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Tuple[Chunk, float]]:

        if (
            self.index is None
            or not self.chunks
            or self.index.ntotal == 0
        ):
            return []

        top_k = max(
            1,
            min(top_k, len(self.chunks)),
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype="float32",
        )

        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(
                1,
                -1,
            )

        faiss.normalize_L2(query_embedding)

        scores, indices = self.index.search(
            query_embedding,
            top_k,
        )

        results: List[Tuple[Chunk, float]] = []

        for score, index in zip(
            scores[0],
            indices[0],
        ):

            if index < 0:
                continue

            if index >= len(self.chunks):
                continue

            results.append(
                (
                    self.chunks[index],
                    float(score),
                )
            )

        return results

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def document_count(self) -> int:
        return len(
            {
                chunk.source
                for chunk in self.chunks
            }
        )


# ============================================================
# INGESTION
# ============================================================

def make_file_id(path: str | Path) -> str:

    path = Path(path)

    try:
        content = path.read_bytes()
    except Exception:
        content = str(path).encode(
            "utf-8"
        )

    return hashlib.sha256(
        content
    ).hexdigest()


def ingest_files(
    paths: List[str],
    store: VectorStore,
) -> int:
    """
    Extract, chunk, embed and index documents.
    """

    if not paths:
        return 0

    embedder = EmbeddingModel()

    chunker = Chunker()

    all_chunks: List[Chunk] = []

    for path_string in paths:

        path = Path(path_string)

        extracted = extract_document(
            path
        )

        local_chunk_index = 0

        for text, page in extracted:

            pieces = chunker.split(text)

            for piece in pieces:

                if not piece.strip():
                    continue

                all_chunks.append(
                    Chunk(
                        text=piece,
                        source=path.name,
                        page=page,
                        chunk_index=local_chunk_index,
                    )
                )

                local_chunk_index += 1

    if not all_chunks:
        return 0

    texts = [
        chunk.text
        for chunk in all_chunks
    ]

    embeddings = embedder.encode(texts)

    store.add(
        all_chunks,
        embeddings,
    )

    return len(all_chunks)


# ============================================================
# RAG SERVICE
# ============================================================

class RAGService:

    def __init__(
        self,
        store: VectorStore,
    ):
        self.store = store

        self.embedding_model = os.getenv(
            "EMBEDDING_MODEL",
            DEFAULT_EMBEDDING_MODEL,
        )

        self.model = os.getenv(
            "OPENROUTER_MODEL",
            DEFAULT_OPENROUTER_MODEL,
        )

        self.client = None

        self._initialize_client()

    # --------------------------------------------------------
    # OPENROUTER
    # --------------------------------------------------------

    def _initialize_client(self) -> None:

        api_key = os.getenv(
            "OPENROUTER_API_KEY"
        )

        if not api_key:
            return

        if OpenAI is None:
            return

        self.client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": os.getenv(
                    "OPENROUTER_SITE_URL",
                    "http://localhost:8501",
                ),
                "X-Title": os.getenv(
                    "OPENROUTER_APP_NAME",
                    "RAG Generator",
                ),
            },
        )

    # --------------------------------------------------------
    # QUERY EMBEDDING
    # --------------------------------------------------------

    def _embed_query(
        self,
        question: str,
    ) -> np.ndarray:

        embedder = EmbeddingModel(
            self.embedding_model
        )

        return embedder.encode(
            [question]
        )

    # --------------------------------------------------------
    # RETRIEVAL
    # --------------------------------------------------------

    def retrieve(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Tuple[Chunk, float]]:

        query_embedding = self._embed_query(
            question
        )

        return self.store.search(
            query_embedding,
            top_k=top_k,
        )

    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    @staticmethod
    def _build_prompt(
        question: str,
        results: List[Tuple[Chunk, float]],
    ) -> str:

        context_parts: List[str] = []

        for index, (chunk, score) in enumerate(
            results,
            start=1,
        ):

            location = ""

            if chunk.page is not None:
                location = (
                    f"Page {chunk.page}"
                )

            context_parts.append(
                f"""
SOURCE {index}
Document: {chunk.source}
{location}
Content:
{chunk.text}
""".strip()
            )

        context = "\n\n---\n\n".join(
            context_parts
        )

        return f"""
You are a grounded document question-answering assistant.

Answer the user's question using ONLY the information
contained in the provided document context.

Important rules:

1. Do not invent facts.
2. Do not use outside knowledge.
3. If the answer is not supported by the context,
   clearly say that the uploaded documents do not
   contain enough information.
4. If the context contains the answer, answer directly.
5. Combine information from multiple sources when needed.
6. Keep the answer clear and concise.
7. Do not mention similarity scores.
8. Do not mention internal retrieval processes.
9. When possible, mention the relevant document or page
   naturally in the answer.

USER QUESTION:
{question}

DOCUMENT CONTEXT:
{context}
""".strip()

    # --------------------------------------------------------
    # OPENROUTER GENERATION
    # --------------------------------------------------------

    def _generate(
        self,
        prompt: str,
    ) -> str:

        if self.client is None:
            raise RuntimeError(
                "OpenRouter is not configured. "
                "Set OPENROUTER_API_KEY in your .env file."
            )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise, grounded RAG "
                        "assistant. Use only the provided "
                        "document context."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.1,
        )

        if not response.choices:
            raise RuntimeError(
                "OpenRouter returned an empty response."
            )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "OpenRouter returned empty content."
            )

        return content.strip()

    # --------------------------------------------------------
    # ANSWER
    # --------------------------------------------------------

    def answer(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> Dict[str, Any]:

        question = question.strip()

        if not question:
            raise ValueError(
                "Question cannot be empty."
            )

        results = self.retrieve(
            question,
            top_k=top_k,
        )

        if not results:

            return {
                "answer": (
                    "I don't have enough information "
                    "in the uploaded documents to answer that."
                ),
                "citations": [],
            }

        prompt = self._build_prompt(
            question,
            results,
        )

        answer = self._generate(
            prompt
        )

        citations = []

        for chunk, score in results:

            citation = {
                "source": chunk.source,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "similarity": round(
                    float(score),
                    4,
                ),
                "text": chunk.text,
            }

            citations.append(
                citation
            )

        return {
            "answer": answer,
            "citations": citations,
        }