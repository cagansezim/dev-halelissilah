# packages/clients/internal_api/client.py
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urljoin
import httpx


class InternalAPIError(RuntimeError):
    pass


class InternalAPIClient:
    """
    Contract (as tested against the internal API):
      - Auth: POST {email, password} -> {"success": true, "data": {"token": "..."}}
              We re-auth **on every request** (per requirement).
      - list : POST {"BaslangicTarihi":"YYYY-MM-DD","BitisTarihi":"YYYY-MM-DD"}
      - json : POST {"Id":"<kod>","Hash":"<expense-hash>"}
      - file : POST {"Id":"<kod>","FileId":"<fid>","FileHash":"<fhash>"} -> base64 string
               (may be raw string OR {"data": "<base64>"} — we normalize)
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_url: str,
        list_url: str,
        json_url: str,
        file_url: str,
        email: str,
        password: str,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_url = self._resolve(auth_url)
        self.list_url = self._resolve(list_url)
        self.json_url = self._resolve(json_url)
        self.file_url = self._resolve(file_url)
        self.email = email
        self.password = password
        self.timeout = timeout

        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "pruva-invoice-extractor/1.0"},
        )

    # ---------- internals ----------
    def _resolve(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return urljoin(self.base_url + "/", url.lstrip("/"))

    def _auth(self) -> str:
        r = self._client.post(
            self.auth_url,
            json={"email": self.email, "password": self.password},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        if r.status_code != 200:
            raise InternalAPIError(f"Auth HTTP {r.status_code} at {self.auth_url}: {r.text[:200]}")
        try:
            data = r.json()
        except Exception:
            raise InternalAPIError(f"Auth returned non-JSON at {self.auth_url}: {r.text[:200]}")

        if not data or not data.get("success"):
            raise InternalAPIError(f"Auth failed: {data}")
        token = (data.get("data") or {}).get("token")
        if not token:
            raise InternalAPIError("Auth ok but token missing in response")
        return token

    def _post_with_token(self, url: str, payload: Dict[str, Any]) -> httpx.Response:
        token = self._auth()  # per-request auth
        return self._client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json", "token": token},
        )

    # ---------- high-level ----------
    def list_expenses(self, start_date: str, end_date: str) -> Dict[str, Any]:
        payload = {"BaslangicTarihi": start_date, "BitisTarihi": end_date}
        r = self._post_with_token(self.list_url, payload)
        if r.status_code != 200:
            raise InternalAPIError(f"List HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    # Accept multiple aliases so callers can pass id/kod/expense_id and hash/hash_/expense_hash
    def expense_json(
        self,
        id: Optional[int] = None,  # noqa: A002
        hash: Optional[str] = None,
        **kw: Any,
    ) -> Dict[str, Any]:
        if id is None:
            id = kw.get("kod") or kw.get("expense_id") or kw.get("Id") or kw.get("Kod")
        if hash is None:
            hash = kw.get("hash_") or kw.get("expense_hash") or kw.get("Hash") or kw.get("hash")
        if id is None or hash is None:
            raise InternalAPIError("expense_json requires id/kod and hash")

        payload = {"Id": str(int(id)), "Hash": str(hash)}
        r = self._post_with_token(self.json_url, payload)
        if r.status_code != 200:
            raise InternalAPIError(f"JSON HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def expense_file_base64(
        self,
        id: Optional[int] = None,  # noqa: A002
        file_id: Optional[int] = None,
        file_hash: Optional[str] = None,
        **kw: Any,
    ) -> str:
        if id is None:
            id = kw.get("kod") or kw.get("expense_id") or kw.get("Id") or kw.get("Kod")
        if file_id is None:
            file_id = kw.get("fileId") or kw.get("FileId") or kw.get("fid")
        if file_hash is None:
            file_hash = kw.get("fileHash") or kw.get("FileHash") or kw.get("Hash")

        if id is None or file_id is None or file_hash is None:
            raise InternalAPIError("expense_file_base64 requires id/kod, file_id, file_hash")

        payload = {"Id": str(int(id)), "FileId": str(int(file_id)), "FileHash": str(file_hash)}
        r = self._post_with_token(self.file_url, payload)
        if r.status_code != 200:
            raise InternalAPIError(f"File HTTP {r.status_code}: {r.text[:200]}")

        # normalize common variants
        try:
            js = r.json()
            if isinstance(js, dict) and isinstance(js.get("data"), str):
                return js["data"]
            if isinstance(js, str):
                return js
        except Exception:
            pass
        return r.text.strip().strip('"\n\r ')
