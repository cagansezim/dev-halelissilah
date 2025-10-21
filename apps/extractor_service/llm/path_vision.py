import json
from .prompts import SCHEMA_TR
from .client_vllm import chat_json

async def run_vision(model_id: str, page_pngs: list[bytes], description: str|None):
    user = ((description or "") + "\n" + "Görsel faturadan şemaya uygun JSON üret.").strip()
    txt = await chat_json(model_id, SCHEMA_TR, user, images=page_pngs)
    try:
        return json.loads(txt)
    except Exception:
        s = txt[txt.find("{"): txt.rfind("}")+1]
        return json.loads(s)
