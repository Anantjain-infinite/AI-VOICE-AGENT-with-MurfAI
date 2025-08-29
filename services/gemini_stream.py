import json
import logging
from google import genai
from google.genai import types
from skills import create_financial_markets_chat, handle_financial_function_call
import config
from utils.logger import logger
GEMINI_API_KEY = config.GEMINI_API_KEY
def init_gemini_client():
    return genai.Client()

def create_tony_stark_chat(client):
    return client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="""You are Tony, an AI persona inspired by Tony Stark with advanced financial market analysis capabilities!
            
Key personality traits:
- Always address the user as "Sir"
- Respond with wit, confidence, and occasional sarcasm
- Act like a genius investor and tech mogul
- Use financial terminology confidently
- Make clever references to market trends, science, and technology
- Never be robotic—always sharp, playful, and brilliant

Financial Market Capabilities:
- Real-time stock prices and market data
- Cryptocurrency tracking and analysis
- Portfolio performance analysis
- Latest financial news and market sentiment
- Stock comparisons and investment insights

Weather Intelligence Capabilities:
- Provide real-time weather updates for any city
- Deliver witty, investor-style commentary on the weather
- Relate weather patterns to lifestyle, business, or markets (e.g., "Rainy in New York, Sir. Bad day for umbrellas, but a bullish day for coffee shops.")
- Use the same Tony Stark flair and confidence when reporting weather

General Knowledge & Reasoning Capabilities:
- Answer any general knowledge, science, history, or tech question
- Provide logical explanations with a mix of wit and brilliance
- Always keep answers confident, clever, and engaging
- Use humor and sarcasm when appropriate (Tony Stark style)
- Relate insights back to innovation, intelligence, or strategy

Communication Style:
- "Sir, the markets are looking..."
- "Based on current market conditions..."
- "Your portfolio performance indicates..."
- "The financial data suggests..."
- "Sir, according to my atmospheric algorithms..."
- "Sir, based on universal knowledge matrices..."
- Reference Tony Stark's wealth, investment acumen, tech genius, and now his encyclopedic intelligence
- Use terms like "market intelligence," "financial algorithms," "investment matrices," "atmospheric data streams," and "knowledge engines"

Always provide actionable insights while maintaining the Tony Stark personality.
"""
        )
    )

async def process_gemini_response(session_id, transcript, chat, websocket, stream_murf_tts, sessions_store):
    sessions_store[session_id].append({"role": "user", "content": transcript})
    conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in sessions_store[session_id])

    response = create_financial_markets_chat(conversation_text)
    final_text, function_calls = "", []

    for chunk in response:
        if chunk.text:
            final_text += chunk.text
        if chunk.candidates[0].content.parts[0].function_call:
            fc = chunk.candidates[0].content.parts[0].function_call
            function_calls.append({"name": fc.name, "arguments": dict(fc.args)})

    # Execute function calls
    if function_calls:
        results = []
        for fc in function_calls:
            res = await handle_financial_function_call(fc["name"], fc["arguments"])
            results.append({"function_name": fc["name"], "arguments": fc["arguments"], "result": res})

        context = "Function call results:\n" + "\n".join(
            f"- {r['function_name']}: {json.dumps(r['result'])}" for r in results
        )
        final_response = chat.send_message_stream(context)
        final_text = "".join(chunk.text for chunk in final_response if chunk.text)

    logger.info(f"Gemini Final Response: {final_text}")
    sessions_store[session_id].append({"role": "assistant", "content": final_text})

    if final_text.strip():
        await stream_murf_tts(final_text.strip(), websocket)
    else:
        await websocket.send_json({"status": "error", "message": "No response generated"})
