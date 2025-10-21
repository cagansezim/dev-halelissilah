import clamd, time, os

class AVScanner:
    def __init__(self, host: str, port: int, required: bool = False, tries: int = 5, delay: float = 1.5):
        self.host, self.port = host, port
        self.required = required
        self.tries = max(1, tries)
        self.delay = delay
        self._client = None

    def _connect(self):
        # Retry a few times because clamd can finish DB updates after container "ready"
        exc = None
        for _ in range(self.tries):
            try:
                c = clamd.ClamdNetworkSocket(self.host, self.port)
                c.ping()
                return c
            except Exception as e:
                exc = e
                time.sleep(self.delay)
        if self.required:
            raise RuntimeError(f"ClamAV not reachable at {self.host}:{self.port}") from exc
        return None

    def scan_bytes(self, data: bytes) -> None:
        if self._client is None:
            self._client = self._connect()
        if not self._client:
            # soft-skip if not required
            return
        res = self._client.instream(data)
        status, sig = res.get("stream", ("OK", None))
        if status != "OK":
            raise ValueError(f"AV scan failed: {status} {sig or ''}".strip())
