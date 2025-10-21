import json
from .prompts import SCHEMA_TR, text_user_prompt
from .client_vllm import chat_json

async def run_text(model_id: str, description: str|None, page_texts: list[str], tables: str|None, email: str|None):
    user = text_user_prompt(description or "", page_texts, tables, email)
    txt = await chat_json(model_id, SCHEMA_TR, user)
    try:
        return json.loads(txt)
    except Exception:
        s = txt[txt.find("{"): txt.rfind("}")+1]
        return json.loads(s)
