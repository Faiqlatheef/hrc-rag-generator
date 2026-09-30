import os

import requests
import streamlit as st


API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="RAG Generator",
    page_icon="📚",
    layout="wide",
)

st.title("📚 RAG Generator")

st.caption(
    "Upload documents, build a searchable knowledge base, "
    "and ask questions grounded in the uploaded content."
)


# ============================================================
# SIDEBAR — KNOWLEDGE BASE
# ============================================================

with st.sidebar:
    st.header("Knowledge Base")

    # --------------------------------------------------------
    # Clear knowledge base
    # --------------------------------------------------------

    if st.button(
        "Clear current knowledge base",
        type="secondary",
        use_container_width=True,
    ):
        try:
            response = requests.delete(
                f"{API}/documents",
                timeout=30,
            )

            response.raise_for_status()

            st.success("Knowledge base cleared.")
            st.rerun()

        except requests.RequestException as exc:
            st.error(f"Could not clear knowledge base: {exc}")

    st.divider()

    # --------------------------------------------------------
    # API health / statistics
    # --------------------------------------------------------

    try:
        response = requests.get(
            f"{API}/health",
            timeout=10,
        )

        response.raise_for_status()

        health = response.json()

        st.metric(
            "Documents",
            health.get("documents_indexed", 0),
        )

        st.metric(
            "Chunks",
            health.get("chunks_indexed", 0),
        )

        if health.get("llm_configured"):
            st.success(
                f"LLM: {health.get('llm_provider', 'configured')}"
            )
        else:
            st.warning("LLM: not configured")

    except requests.RequestException:
        st.warning(
            "API is not reachable.\n\n"
            "Start the FastAPI server first."
        )


# ============================================================
# 1. UPLOAD DOCUMENTS
# ============================================================

st.subheader("1. Upload documents")

files = st.file_uploader(
    "Upload PDF, DOCX, TXT or Markdown files",
    type=["pdf", "docx", "txt", "md"],
    accept_multiple_files=True,
)

replace_existing = st.checkbox(
    "Replace the current knowledge base",
    value=True,
    help=(
        "Enable this when you want to create a new knowledge base "
        "from the uploaded documents."
    ),
)


# ============================================================
# INDEX DOCUMENTS
# ============================================================

if st.button(
    "Index documents",
    disabled=not files,
    type="primary",
    use_container_width=True,
):
    payload = [
        (
            "files",
            (
                file.name,
                file.getvalue(),
                file.type or "application/octet-stream",
            ),
        )
        for file in files
    ]

    with st.spinner("Indexing documents..."):
        try:
            response = requests.post(
                f"{API}/documents",
                files=payload,
                params={
                    "replace_existing": replace_existing,
                },
                timeout=180,
            )

            response.raise_for_status()

            result = response.json()

            st.success(
                f"Indexed {result['documents']} document(s) "
                f"and {result['chunks_indexed']} chunks."
            )

            st.info(
                f"Total chunks in knowledge base: "
                f"{result['total_chunks']}"
            )

        except requests.RequestException as exc:
            try:
                detail = response.json().get("detail", str(exc))
            except Exception:
                detail = str(exc)

            st.error(f"Indexing failed: {detail}")


# ============================================================
# 2. ASK QUESTION
# ============================================================

st.subheader("2. Ask a grounded question")

question = st.text_area(
    "Question",
    placeholder=(
        "Example: What are the main objectives mentioned "
        "in the document?"
    ),
    height=100,
)


if st.button(
    "Ask",
    disabled=not question.strip(),
    type="primary",
    use_container_width=True,
):

    with st.spinner("Searching the knowledge base and generating an answer..."):

        try:
            response = requests.post(
                f"{API}/query",
                json={
                    "question": question.strip(),
                },
                timeout=180,
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as exc:

            try:
                detail = response.json().get(
                    "detail",
                    str(exc),
                )
            except Exception:
                detail = str(exc)

            st.error(
                f"Unable to answer the question: {detail}"
            )

            st.stop()


    # ========================================================
    # ANSWER
    # ========================================================

    st.subheader("Answer")

    answer = data.get(
        "answer",
        "No answer was returned.",
    )

    st.write(answer)


    # ========================================================
    # SOURCES
    # ========================================================

    st.subheader("Retrieved sources")

    citations = data.get(
        "citations",
        [],
    )

    if not citations:

        st.info(
            "No supporting sources were retrieved."
        )

    else:

        for index, citation in enumerate(
            citations,
            start=1,
        ):

            source = citation.get(
                "source",
                "Unknown document",
            )

            page = citation.get("page")

            if page:
                location = f"Page {page}"
            else:
                chunk_index = citation.get(
                    "chunk_index",
                    "?",
                )
                location = f"Chunk {chunk_index}"

            with st.container():

                st.markdown(
                    f"**[{index}] {source}** — {location}"
                )

                # Similarity is intentionally hidden from
                # the normal UI. It is an internal retrieval
                # metric and is not useful to most users.

                preview = citation.get(
                    "text",
                    "",
                )

                if preview:
                    with st.expander("View retrieved text"):
                        st.write(preview)