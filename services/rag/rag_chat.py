"""
Retrieve relevant chunks for a question, ground a Gemini answer in them,
and return page-level citations alongside the answer.
"""
from google import genai
from google.genai import types
import config
from services.rag.vector_store import query_chunks
from utils.logger import logger

_SYSTEM_INSTRUCTION = (
    "You are a document Q&A assistant. Answer the question using ONLY the "
    "provided context from the user's uploaded document(s). If the answer "
    "isn't contained in the context, say clearly that you couldn't find it "
    "in the uploaded documents instead of guessing. Be concise. When useful, "
    "mention which page the information came from."
)


def rag_answer(session_id: str, question: str) -> dict:
    chunks = query_chunks(session_id, question)

    if not chunks:
        return {
            "answer": "I couldn't find anything relevant in your uploaded documents. "
                      "Try uploading a PDF first, or rephrase your question.",
            "sources": [],
        }

    context = "\n\n".join(
        f"[{c['filename']} - page {c['page']}]\n{c['text']}" for c in chunks
    )
    prompt = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=config.CHAT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=_SYSTEM_INSTRUCTION),
        )
        answer_text = response.text
    except Exception as e:
        logger.error(f"RAG generation failed: {e}")
        answer_text = "Something went wrong while generating the answer from your documents."

    sources = []
    seen = set()
    for c in chunks:
        key = (c["doc_id"], c["page"])
        if key not in seen:
            seen.add(key)
            sources.append({"doc_id": c["doc_id"], "filename": c["filename"], "page": c["page"]})
    sources.sort(key=lambda s: s["page"])

    return {"answer": answer_text, "sources": sources}
