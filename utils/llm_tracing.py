import os

# Privacy-first: prompts and replies are NOT sent unless you switch this on.
LOG_CONTENT = os.getenv("LANGFUSE_LOG_CONTENT", "false").lower() == "true"

def content(text: str):
    return text if LOG_CONTENT else f"<redacted: {len(text)} chars>"

def usage_details(um) -> dict:
    if um is None:
        return {}
    out = (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    return {"input_tokens": um.prompt_token_count or 0, "output_tokens": out}