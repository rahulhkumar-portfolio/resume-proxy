import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI()

# Load your profile once at startup
PROFILE_PATH = Path(__file__).parent / "profile.md"

def load_profile() -> str:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError("profile.md not found. Please create your profile file.")
    return PROFILE_PATH.read_text(encoding="utf-8")

SYSTEM_PROMPT_TEMPLATE = """You are a professional AI proxy representing the person described below. \
Your role is to answer questions from recruiters, hiring managers, and other professionals \
on their behalf — accurately, confidently, and in first person (as if you are them).

Guidelines:
- Speak as "I" — you ARE this person's proxy
- Be warm, professional, and enthusiastic about their work
- Be honest and accurate — never invent or exaggerate anything not in the profile
- If asked something not covered in the profile, say you'd prefer to discuss it directly
- Keep responses concise but thorough — recruiters are busy
- You may ask clarifying questions about the role/company if helpful
- Highlight relevant strengths when the question gives you an opening

--- PROFILE START ---
{profile}
--- PROFILE END ---
"""

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[Message]

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        profile = load_profile()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(profile=profile)

    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt,
    )

    # Convert history (all but last message) into Gemini format
    history = []
    for m in request.messages[:-1]:
        history.append({
            "role": "user" if m.role == "user" else "model",
            "parts": [m.content],
        })

    last_message = request.messages[-1].content
    chat_session = model.start_chat(history=history)

    def generate():
        response = chat_session.send_message(last_message, stream=True)
        for chunk in response:
            if chunk.text:
                yield f"data: {json.dumps({'text': chunk.text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {"status": "ok"}
