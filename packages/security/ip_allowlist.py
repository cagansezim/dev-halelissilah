# packages/security/ip_allowlist.py
from __future__ import annotations
import ipaddress, os
from typing import Iterable, List
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

LOCAL_LOOPBACKS = {"127.0.0.1", "::1", "localhost"}
LOCAL_NETS = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("192.168.65.0/24"),  # Docker Desktop (macOS)
]

IP_MODE = os.getenv("IP_MODE", "private").lower()         # "off" | "private" | "explicit"
TRUST_XFF = os.getenv("IP_TRUST_XFF", "1") not in ("0", "false", "False")
IP_DEBUG  = os.getenv("IP_DEBUG", "0") in ("1", "true", "True")

def _parse_allowlist(items: Iterable[str]) -> List[ipaddress._BaseNetwork]:
    nets: List[ipaddress._BaseNetwork] = []
    for raw in items:
        raw = (raw or "").strip()
        if not raw:
            continue
        if raw in LOCAL_LOOPBACKS:
            continue
        try:
            nets.append(ipaddress.ip_network(raw if "/" in raw else f"{raw}/32", strict=False))
        except Exception:
            # ignore malformed entry
            pass
    return nets

class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """
    IP allow-list with sane Docker/LAN defaults.
    - IP_MODE=off      -> allow all
    - IP_MODE=private  -> allow RFC1918 + link-local + DockerDesktop + loopback
    - IP_MODE=explicit -> allow only ALLOWED_IPS (CIDR/host) + loopback (+ first private peer seen)
    """
    def __init__(self, app, allowlist: Iterable[str] = ()):
        super().__init__(app)
        explicit = _parse_allowlist(allowlist)
        nets = LOCAL_NETS.copy()
        if IP_MODE == "explicit":
            nets.extend(explicit)
        elif IP_MODE == "private":
            nets.extend(PRIVATE_NETS)
        # else "off": nets unused
        self.nets = nets
        self.explicit = (IP_MODE == "explicit")

    @staticmethod
    def _client_ip(request: Request) -> str:
        if TRUST_XFF:
            xf = request.headers.get("x-forwarded-for")
            if xf:
                return xf.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    def _allowed(self, ip_str: str) -> bool:
        if ip_str in LOCAL_LOOPBACKS:
            return True
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        return any(ip in net for net in self.nets)

    async def dispatch(self, request: Request, call_next):
        if IP_MODE == "off":
            return await call_next(request)

        ip_str = self._client_ip(request)

        # In explicit mode, auto-allow the first private peer (Docker bridge) so host curls work.
        if self.explicit:
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private and not self._allowed(ip_str):
                    self.nets.append(ipaddress.ip_network(f"{ip_str}/32"))
            except Exception:
                pass

        ok = (IP_MODE == "private" and self._allowed(ip_str)) or (IP_MODE == "explicit" and self._allowed(ip_str))
        if not ok:
            if IP_DEBUG:
                # Print a line per reject; visible in container logs
                print(f"[IP-ALLOW] reject ip={ip_str} mode={IP_MODE} nets={[str(n) for n in self.nets]}", flush=True)
            raise HTTPException(status_code=403, detail="IP not allowed")
        return await call_next(request)
