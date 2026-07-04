"""
PDF -> text -> chunks.

Chunking is done per-page so every chunk carries an accurate page number for
citations. Within a page, text is split with overlap so we don't cut a
sentence in half between chunks.
"""
import pdfplumber
from config import RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP
from utils.logger import logger


def extract_and_chunk(file_path: str, chunk_size: int = RAG_CHUNK_SIZE,
                       overlap: int = RAG_CHUNK_OVERLAP) -> list[dict]:
    """Returns a list of {"text": str, "page": int} chunks."""
    chunks = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()
                if not text:
                    continue

                step = max(1, chunk_size - overlap)
                for i in range(0, len(text), step):
                    chunk = text[i:i + chunk_size].strip()
                    if chunk:
                        chunks.append({"text": chunk, "page": page_num})
    except Exception as e:
        logger.error(f"Failed to extract/chunk PDF {file_path}: {e}")
        raise

    return chunks
