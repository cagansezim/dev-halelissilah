import base64, hashlib
from typing import Tuple

def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def decode_base64(b64: str) -> bytes:
    # tolerate data-url prefixes
    if "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64, validate=True)

def verify_hashes(data: bytes, md5_expected: str | None = None) -> Tuple[str, str]:
    md5v = md5_hex(data)
    sha256v = sha256_hex(data)
    if md5_expected and md5v.lower() != md5_expected.lower():
        raise ValueError(f"MD5 mismatch: expected {md5_expected} got {md5v}")
    return md5v, sha256v
