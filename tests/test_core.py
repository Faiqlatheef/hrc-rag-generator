from app.core import Chunker


def test_chunker_returns_overlap_chunks():
    text = "Sentence one. " * 150
    chunks = Chunker(200, 40).split(text)
    assert len(chunks) > 1
    assert all(chunks)


def test_chunker_empty():
    assert Chunker().split("   ") == []


def test_chunker_rejects_invalid_overlap():
    try:
        Chunker(100, 100)
        assert False, "Expected ValueError"
    except ValueError:
        pass
