# Stub kept so we can load vision models locally if your vLLM doesn't serve multi-image.
# We'll flip to this client per-model with a small switch if needed.
def vision_chat_local(images: list[bytes], system: str, user: str, model_id: str) -> str:
    raise NotImplementedError("Enable local Transformers vision runner when needed.")
