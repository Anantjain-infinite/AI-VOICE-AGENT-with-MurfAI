"""
ChromaDB wrapper: one collection per chat session, so a user's uploaded
documents are only ever retrieved within their own session.
"""
import chromadb
from google import genai
import config
from utils.logger import logger

_client = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    return _client


def _collection_name(session_id: str) -> str:
    # Chroma collection names must be alnum/underscore/hyphen; session ids
    # are UUIDs so this is already safe, but sanitize defensively.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return f"docs_{safe}"


def get_collection(session_id: str):
    return get_chroma_client().get_or_create_collection(_collection_name(session_id))


def embed_text(text: str) -> list[float]:
    client = genai.Client()
    result = client.models.embed_content(model=config.EMBEDDING_MODEL, contents=text)
    return result.embeddings[0].values


def add_chunks(session_id: str, doc_id: str, filename: str, chunks: list[dict]):
    if not chunks:
        return
    collection = get_collection(session_id)
    embeddings = [embed_text(c["text"]) for c in chunks]
    collection.add(
        ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[{"doc_id": doc_id, "filename": filename, "page": c["page"]} for c in chunks],
    )


def query_chunks(session_id: str, question: str, top_k: int = None) -> list[dict]:
    top_k = top_k or config.RAG_TOP_K
    collection = get_collection(session_id)
    if collection.count() == 0:
        return []

    q_embedding = embed_text(question)
    results = collection.query(query_embeddings=[q_embedding], n_results=min(top_k, collection.count()))

    chunks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append({"text": doc, "page": meta["page"], "doc_id": meta["doc_id"], "filename": meta["filename"]})
    return chunks


def delete_document(session_id: str, doc_id: str):
    collection = get_collection(session_id)
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception as e:
        logger.warning(f"Failed to delete doc_id {doc_id} from Chroma: {e}")


def delete_session_collection(session_id: str):
    try:
        get_chroma_client().delete_collection(_collection_name(session_id))
    except Exception as e:
        logger.warning(f"Failed to delete collection for session {session_id}: {e}")
