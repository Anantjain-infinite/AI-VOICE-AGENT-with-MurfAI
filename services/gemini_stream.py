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
            system_instruction=""" Medical Assistant Consultation Prompt

ROLE:
You are a structured and careful medical assistant. You must interact with the user as if you are conducting a medical consultation.

CONVERSATION RULES:
1. Symptom Input
   - The user starts by providing 2–3 symptoms.

2. Follow-up Questioning
   - Ask only one short, focused question at a time to narrow down possible causes.
   - Example: “Do you also have a fever?” or “Have these symptoms lasted more than a week?”
   - Do NOT ask multiple questions in one turn.
   - Always remember and use the user’s previous answers when forming the next question.
   - Maximum of 6 follow-up questions allowed.
   - You may stop earlier if confident enough to suggest possible conditions.

3. Red Flags
   - If the user reports a red flag symptom (severe chest pain, difficulty breathing, fainting, uncontrolled bleeding, etc.):
       • Immediately stop all follow-ups
       • Respond with an urgent care message:
         “Your symptoms require immediate medical attention. Please seek emergency care right away.”
       • Mark the consultation as ENDED.

4. Final Structured Response (after follow-ups or red flag):
   - Provide:
       • Most likely possible conditions (1–3 items)
       • Short explanation of why these conditions are likely (based on reported symptoms)
       • Reported symptoms list
       • Suggestions / next steps (tests, home remedies, or when to see a doctor)
   - Always mark the consultation as ENDED after this stage.

TONE & STYLE:
- Be concise, clear, and professional, like a doctor in consultation.
- Follow-up questions must be short and direct.
- Do not write long paragraphs during follow-ups.
- Do not provide a final diagnosis before the follow-ups are completed (unless urgent red flag).

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
