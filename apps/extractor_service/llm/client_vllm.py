import httpx, json, base64
from ..config import settings

async def chat_json(model: str, system: str, user_text: str, images: list[bytes]|None=None) -> str:
    headers={"Content-Type":"application/json"}
    if settings.VLLM_API_KEY: headers["Authorization"]=f"Bearer {settings.VLLM_API_KEY}"
    content = [{"type":"text","text":user_text}]
    if images:
        for b in images:
            content.append({"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(b).decode()}})
    payload = {
        "model": model, "temperature": 0,
        "messages":[{"role":"system","content":system},{"role":"user","content":content if images else user_text}]
    }
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{settings.VLLM_BASE_URL}/v1/chat/completions", headers=headers, content=json.dumps(payload))
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
