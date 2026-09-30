from datetime import datetime
from pathlib import Path


TRANSCRIPT_DIR = Path("transcripts")
TRANSCRIPT_FILE = TRANSCRIPT_DIR / "development_transcript.md"


def initialize_transcript():
    """Create the transcript file if it does not already exist."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    if not TRANSCRIPT_FILE.exists():
        TRANSCRIPT_FILE.write_text(
            "# AI Development Transcript\n\n"
            "This file records AI-assisted development activities "
            "for the RAG Generator project.\n\n",
            encoding="utf-8",
        )


def log_exchange(
    user_message: str,
    assistant_response: str,
    tool: str = "ChatGPT",
):
    """Append an AI development exchange to the transcript."""

    initialize_transcript()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"""
---

## Development Session — {timestamp}

**AI Tool:** {tool}

### User

{user_message.strip()}

### AI Assistant

{assistant_response.strip()}

"""

    with TRANSCRIPT_FILE.open("a", encoding="utf-8") as file:
        file.write(entry)


if __name__ == "__main__":
    initialize_transcript()
    print(f"Transcript initialized: {TRANSCRIPT_FILE}")