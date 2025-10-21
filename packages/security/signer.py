import base64, hashlib, hmac, time, uuid
from urllib.parse import urlparse, parse_qsl, urlencode

CANONICAL_HEADERS = ("content-type", "x-pruva-keyid", "x-pruva-timestamp", "x-pruva-nonce", "x-pruva-body-sha256")

def _canonical_query(path_with_query: str) -> str:
    u = urlparse(path_with_query)
    qs = urlencode(sorted(parse_qsl(u.query, keep_blank_values=True)))
    return u.path + (("?" + qs) if qs else "")

def build_signature(method: str, host: str, path_with_query: str, headers: dict, body: bytes, secret: str) -> str:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    canonical = [
        method.upper(),
        host.lower(),
        _canonical_query(path_with_query),
    ]
    for h in CANONICAL_HEADERS:
        canonical.append(f"{h}:{headers.get(h, '')}")
    canonical.append(f"x-pruva-body-sha256:{body_hash}")
    msg = ("\n".join(canonical)).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"v1={base64.b64encode(sig).decode()}", body_hash

def signed_headers(key_id: str, secret: str, content_type: str, method: str, host: str, path_with_query: str, body: bytes):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    nonce = str(uuid.uuid4())
    headers = {
        "content-type": content_type,
        "x-pruva-keyid": key_id,
        "x-pruva-timestamp": now,
        "x-pruva-nonce": nonce,
    }
    signature, body_hash = build_signature(method, host, path_with_query, headers, body, secret)
    headers["x-pruva-body-sha256"] = body_hash
    headers["x-pruva-signature"] = signature
    return headers
